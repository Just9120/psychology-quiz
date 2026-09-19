"""Versioned learning-identity migration, run by init_db with writers stopped.

Request handlers never rebuild tables. Existing IDs and every user field survive;
nullable Telegram identity permits independent web users without invented IDs.
"""
from __future__ import annotations

import re
import sqlite3

VERSION = "identity-v1"


def migrate_identity_schema(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        raise RuntimeError("Identity migration requires a separate transaction")
    foreign_keys = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Identity migration requires valid foreign keys")
        columns = conn.execute("PRAGMA table_info(users)").fetchall()
        telegram = next((row for row in columns if row[1] == "telegram_user_id"), None)
        if telegram is None:
            raise RuntimeError("Missing learning identity schema")
        if telegram[3]:
            _rebuild_users(conn, columns)
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)", (VERSION,))
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Identity migration broke foreign keys")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA foreign_keys={foreign_keys}")


def _rebuild_users(conn: sqlite3.Connection, columns: list) -> None:
    original = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0]
    # Only the known legacy declaration is rewritten; unfamiliar schema fails closed.
    revised, count = re.subn(r"\btelegram_user_id\s+INTEGER\s+NOT\s+NULL\b", "telegram_user_id INTEGER", original, flags=re.I)
    revised, renamed = re.subn(r"^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`\[]?users[\"`\]]?", "CREATE TABLE users_identity_v1", revised, count=1, flags=re.I)
    if count != 1 or renamed != 1:
        raise RuntimeError("Unsupported legacy identity declaration")
    definitions = [row[0] for row in conn.execute("""SELECT sql FROM sqlite_master
        WHERE tbl_name='users' AND type IN ('index','trigger') AND sql IS NOT NULL""")]
    sequence = conn.execute("SELECT seq FROM sqlite_sequence WHERE name='users'").fetchone()
    fields = ",".join('"' + row[1].replace('"', '""') + '"' for row in columns)
    conn.execute(revised)
    conn.execute(f"INSERT INTO users_identity_v1 ({fields}) SELECT {fields} FROM users")
    # Verify exact values both ways before replacing the old table.
    for left, right in (("users", "users_identity_v1"), ("users_identity_v1", "users")):
        if conn.execute(f"SELECT {fields} FROM {left} EXCEPT SELECT {fields} FROM {right}").fetchone():
            raise RuntimeError("Identity migration did not preserve user fields")
    conn.execute("DROP TABLE users")
    conn.execute("ALTER TABLE users_identity_v1 RENAME TO users")
    if sequence is not None:
        conn.execute("UPDATE sqlite_sequence SET seq=max(seq, ?) WHERE name='users'", (sequence[0],))
    for statement in definitions:
        conn.execute(statement)
