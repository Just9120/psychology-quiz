from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


SESSION_QUESTION_LIMIT = 10


def get_connection(db_path: str) -> sqlite3.Connection:
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000;")
    if db_file != Path(":memory:"):
        conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db_connection(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("SELECT 1;")
        ensure_users_reading_mode_column(conn)
        ensure_quiz_sessions_difficulty_mode_column(conn)
        ensure_quiz_session_selected_categories_table(conn)
        ensure_performance_indexes(conn)
    finally:
        conn.close()


def ensure_performance_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_quiz_sessions_user_status ON quiz_sessions(user_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_quiz_answers_session_question ON quiz_answers(session_id, question_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_quiz_session_questions_session_order ON quiz_session_questions(session_id, order_index)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_quiz_session_questions_question ON quiz_session_questions(question_id)"
    )


VALID_READING_MODES = {"normal", "bionic"}
VALID_DIFFICULTY_MODES = {"easy", "medium", "hard"}


def ensure_users_reading_mode_column(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(users)").fetchall()
    column_names = {str(column["name"]) for column in columns}
    if "reading_mode" in column_names:
        return

    conn.execute(
        "ALTER TABLE users ADD COLUMN reading_mode TEXT NOT NULL DEFAULT 'normal'"
    )


def ensure_quiz_session_selected_categories_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_session_selected_categories (
            session_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (session_id, category_id),
            FOREIGN KEY (session_id) REFERENCES quiz_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
        """
    )


def ensure_quiz_sessions_difficulty_mode_column(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(quiz_sessions)").fetchall()
    column_names = {str(column["name"]) for column in columns}
    if "difficulty_mode" in column_names:
        return

    conn.execute("ALTER TABLE quiz_sessions ADD COLUMN difficulty_mode TEXT")


def _normalize_reading_mode(mode: str | None) -> str:
    if mode in VALID_READING_MODES:
        return str(mode)
    return "normal"


def _normalize_difficulty_mode(mode: str | None) -> str | None:
    if mode is None:
        return None

    normalized_mode = str(mode).strip().lower()
    if normalized_mode in {"", "any"}:
        return None
    if normalized_mode in VALID_DIFFICULTY_MODES:
        return normalized_mode
    return None


def _slugify_category(name: str) -> str:
    slug = "-".join(name.lower().strip().split())
    return slug or "category"


def ensure_categories(conn: sqlite3.Connection, category_names: list[str]) -> dict[str, int]:
    category_ids: dict[str, int] = {}

    for raw_name in category_names:
        name = raw_name.strip()
        if not name:
            continue

        slug = _slugify_category(name)
        conn.execute(
            """
            INSERT INTO categories (slug, name)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET slug = excluded.slug
            """,
            (slug, name),
        )

        row = conn.execute(
            "SELECT id FROM categories WHERE name = ?",
            (name,),
        ).fetchone()
        if row:
            category_ids[name] = int(row["id"])

    return category_ids


def upsert_approved_questions(conn: sqlite3.Connection, questions: list[dict[str, Any]]) -> dict[str, int]:
    approved = [item for item in questions if item.get("status") == "approved"]
    categories = sorted({str(item["category"]).strip() for item in approved if item.get("category")})
    category_ids = ensure_categories(conn, categories)

    inserted_or_updated = 0

    for item in approved:
        category_name = str(item["category"]).strip()
        category_id = category_ids.get(category_name)
        if not category_id:
            continue

        external_id = str(item["id"]).strip()
        source_ref = item.get("source_ref")
        difficulty = str(item.get("difficulty", "easy")).strip() or "easy"
        question_text = str(item["question"]).strip()
        explanation = item.get("explanation")

        conn.execute(
            """
            INSERT INTO questions (
                external_id, category_id, source_ref, difficulty, status, question_text, explanation
            )
            VALUES (?, ?, ?, ?, 'approved', ?, ?)
            ON CONFLICT(external_id) DO UPDATE SET
                category_id = excluded.category_id,
                source_ref = excluded.source_ref,
                difficulty = excluded.difficulty,
                status = excluded.status,
                question_text = excluded.question_text,
                explanation = excluded.explanation,
                updated_at = CURRENT_TIMESTAMP
            """,
            (external_id, category_id, source_ref, difficulty, question_text, explanation),
        )

        question_row = conn.execute(
            "SELECT id FROM questions WHERE external_id = ?",
            (external_id,),
        ).fetchone()
        if not question_row:
            continue

        question_id = int(question_row["id"])
        options = item.get("options", [])
        correct_option_index = int(item["correct_option_index"])

        for idx, option_text in enumerate(options):
            conn.execute(
                """
                INSERT INTO question_options (question_id, option_index, option_text, is_correct)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(question_id, option_index) DO UPDATE SET
                    option_text = excluded.option_text,
                    is_correct = excluded.is_correct
                """,
                (question_id, idx, str(option_text), 1 if idx == correct_option_index else 0),
            )

        if options:
            placeholders = ",".join("?" for _ in options)
            params = [question_id, *range(len(options))]
            conn.execute(
                f"""
                DELETE FROM question_options
                WHERE question_id = ?
                  AND option_index NOT IN ({placeholders})
                """,
                params,
            )
        else:
            conn.execute(
                "DELETE FROM question_options WHERE question_id = ?",
                (question_id,),
            )

        inserted_or_updated += 1

    return {
        "approved_questions": len(approved),
        "upserted_questions": inserted_or_updated,
        "categories": len(category_ids),
    }


def get_active_categories(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT c.id, c.slug, c.name
        FROM categories c
        WHERE EXISTS (
            SELECT 1 FROM questions q
            WHERE q.category_id = c.id AND q.status = 'approved'
        )
        ORDER BY c.name ASC
        """
    ).fetchall()


def create_or_load_user(
    conn: sqlite3.Connection,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,),
    ).fetchone()

    if row is None:
        try:
            conn.execute(
                """
                INSERT INTO users (telegram_user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                """,
                (telegram_user_id, username, first_name, last_name),
            )
        except sqlite3.IntegrityError:
            # Another caller may have inserted the same Telegram user inside a
            # concurrent transaction. Fall through to the normal load/update
            # path while preserving the caller-owned connection and transaction.
            pass

        row = conn.execute(
            "SELECT * FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()

    if row is None:
        raise RuntimeError("Не удалось создать или загрузить пользователя")

    profile_fields_changed = (
        row["username"] != username
        or row["first_name"] != first_name
        or row["last_name"] != last_name
    )
    if not profile_fields_changed:
        return row

    conn.execute(
        """
        UPDATE users
        SET username = ?,
            first_name = ?,
            last_name = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE telegram_user_id = ?
        """,
        (username, first_name, last_name, telegram_user_id),
    )

    row = conn.execute(
        "SELECT * FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Не удалось создать или загрузить пользователя")
    return row


def start_quiz_session(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int | None,
    difficulty_mode: str | None = None,
) -> int:
    normalized_difficulty_mode = _normalize_difficulty_mode(difficulty_mode)
    cursor = conn.execute(
        """
        INSERT INTO quiz_sessions (user_id, category_id, status, difficulty_mode)
        VALUES (?, ?, 'in_progress', ?)
        """,
        (user_id, category_id, normalized_difficulty_mode),
    )
    return int(cursor.lastrowid)


def abandon_in_progress_sessions_for_user(conn: sqlite3.Connection, user_id: int) -> int:
    cursor = conn.execute(
        """
        UPDATE quiz_sessions
        SET status = 'abandoned',
            finished_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
          AND status = 'in_progress'
        """,
        (user_id,),
    )
    return int(cursor.rowcount or 0)


def select_random_approved_question_ids_by_category(
    conn: sqlite3.Connection,
    category_id: int,
    limit: int | None = SESSION_QUESTION_LIMIT,
    difficulty_mode: str | None = None,
) -> list[int]:
    normalized_difficulty_mode = _normalize_difficulty_mode(difficulty_mode)
    params: list[Any] = [category_id]
    where_clause = "q.category_id = ? AND q.status = 'approved'"
    if normalized_difficulty_mode:
        where_clause += " AND q.difficulty = ?"
        params.append(normalized_difficulty_mode)

    query = f"""
        SELECT q.id
        FROM questions q
        WHERE {where_clause}
        ORDER BY RANDOM()
    """

    if limit is not None:
        query += "\nLIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [int(row["id"]) for row in rows]


def select_random_approved_question_ids_across_active_categories(
    conn: sqlite3.Connection,
    limit: int | None = SESSION_QUESTION_LIMIT,
    difficulty_mode: str | None = None,
) -> list[int]:
    normalized_difficulty_mode = _normalize_difficulty_mode(difficulty_mode)
    params: list[Any] = []
    where_clause = "q.status = 'approved'"
    if normalized_difficulty_mode:
        where_clause += " AND q.difficulty = ?"
        params.append(normalized_difficulty_mode)

    query = f"""
        SELECT q.id
        FROM questions q
        INNER JOIN categories c ON c.id = q.category_id
        WHERE {where_clause}
          AND EXISTS (
              SELECT 1
              FROM questions q2
              WHERE q2.category_id = c.id
                AND q2.status = 'approved'
          )
        ORDER BY RANDOM()
    """

    if limit is not None:
        query += "\nLIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [int(row["id"]) for row in rows]


def select_random_approved_question_ids_by_categories(
    conn: sqlite3.Connection,
    category_ids: list[int],
    limit: int | None = SESSION_QUESTION_LIMIT,
    difficulty_mode: str | None = None,
) -> list[int]:
    if not category_ids:
        return []

    placeholders = ",".join("?" for _ in category_ids)
    params: list[Any] = list(category_ids)
    where_clause = f"q.category_id IN ({placeholders}) AND q.status = 'approved'"
    normalized_difficulty_mode = _normalize_difficulty_mode(difficulty_mode)
    if normalized_difficulty_mode:
        where_clause += " AND q.difficulty = ?"
        params.append(normalized_difficulty_mode)

    query = f"""
        SELECT q.id
        FROM questions q
        WHERE {where_clause}
        ORDER BY RANDOM()
    """

    if limit is not None:
        query += "\nLIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [int(row["id"]) for row in rows]


def store_session_questions(conn: sqlite3.Connection, session_id: int, question_ids: list[int]) -> None:
    for order_index, question_id in enumerate(question_ids, start=1):
        conn.execute(
            """
            INSERT INTO quiz_session_questions (session_id, question_id, order_index)
            VALUES (?, ?, ?)
            """,
            (session_id, question_id, order_index),
        )


def get_session_question_count(conn: sqlite3.Connection, session_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS total_questions
        FROM quiz_session_questions
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    return int(row["total_questions"]) if row else 0


def get_current_unanswered_question(conn: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT
            sq.question_id,
            sq.order_index,
            q.question_text,
            q.explanation,
            (SELECT COUNT(*) FROM quiz_session_questions WHERE session_id = sq.session_id) AS total_questions
        FROM quiz_session_questions sq
        INNER JOIN questions q ON q.id = sq.question_id
        LEFT JOIN quiz_answers qa
            ON qa.session_id = sq.session_id
           AND qa.question_id = sq.question_id
        WHERE sq.session_id = ?
          AND qa.id IS NULL
        ORDER BY sq.order_index ASC
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()


def get_question_options(conn: sqlite3.Connection, question_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT option_index, option_text, is_correct
        FROM question_options
        WHERE question_id = ?
        ORDER BY option_index ASC
        """,
        (question_id,),
    ).fetchall()


def save_quiz_answer(
    conn: sqlite3.Connection,
    session_id: int,
    question_id: int,
    selected_option_index: int,
) -> dict[str, int]:
    existing = conn.execute(
        """
        SELECT is_correct
        FROM quiz_answers
        WHERE session_id = ? AND question_id = ?
        LIMIT 1
        """,
        (session_id, question_id),
    ).fetchone()
    if existing is not None:
        return {"is_correct": int(existing["is_correct"]), "already_answered": 1}

    option_row = conn.execute(
        """
        SELECT is_correct
        FROM question_options
        WHERE question_id = ? AND option_index = ?
        """,
        (question_id, selected_option_index),
    ).fetchone()
    is_correct = int(option_row["is_correct"]) if option_row else 0

    try:
        conn.execute(
            """
            INSERT INTO quiz_answers (session_id, question_id, selected_option_index, is_correct)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, question_id, selected_option_index, is_correct),
        )
    except sqlite3.IntegrityError:
        existing = conn.execute(
            """
            SELECT is_correct
            FROM quiz_answers
            WHERE session_id = ? AND question_id = ?
            LIMIT 1
            """,
            (session_id, question_id),
        ).fetchone()
        if existing is not None:
            return {"is_correct": int(existing["is_correct"]), "already_answered": 1}
        raise

    return {"is_correct": is_correct, "already_answered": 0}


def get_answered_questions_count(conn: sqlite3.Connection, session_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS answered_questions
        FROM quiz_answers
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    return int(row["answered_questions"]) if row else 0


def finalize_quiz_session(conn: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    stats = conn.execute(
        """
        SELECT
            COALESCE(SUM(qa.is_correct), 0) AS score,
            (SELECT COUNT(*) FROM quiz_session_questions WHERE session_id = ?) AS total_questions
        FROM quiz_answers qa
        WHERE qa.session_id = ?
        """,
        (session_id, session_id),
    ).fetchone()

    if stats is None:
        return None

    score = int(stats["score"])
    total_questions = int(stats["total_questions"])

    conn.execute(
        """
        UPDATE quiz_sessions
        SET score = ?,
            total_questions = ?,
            finished_at = CURRENT_TIMESTAMP,
            status = 'finished'
        WHERE id = ?
        """,
        (score, total_questions, session_id),
    )

    return conn.execute(
        "SELECT * FROM quiz_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()


def get_quiz_session(conn: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM quiz_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()


def set_selected_categories_for_session(
    conn: sqlite3.Connection,
    session_id: int,
    category_ids: list[int],
) -> None:
    unique_category_ids = sorted(set(category_ids))
    for category_id in unique_category_ids:
        conn.execute(
            """
            INSERT OR IGNORE INTO quiz_session_selected_categories (session_id, category_id)
            VALUES (?, ?)
            """,
            (session_id, category_id),
        )


def get_selected_categories_for_session(conn: sqlite3.Connection, session_id: int) -> list[int]:
    rows = conn.execute(
        """
        SELECT category_id
        FROM quiz_session_selected_categories
        WHERE session_id = ?
        ORDER BY category_id ASC
        """,
        (session_id,),
    ).fetchall()
    return [int(row["category_id"]) for row in rows]


def is_question_in_session(conn: sqlite3.Connection, session_id: int, question_id: int) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM quiz_session_questions
        WHERE session_id = ? AND question_id = ?
        LIMIT 1
        """,
        (session_id, question_id),
    ).fetchone()
    return row is not None


def get_user_reading_mode(conn: sqlite3.Connection, user_id: int) -> str:
    row = conn.execute(
        "SELECT reading_mode FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return "normal"
    return _normalize_reading_mode(row["reading_mode"])


def set_user_reading_mode(conn: sqlite3.Connection, user_id: int, mode: str) -> str:
    normalized_mode = _normalize_reading_mode(mode)
    conn.execute(
        "UPDATE users SET reading_mode = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (normalized_mode, user_id),
    )
    return normalized_mode


def get_owner_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    def _fetch_count(query: str) -> int:
        row = conn.execute(query).fetchone()
        if row is None:
            return 0
        return int(row[0])

    questions_by_category_rows = conn.execute(
        """
        SELECT c.name AS category_name, COUNT(q.id) AS question_count
        FROM categories c
        LEFT JOIN questions q
          ON q.category_id = c.id
         AND q.status = 'approved'
        GROUP BY c.id, c.name
        HAVING COUNT(q.id) > 0
        ORDER BY c.name ASC
        """
    ).fetchall()

    top_categories_30d_rows = conn.execute(
        """
        SELECT c.name, COUNT(DISTINCT qs.id) AS started_sessions
        FROM quiz_sessions qs
        JOIN quiz_session_questions qsq ON qsq.session_id = qs.id
        JOIN questions q ON q.id = qsq.question_id
        JOIN categories c ON c.id = q.category_id
        WHERE qs.started_at >= datetime('now', '-30 day')
        GROUP BY c.id, c.name
        ORDER BY started_sessions DESC, c.name ASC
        LIMIT 5
        """
    ).fetchall()

    return {
        "total_users": _fetch_count("SELECT COUNT(*) FROM users"),
        "new_users_24h": _fetch_count(
            "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-24 hour')"
        ),
        "new_users_7d": _fetch_count(
            "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-7 day')"
        ),
        "new_users_30d": _fetch_count(
            "SELECT COUNT(*) FROM users WHERE created_at >= datetime('now', '-30 day')"
        ),
        "active_users_24h": _fetch_count(
            "SELECT COUNT(DISTINCT user_id) FROM quiz_sessions WHERE started_at >= datetime('now', '-24 hour')"
        ),
        "active_users_7d": _fetch_count(
            "SELECT COUNT(DISTINCT user_id) FROM quiz_sessions WHERE started_at >= datetime('now', '-7 day')"
        ),
        "active_users_30d": _fetch_count(
            "SELECT COUNT(DISTINCT user_id) FROM quiz_sessions WHERE started_at >= datetime('now', '-30 day')"
        ),
        "total_quiz_sessions": _fetch_count("SELECT COUNT(*) FROM quiz_sessions"),
        "completed_quiz_sessions": _fetch_count("SELECT COUNT(*) FROM quiz_sessions WHERE status = 'finished'"),
        "in_progress_quiz_sessions": _fetch_count(
            "SELECT COUNT(*) FROM quiz_sessions WHERE status = 'in_progress'"
        ),
        "total_quiz_answers": _fetch_count("SELECT COUNT(*) FROM quiz_answers"),
        "total_approved_questions": _fetch_count("SELECT COUNT(*) FROM questions WHERE status = 'approved'"),
        "active_categories_count": _fetch_count(
            """
            SELECT COUNT(*)
            FROM categories c
            WHERE EXISTS (
                SELECT 1 FROM questions q
                WHERE q.category_id = c.id
                  AND q.status = 'approved'
            )
            """
        ),
        "questions_by_category": [
            {
                "category_name": str(row["category_name"]),
                "question_count": int(row["question_count"]),
            }
            for row in questions_by_category_rows
        ],
        "top_categories_30d": [
            {
                "category_name": str(row["name"]),
                "started_sessions": int(row["started_sessions"]),
            }
            for row in top_categories_30d_rows
        ],
    }
