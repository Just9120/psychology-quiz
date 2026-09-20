"""Explicit additive SQLite glossary migration; runtime never creates tables."""
from pathlib import Path

VERSION = "glossary-v1"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "glossary-v1.sql"


def migrate_glossary_schema(conn):
    statements = [part.strip() for part in SCHEMA_PATH.read_text(encoding="utf-8").split(';') if part.strip()]
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='glossary_sessions'").fetchone()
    marker = conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (VERSION,)).fetchone()
    if exists:
        actual = [row[0] for row in conn.execute("""SELECT sql FROM sqlite_master
            WHERE tbl_name='glossary_sessions' AND sql IS NOT NULL ORDER BY type DESC,name""")]
        normalize = lambda value: ' '.join(value.split()).lower()
        if not marker or sorted(map(normalize, actual)) != sorted(map(normalize, statements)):
            raise ValueError("Unknown glossary schema; refusing adoption")
        return
    if marker:
        raise ValueError("Glossary schema is incomplete")
    # execute rather than executescript: preserve the caller's transaction.
    conn.execute("BEGIN IMMEDIATE") if not conn.in_transaction else None
    for statement in statements:
        conn.execute(statement)
    conn.execute("INSERT INTO schema_migrations(version) VALUES(?)", (VERSION,))
