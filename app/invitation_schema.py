"""Additive storage for invitation offers and single-use PWA invitations."""
from __future__ import annotations

VERSION = "invitations-v1"

DDL = (
    """CREATE TABLE pwa_invitations (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        promo_shown_at INTEGER,
        token_digest TEXT UNIQUE,
        expires_at INTEGER,
        consumed_at INTEGER,
        invited_email TEXT,
        account_id INTEGER UNIQUE REFERENCES web_accounts(id) ON DELETE SET NULL,
        CHECK ((token_digest IS NULL AND (expires_at IS NULL OR consumed_at IS NOT NULL))
            OR (token_digest IS NOT NULL AND expires_at IS NOT NULL AND consumed_at IS NULL))
    )""",
    "CREATE INDEX pwa_invitations_expiry ON pwa_invitations(expires_at)",
    "CREATE UNIQUE INDEX pwa_invitations_email ON pwa_invitations(invited_email) WHERE invited_email IS NOT NULL",
)


def migrate_invitation_schema(conn) -> None:
    marker = conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (VERSION,)).fetchone()
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    present = ("pwa_invitations" in tables, "pwa_invitations_expiry" in indexes,
               "pwa_invitations_email" in indexes)
    if marker:
        if not all(present):
            raise ValueError("Invitation schema is incomplete")
        return
    if any(present):
        raise ValueError("Unknown partial invitation schema; refusing adoption")
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    for statement in DDL:
        conn.execute(statement)
    conn.execute("INSERT INTO schema_migrations(version) VALUES(?)", (VERSION,))
