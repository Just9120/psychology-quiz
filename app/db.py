from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
from typing import Any

from app.attempt_content import capture_question, ensure_attempt_snapshots, get_attempt_content
from app.case_content import case_error
from app.database import Connection, Row, begin_write, connect_database, is_postgres, timestamp_sql


SESSION_QUESTION_LIMIT = 10


def get_connection(db_path: str) -> Connection:
    return connect_database(db_path)


def init_db_connection(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        if is_postgres(conn):
            from app.postgres_schema import verify_schema
            verify_schema(conn)
            return
        if Path(db_path) != Path(":memory:"):
            conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("SELECT 1;")
        ensure_users_reading_mode_column(conn)
        ensure_quiz_sessions_difficulty_mode_column(conn)
        ensure_quiz_session_selected_categories_table(conn)
        ensure_user_literature_progress_table(conn)
        ensure_performance_indexes(conn)
        ensure_attempt_snapshots(conn)
        conn.commit()
    finally:
        conn.close()


def ensure_performance_indexes(conn: Connection) -> None:
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


def ensure_users_reading_mode_column(conn: Connection) -> None:
    columns = conn.execute("PRAGMA table_info(users)").fetchall()
    column_names = {str(column["name"]) for column in columns}
    if "reading_mode" in column_names:
        return

    conn.execute(
        "ALTER TABLE users ADD COLUMN reading_mode TEXT NOT NULL DEFAULT 'normal'"
    )


def ensure_quiz_session_selected_categories_table(conn: Connection) -> None:
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


USER_LITERATURE_READING_STATUSES = {"not_started", "in_progress", "read", "revisit", "skipped"}


def ensure_user_literature_progress_table(conn: Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_literature_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            literature_id TEXT NOT NULL CHECK (length(trim(literature_id)) > 0),
            reading_status TEXT NOT NULL CHECK (
                reading_status IN ('not_started', 'in_progress', 'read', 'revisit', 'skipped')
            ),
            progress_percent INTEGER CHECK (
                progress_percent IS NULL OR (progress_percent >= 0 AND progress_percent <= 100)
            ),
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL,
            last_opened_at TEXT,
            private_note TEXT,
            remind_at TEXT,
            UNIQUE (user_id, literature_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_literature_progress_user_id "
        "ON user_literature_progress(user_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_literature_progress_reading_status "
        "ON user_literature_progress(reading_status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_literature_progress_user_updated "
        "ON user_literature_progress(user_id, updated_at)"
    )


def ensure_quiz_sessions_difficulty_mode_column(conn: Connection) -> None:
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


def ensure_categories(conn: Connection, category_names: list[str]) -> dict[str, int]:
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


def upsert_approved_questions(
    conn: Connection, questions: list[dict[str, Any]], *, authoritative: bool = False
) -> dict[str, int]:
    begin_write(conn, "content")
    # A partial import may update supplied IDs, but may not retire unspecified IDs.
    ids = [str(item["id"]).strip() for item in questions]
    if any(not external_id for external_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("Question IDs must be non-empty and unique")
    ensure_attempt_snapshots(conn)  # Preserve legacy attempts BEFORE mutating live content.
    for item in questions:
        if item.get("status") != "approved":
            conn.execute(
                f"UPDATE questions SET status=?, updated_at={timestamp_sql(conn)} WHERE external_id=? AND status IS DISTINCT FROM ?",
                (str(item.get("status") or "retired"), str(item["id"]).strip(), str(item.get("status") or "retired")),
            )
    if authoritative:
        # Avoid SQL parameter limits on a growing bank; no deletion of history rows.
        supplied = set(ids)
        for row in conn.execute("SELECT external_id FROM questions WHERE status != 'retired'").fetchall():
            if row[0] not in supplied:
                conn.execute(f"UPDATE questions SET status='retired', updated_at={timestamp_sql(conn)} WHERE external_id=?", (row[0],))
    approved = [item for item in questions if item.get("status") == "approved"]
    categories = sorted({str(item["category"]).strip() for item in approved if item.get("category")})
    category_ids = ensure_categories(conn, categories)

    inserted_or_updated = 0

    for item in approved:
        invalid_case = case_error(item)
        if invalid_case:
            raise ValueError(invalid_case)
        category_name = str(item["category"]).strip()
        category_id = category_ids.get(category_name)
        if not category_id:
            continue

        external_id = str(item["id"]).strip()
        source_ref = item.get("source_ref")
        difficulty = str(item.get("difficulty", "easy")).strip() or "easy"
        question_text = str(item["question"]).strip()
        explanation = item.get("explanation")
        kind = item.get("kind", "theory")
        case_content = (json.dumps(item["case"], ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")) if kind == "case" else None)

        conn.execute(
            f"""
            INSERT INTO questions (
                external_id, category_id, source_ref, difficulty, status, question_text, explanation, kind, case_content
            )
            VALUES (?, ?, ?, ?, 'approved', ?, ?, ?, ?)
            ON CONFLICT(external_id) DO UPDATE SET
                category_id = excluded.category_id,
                source_ref = excluded.source_ref,
                difficulty = excluded.difficulty,
                status = excluded.status,
                question_text = excluded.question_text,
                explanation = excluded.explanation,
                kind = excluded.kind,
                case_content = excluded.case_content,
                updated_at = {timestamp_sql(conn)}
            """,
            (external_id, category_id, source_ref, difficulty, question_text, explanation, kind, case_content),
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


def get_active_categories(conn: Connection) -> list[Row]:
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
    conn: Connection,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> Row:
    row = conn.execute(
        "SELECT * FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,),
    ).fetchone()

    if row is None:
        conn.execute(
            """
            INSERT INTO users (telegram_user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?) ON CONFLICT(telegram_user_id) DO NOTHING
            """,
            (telegram_user_id, username, first_name, last_name),
        )

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
        f"""
        UPDATE users
        SET username = ?,
            first_name = ?,
            last_name = ?,
            updated_at = {timestamp_sql(conn)}
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
    conn: Connection,
    user_id: int,
    category_id: int | None,
    difficulty_mode: str | None = None,
) -> int:
    begin_write(conn, f"actor:{user_id}")
    normalized_difficulty_mode = _normalize_difficulty_mode(difficulty_mode)
    cursor = conn.execute(
        """
        INSERT INTO quiz_sessions (user_id, category_id, status, difficulty_mode)
        VALUES (?, ?, 'in_progress', ?) RETURNING id
        """,
        (user_id, category_id, normalized_difficulty_mode),
    )
    return int(cursor.fetchone()[0])


def abandon_in_progress_sessions_for_user(conn: Connection, user_id: int) -> int:
    begin_write(conn, f"actor:{user_id}")
    cursor = conn.execute(
        f"""
        UPDATE quiz_sessions
        SET status = 'abandoned',
            finished_at = {timestamp_sql(conn)}
        WHERE user_id = ?
          AND status = 'in_progress'
        """,
        (user_id,),
    )
    return int(cursor.rowcount or 0)


def select_random_approved_question_ids_by_category(
    conn: Connection,
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
    conn: Connection,
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
    conn: Connection,
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


def store_session_questions(conn: Connection, session_id: int, question_ids: list[int]) -> None:
    # Both question and option reads must see the same committed edition.
    begin_write(conn, "content")
    for order_index, question_id in enumerate(question_ids, start=1):
        serving = conn.execute("SELECT 1 FROM questions WHERE id=? AND status='approved'", (question_id,)).fetchone()
        if serving is None:
            raise ValueError("Only approved questions can enter a new attempt")
        snapshot, digest = capture_question(conn, question_id)
        conn.execute(
            """
            INSERT INTO quiz_session_questions
                (session_id, question_id, order_index, content_snapshot, content_sha256, snapshot_provenance)
            VALUES (?, ?, ?, ?, ?, 'captured')
            """,
            (session_id, question_id, order_index, snapshot, digest),
        )


def get_session_question_count(conn: Connection, session_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS total_questions
        FROM quiz_session_questions
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    return int(row["total_questions"]) if row else 0


def get_current_unanswered_question(conn: Connection, session_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT
            sq.question_id,
            sq.order_index,
            (SELECT COUNT(*) FROM quiz_session_questions WHERE session_id = sq.session_id) AS total_questions
        FROM quiz_session_questions sq
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
    if row is None:
        return None
    content = get_attempt_content(conn, session_id, int(row["question_id"]))
    return {**dict(row), "question_text": content["question_text"], "explanation": content["explanation"]}


def get_question_options(conn: Connection, question_id: int, *, session_id: int) -> list[dict]:
    content = get_attempt_content(conn, session_id, question_id)
    return content["options"] if content is not None else []


def save_quiz_answer(
    conn: Connection,
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

    option_row = next((option for option in get_question_options(conn, question_id, session_id=session_id)
                       if option["option_index"] == selected_option_index), None)
    if option_row is None:
        raise ValueError("Invalid attempt question/option")
    is_correct = int(option_row["is_correct"])

    inserted = conn.execute(
        """
        INSERT INTO quiz_answers (session_id, question_id, selected_option_index, is_correct)
        VALUES (?, ?, ?, ?) ON CONFLICT(session_id, question_id) DO NOTHING
        """,
        (session_id, question_id, selected_option_index, is_correct),
    )
    if not inserted.rowcount:
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
        raise RuntimeError("Conflicting answer is missing")

    return {"is_correct": is_correct, "already_answered": 0}


def get_answered_questions_count(conn: Connection, session_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS answered_questions
        FROM quiz_answers
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    return int(row["answered_questions"]) if row else 0


def finalize_quiz_session(conn: Connection, session_id: int) -> Row | None:
    session = get_quiz_session(conn, session_id)
    if session is None:
        return None
    begin_write(conn, f"actor:{session['user_id']}")
    session = get_quiz_session(conn, session_id)
    if session is None or session['status'] == 'abandoned':
        return None
    if session['status'] == 'finished':
        return session
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
        f"""
        UPDATE quiz_sessions
        SET score = ?,
            total_questions = ?,
            finished_at = {timestamp_sql(conn)},
            status = 'finished'
        WHERE id = ?
        """,
        (score, total_questions, session_id),
    )

    return conn.execute(
        "SELECT * FROM quiz_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()


def get_quiz_session(conn: Connection, session_id: int) -> Row | None:
    return conn.execute(
        "SELECT * FROM quiz_sessions WHERE id = ?",
        (session_id,),
    ).fetchone()


def set_selected_categories_for_session(
    conn: Connection,
    session_id: int,
    category_ids: list[int],
) -> None:
    unique_category_ids = sorted(set(category_ids))
    for category_id in unique_category_ids:
        conn.execute(
            """
            INSERT INTO quiz_session_selected_categories (session_id, category_id)
            VALUES (?, ?) ON CONFLICT(session_id, category_id) DO NOTHING
            """,
            (session_id, category_id),
        )


def get_selected_categories_for_session(conn: Connection, session_id: int) -> list[int]:
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


def is_question_in_session(conn: Connection, session_id: int, question_id: int) -> bool:
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


def get_user_reading_mode(conn: Connection, user_id: int) -> str:
    row = conn.execute(
        "SELECT reading_mode FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return "normal"
    return _normalize_reading_mode(row["reading_mode"])


def set_user_reading_mode(conn: Connection, user_id: int, mode: str) -> str:
    normalized_mode = _normalize_reading_mode(mode)
    conn.execute(
        f"UPDATE users SET reading_mode = ?, updated_at = {timestamp_sql(conn)} WHERE id = ?",
        (normalized_mode, user_id),
    )
    return normalized_mode


def get_owner_stats(conn: Connection) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoffs = {days: (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S") for days in (1, 7, 30)}

    def _fetch_count(query: str, parameters=()) -> int:
        row = conn.execute(query, parameters).fetchone()
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
        WHERE qs.started_at >= ?
        GROUP BY c.id, c.name
        ORDER BY started_sessions DESC, c.name ASC
        LIMIT 5
        """, (cutoffs[30],)
    ).fetchall()

    return {
        "total_users": _fetch_count("SELECT COUNT(*) FROM users"),
        "new_users_24h": _fetch_count(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (cutoffs[1],)
        ),
        "new_users_7d": _fetch_count(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (cutoffs[7],)
        ),
        "new_users_30d": _fetch_count(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (cutoffs[30],)
        ),
        "active_users_24h": _fetch_count(
            "SELECT COUNT(DISTINCT user_id) FROM quiz_sessions WHERE started_at >= ?", (cutoffs[1],)
        ),
        "active_users_7d": _fetch_count(
            "SELECT COUNT(DISTINCT user_id) FROM quiz_sessions WHERE started_at >= ?", (cutoffs[7],)
        ),
        "active_users_30d": _fetch_count(
            "SELECT COUNT(DISTINCT user_id) FROM quiz_sessions WHERE started_at >= ?", (cutoffs[30],)
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
