"""Additive owner authentication storage; init script only, no request-time DDL."""
import sqlite3

AUTH_TABLES = ("web_accounts", "web_sessions", "web_mail_tokens", "web_link_tokens", "web_auth_limits")

DDL = (
    """CREATE TABLE IF NOT EXISTS web_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        user_id INTEGER UNIQUE REFERENCES users(id),
        enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
        verified_at INTEGER NOT NULL,
        created_at INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS web_sessions (
        digest TEXT PRIMARY KEY,
        account_id INTEGER NOT NULL REFERENCES web_accounts(id) ON DELETE CASCADE,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        last_seen_at INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS web_mail_tokens (
        digest TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        purpose TEXT NOT NULL CHECK(purpose IN ('register','recover')),
        account_id INTEGER REFERENCES web_accounts(id) ON DELETE CASCADE,
        expires_at INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS web_link_tokens (
        digest TEXT PRIMARY KEY,
        account_id INTEGER NOT NULL REFERENCES web_accounts(id) ON DELETE CASCADE,
        session_digest TEXT NOT NULL UNIQUE REFERENCES web_sessions(digest) ON DELETE CASCADE,
        proposed_user_id INTEGER REFERENCES users(id),
        telegram_confirmed INTEGER NOT NULL DEFAULT 0 CHECK(telegram_confirmed IN (0,1)),
        expires_at INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS web_auth_limits (
        bucket TEXT PRIMARY KEY, started_at INTEGER NOT NULL, count INTEGER NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_web_sessions_account ON web_sessions(account_id)",
    "CREATE INDEX IF NOT EXISTS idx_web_mail_account ON web_mail_tokens(account_id)",
    "CREATE INDEX IF NOT EXISTS idx_web_link_account ON web_link_tokens(account_id)",
)


def migrate_auth_schema(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        raise RuntimeError("Auth migration requires a separate transaction")
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        for statement in DDL:
            conn.execute(statement)
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES ('auth-v1')")
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("Auth migration requires valid foreign keys")
