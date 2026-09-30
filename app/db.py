from __future__ import annotations

from pathlib import Path
import json
import random
from typing import Any

from app.attempt_content import capture_question, ensure_attempt_snapshots, get_attempt_content
from app.case_content import case_error
from app.database import Connection, Row, begin_write, connect_database, is_postgres, timestamp_sql
from app.quiz_overlap import balanced_diverse_first, diverse_first
from app.owner_stats import OWNER_STATS_PERIODS, get_owner_stats, get_owner_period_stats
from app.quiz_schema import (
    ensure_performance_indexes, ensure_users_reading_mode_column,
    ensure_quiz_session_selected_categories_table,
    ensure_user_literature_progress_table, ensure_quiz_sessions_difficulty_mode_column,
)


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


VALID_READING_MODES = {"normal", "bionic"}
VALID_DIFFICULTY_MODES = {"easy", "medium", "hard"}


USER_LITERATURE_READING_STATUSES = {"not_started", "in_progress", "read", "revisit", "skipped"}


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
        SELECT q.id,q.external_id
        FROM questions q
        WHERE {where_clause}
    """

    rows = conn.execute(query, params).fetchall()
    # Fetching the full candidate set is required for overlap-aware selection.
    # A linear shuffle avoids sorting that same set inside the database.
    random.shuffle(rows)
    return diverse_first([(int(row["id"]), str(row["external_id"])) for row in rows], limit)


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
        SELECT q.id,q.external_id
        FROM questions q
        INNER JOIN categories c ON c.id = q.category_id
        WHERE {where_clause}
          AND EXISTS (
              SELECT 1
              FROM questions q2
              WHERE q2.category_id = c.id
                AND q2.status = 'approved'
          )
    """

    rows = conn.execute(query, params).fetchall()
    # Fetching the full candidate set is required for overlap-aware selection.
    # A linear shuffle avoids sorting that same set inside the database.
    random.shuffle(rows)
    return diverse_first([(int(row["id"]), str(row["external_id"])) for row in rows], limit)


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

    # Shuffle inside each selected topic, then deal one question per topic in
    # rounds. A global random LIMIT can hide smaller selected topics entirely.
    rows = conn.execute(f"""
        SELECT q.id, q.category_id, q.external_id
        FROM questions q
        WHERE {where_clause}
    """, params).fetchall()
    random.shuffle(rows)
    order = list(dict.fromkeys(category_ids))
    random.shuffle(order)
    buckets: dict[int, list[tuple[int, str]]] = {category_id: [] for category_id in order}
    for row in rows:
        buckets[int(row["category_id"])].append((int(row["id"]), str(row["external_id"])))
    return balanced_diverse_first(buckets, order, limit)


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
    question_text = content["question_text"]
    explanation = content["explanation"]
    if content.get("kind") == "case":
        question_text = content["case"]["situation"] + "\n\n" + question_text
        rationales = content["case"]["option_rationales"]
        explanation = (explanation or "") + "\n\nРазбор вариантов:\n" + "\n".join(
            f"{index + 1}. {rationale}" for index, rationale in enumerate(rationales))
        explanation += "\n\n" + content["case"]["ambiguity"]
    return {**dict(row), "question_text": question_text, "explanation": explanation}


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
    if option_row is None and selected_option_index != -1:
        raise ValueError("Invalid attempt question/option")
    is_correct = int(option_row["is_correct"]) if option_row is not None else 0

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
