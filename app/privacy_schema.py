"""Additive SQLite storage for one-use Telegram learning-data deletion challenges."""

VERSION = "privacy-v1"


def migrate_privacy_schema(conn) -> None:
    marker = conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (VERSION,)).fetchone()
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    present = "user_data_deletion_challenges" in tables
    columns = ({row[1] for row in conn.execute("PRAGMA table_info(user_data_deletion_challenges)")}
               if present else set())
    expected = {"user_id", "token_digest", "expires_at"}
    if marker:
        if columns != expected:
            raise ValueError("Privacy schema is incomplete")
        return
    if present:
        raise ValueError("Unknown partial privacy schema; refusing adoption")
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    conn.execute("""CREATE TABLE user_data_deletion_challenges (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        token_digest TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )""")
    conn.execute("INSERT INTO schema_migrations(version) VALUES(?)", (VERSION,))
