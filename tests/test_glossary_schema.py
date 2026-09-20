from contextlib import closing
import sqlite3

import pytest

from app.glossary_schema import migrate_glossary_schema
from app.identity_schema import migrate_identity_schema
from tests.test_attempt_content import bank


def test_sqlite_upgrade_replay_and_unknown_schema(bank):
    with closing(sqlite3.connect(bank)) as conn, conn:
        migrate_identity_schema(conn)
        before = list(conn.execute('SELECT * FROM users'))
        migrate_glossary_schema(conn)
        migrate_glossary_schema(conn)
        assert list(conn.execute('SELECT * FROM users')) == before
        conn.execute('ALTER TABLE glossary_sessions ADD COLUMN unexpected TEXT')
        with pytest.raises(ValueError, match='Unknown'):
            migrate_glossary_schema(conn)


def test_sqlite_failed_transaction_leaves_no_partial_migration(bank):
    with closing(sqlite3.connect(bank)) as conn:
        migrate_identity_schema(conn)
        with pytest.raises(RuntimeError):
            with conn:
                migrate_glossary_schema(conn)
                raise RuntimeError('injected')
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='glossary_sessions'").fetchone() is None
        assert conn.execute("SELECT 1 FROM schema_migrations WHERE version='glossary-v1'").fetchone() is None
