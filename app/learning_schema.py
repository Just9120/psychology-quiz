"""Additive SQLite learning-state migration, run by explicit initialization."""
from __future__ import annotations

VERSION = "learning-v1"

DDL = (
    "ALTER TABLE questions ADD COLUMN kind TEXT NOT NULL DEFAULT 'theory' CHECK(kind IN ('theory','glossary','case'))",
    "ALTER TABLE questions ADD COLUMN case_content TEXT",
    """CREATE TABLE user_learning_goals (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        goal_kind TEXT NOT NULL CHECK(goal_kind IN ('study','review','reading')),
        weekly_target INTEGER NOT NULL CHECK(weekly_target > 0),
        updated_at TEXT NOT NULL,
        PRIMARY KEY(user_id,goal_kind)
    )""",
    """CREATE TABLE user_achievements (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        achievement_kind TEXT NOT NULL,
        evidence_key TEXT NOT NULL,
        earned_at TEXT NOT NULL,
        PRIMARY KEY(user_id,achievement_kind,evidence_key)
    )""",
    "CREATE INDEX user_achievements_owner ON user_achievements(user_id,earned_at)",
    """CREATE TABLE user_review_events (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        answer_kind TEXT NOT NULL CHECK(answer_kind IN ('quiz','glossary')),
        answer_key TEXT NOT NULL,
        answered_at TEXT NOT NULL,
        PRIMARY KEY(user_id,answer_kind,answer_key)
    )""",
    "CREATE INDEX user_review_events_owner_time ON user_review_events(user_id,answered_at)",
    """CREATE TABLE user_review_sessions (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        session_kind TEXT NOT NULL CHECK(session_kind IN ('quiz','glossary')),
        session_key TEXT NOT NULL,
        started_at TEXT NOT NULL,
        PRIMARY KEY(session_kind,session_key)
    )""",
    "CREATE INDEX user_review_sessions_owner ON user_review_sessions(user_id,session_kind)",
)


def migrate_learning_schema(conn) -> None:
    marker = conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (VERSION,)).fetchone()
    columns = {table: {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
               for table in ("questions",)}
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    present = ("kind" in columns["questions"], "case_content" in columns["questions"],
               "user_learning_goals" in tables, "user_achievements" in tables,
               "user_achievements_owner" in indexes, "user_review_events" in tables,
               "user_review_events_owner_time" in indexes, "user_review_sessions" in tables,
               "user_review_sessions_owner" in indexes)
    if marker:
        if not all(present):
            raise ValueError("Learning schema is incomplete")
        return
    if any(present):
        raise ValueError("Unknown partial learning schema; refusing adoption")
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    for statement in DDL:
        conn.execute(statement)
    conn.execute("INSERT INTO schema_migrations(version) VALUES(?)", (VERSION,))
