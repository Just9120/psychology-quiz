from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def get_connection(db_path: str) -> sqlite3.Connection:
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db_connection(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("SELECT 1;")
    finally:
        conn.close()


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
    conn.execute(
        """
        INSERT INTO users (telegram_user_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            updated_at = CURRENT_TIMESTAMP
        """,
        (telegram_user_id, username, first_name, last_name),
    )

    row = conn.execute(
        "SELECT * FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Не удалось создать или загрузить пользователя")
    return row


def start_quiz_session(conn: sqlite3.Connection, user_id: int, category_id: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO quiz_sessions (user_id, category_id, status)
        VALUES (?, ?, 'in_progress')
        """,
        (user_id, category_id),
    )
    return int(cursor.lastrowid)


def get_random_approved_question_by_category(
    conn: sqlite3.Connection,
    category_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT q.id, q.external_id, q.question_text, q.explanation
        FROM questions q
        WHERE q.category_id = ? AND q.status = 'approved'
        ORDER BY RANDOM()
        LIMIT 1
        """,
        (category_id,),
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
    option_row = conn.execute(
        """
        SELECT is_correct
        FROM question_options
        WHERE question_id = ? AND option_index = ?
        """,
        (question_id, selected_option_index),
    ).fetchone()
    is_correct = int(option_row["is_correct"]) if option_row else 0

    conn.execute(
        """
        INSERT INTO quiz_answers (session_id, question_id, selected_option_index, is_correct)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, question_id, selected_option_index, is_correct),
    )

    return {"is_correct": is_correct}


def finalize_quiz_session(conn: sqlite3.Connection, session_id: int) -> sqlite3.Row | None:
    stats = conn.execute(
        """
        SELECT COALESCE(SUM(is_correct), 0) AS score, COUNT(*) AS total_questions
        FROM quiz_answers
        WHERE session_id = ?
        """,
        (session_id,),
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
