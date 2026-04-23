from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv


def ensure_users_reading_mode_column(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(users)").fetchall()
    column_names = {str(column[1]) for column in columns}
    if "reading_mode" in column_names:
        return
    conn.execute(
        "ALTER TABLE users ADD COLUMN reading_mode TEXT NOT NULL DEFAULT 'normal'"
    )


def ensure_quiz_sessions_difficulty_mode_column(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(quiz_sessions)").fetchall()
    column_names = {str(column[1]) for column in columns}
    if "difficulty_mode" in column_names:
        return
    conn.execute("ALTER TABLE quiz_sessions ADD COLUMN difficulty_mode TEXT")


def resolve_db_path() -> str:
    load_dotenv()
    return os.getenv("DB_PATH", "/data/quiz.sqlite3").strip() or "/data/quiz.sqlite3"


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    schema_path = repo_root / "sql" / "schema.sql"

    if not schema_path.exists():
        print(f"[ERROR] Не найден файл схемы: {schema_path}")
        return 1

    db_path = Path(resolve_db_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        schema_sql = schema_path.read_text(encoding="utf-8")
        with sqlite3.connect(db_path) as conn:
            conn.executescript(schema_sql)
            ensure_users_reading_mode_column(conn)
            ensure_quiz_sessions_difficulty_mode_column(conn)
        print(f"[OK] База данных инициализирована: {db_path}")
        print("[OK] SQL-схема успешно применена.")
        return 0
    except sqlite3.Error as exc:
        print(f"[ERROR] Ошибка SQLite: {exc}")
        return 1
    except OSError as exc:
        print(f"[ERROR] Ошибка файловой системы: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
