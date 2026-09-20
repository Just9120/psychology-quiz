from contextlib import closing

import pytest

from app.database import PostgresConnection
from app.db import get_connection
from app.postgres_import import import_snapshot
from app.postgres_recovery import manifest, verify_user_state
from app.postgres_schema import initialize_schema, upgrade_schema, verify_schema


def test_versioned_upgrade_preserves_legacy_data_and_is_idempotent(source, pg_target):
    with closing(get_connection(str(source))) as conn, conn:
        conn.execute("DROP TABLE glossary_sessions")
        conn.execute("DELETE FROM schema_migrations WHERE version='glossary-v1'")
    import_snapshot(source, pg_target)
    with closing(get_connection(pg_target)) as conn, conn:
        assert verify_schema(conn, allow_legacy=True) == 'postgres-v1'
        before = manifest(conn)
        with pytest.raises(ValueError, match='version/drift'):
            verify_schema(conn)
        upgrade_schema(conn)
        after = manifest(conn)
        verify_user_state(before, after)
        assert after['tables']['glossary_sessions']['rows'] == 0
        assert after['sequences'] == before['sequences']
        assert verify_schema(conn) == 'postgres-v2'
        upgrade_schema(conn)
        assert manifest(conn) == after
        conn.execute("INSERT INTO glossary_sessions VALUES('session',1,'topic','Title','in_progress','{}','{}','now','now')")
        with pytest.raises(ValueError, match='empty'):
            verify_user_state(before, manifest(conn))


def test_upgrade_failure_is_atomic_and_rejects_drift(pg_target, monkeypatch):
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn, version='postgres-v1')
        conn.execute("INSERT INTO users(first_name) VALUES('kept')")
        before = manifest(conn)
    real = PostgresConnection.execute
    def fail(self, statement, parameters=None):
        if statement.startswith('UPDATE postgres_storage'):
            raise RuntimeError('injected after DDL')
        return real(self, statement, parameters)
    with monkeypatch.context() as patch:
        patch.setattr(PostgresConnection, 'execute', fail)
        with pytest.raises(RuntimeError, match='injected'):
            with closing(get_connection(pg_target)) as conn, conn:
                upgrade_schema(conn)
    with closing(get_connection(pg_target)) as conn, conn:
        assert manifest(conn) == before
        conn.execute('ALTER TABLE users ADD COLUMN unexpected TEXT')
    with closing(get_connection(pg_target)) as conn, conn:
        with pytest.raises(ValueError, match='drift'):
            upgrade_schema(conn)
        assert conn.execute("SELECT to_regclass('glossary_sessions')").fetchone()[0] is None


def test_existing_glossary_data_is_part_of_preservation_contract(bank):
    with closing(get_connection(bank)) as conn, conn:
        conn.execute("INSERT INTO glossary_sessions VALUES('session',1,'topic','Title','in_progress','{}','{}','now','now')")
        before = manifest(conn)
        conn.execute("UPDATE glossary_sessions SET state='changed'")
        with pytest.raises(ValueError, match='user state'):
            verify_user_state(before, manifest(conn))
