"""Additive SQLite association of reviewed homework tests with quiz attempts."""

VERSION = "homework-v1"


def migrate_homework_schema(conn):
    marker = conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (VERSION,)).fetchone()
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    present = ("homework_attempts" in tables, "homework_attempts_assignment" in indexes)
    if marker:
        if not all(present):
            raise ValueError("Homework schema is incomplete")
        return
    if any(present):
        raise ValueError("Unknown partial homework schema; refusing adoption")
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    conn.execute("""CREATE TABLE homework_attempts (
        session_id INTEGER PRIMARY KEY REFERENCES quiz_sessions(id) ON DELETE CASCADE,
        assignment_id TEXT NOT NULL CHECK (length(trim(assignment_id)) > 0)
    )""")
    conn.execute("CREATE INDEX homework_attempts_assignment ON homework_attempts(assignment_id)")
    conn.execute("INSERT INTO schema_migrations(version) VALUES(?)", (VERSION,))
