"""Additive SQLite quiz schema preparation shared by startup and init.

PostgreSQL uses versioned migrations in postgres_schema instead. These helpers
retain the legacy reading table for import/recovery; they do not rewrite data or
manage transactions. app.db re-exports them for existing callers.
"""
from __future__ import annotations

from app.database import Connection


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



def ensure_users_reading_mode_column(conn: Connection) -> None:
    columns = conn.execute("PRAGMA table_info(users)").fetchall()
    # PRAGMA's name is column 1 for both sqlite3.Row runtime and tuple init connections.
    column_names = {str(column[1]) for column in columns}
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
    column_names = {str(column[1]) for column in columns}
    if "difficulty_mode" in column_names:
        return

    conn.execute("ALTER TABLE quiz_sessions ADD COLUMN difficulty_mode TEXT")

