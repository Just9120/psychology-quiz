from contextlib import closing

import pytest

from app.db import get_connection
from app.postgres_schema import initialize_schema, upgrade_schema, verify_schema
from app.postgres_recovery import manifest, verify_user_state
from app.reading_schema import migrate_reading_schema
from tests.test_reading_work_migration import ITEMS


def seed(conn, second_time):
    conn.execute("INSERT INTO users(id,first_name) VALUES(1,'Synthetic')")
    for item, status, time in [('one', 'read', '2026-09-01T12:00:00Z'), ('two', 'skipped', second_time)]:
        conn.execute("""INSERT INTO user_literature_progress
            (user_id,literature_id,reading_status,progress_percent,updated_at,private_note)
            VALUES(1,?,?,37,?,'private history')""", (item,status,time))


def test_postgres_reading_migration_preserves_history_and_is_idempotent(pg_target, monkeypatch):
    monkeypatch.setattr("app.literature.load_literature_items", lambda: ITEMS)
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn, version="postgres-v7")
        seed(conn, '2026-09-29T12:00:00Z')
        before = [tuple(row) for row in conn.execute('SELECT * FROM user_literature_progress ORDER BY id')]
        before_manifest = manifest(conn)
        upgrade_schema(conn)
        assert verify_schema(conn) == 'postgres-v9'
        verify_user_state(before_manifest, manifest(conn))
        assert [tuple(row) for row in conn.execute('SELECT * FROM user_literature_progress ORDER BY id')] == before
        assert conn.execute('SELECT reading_status FROM user_literature_work_progress').fetchone()[0] == 'deferred'
        conn.execute("UPDATE user_literature_work_progress SET reading_status='in_progress'")
        upgraded = manifest(conn)
        upgrade_schema(conn)
        assert manifest(conn) == upgraded
        assert conn.execute('SELECT reading_status FROM user_literature_work_progress').fetchone()[0] == 'in_progress'


def test_postgres_ambiguous_reading_migration_does_not_create_table(pg_target, monkeypatch):
    monkeypatch.setattr("app.literature.load_literature_items", lambda: ITEMS)
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn, version="postgres-v7")
        seed(conn, '2026-09-01T12:00:00Z')
        with pytest.raises(ValueError, match='conflict'):
            upgrade_schema(conn)
        assert conn.execute("SELECT to_regclass('user_literature_work_progress')").fetchone()[0] is None
        assert conn.execute('SELECT COUNT(*) FROM user_literature_progress').fetchone()[0] == 2
        assert verify_schema(conn, allow_legacy=True) == 'postgres-v7'


def test_failed_postgres_reading_upgrade_rolls_back_table_rows_and_marker(pg_target, monkeypatch):
    from app.database import PostgresConnection
    monkeypatch.setattr("app.literature.load_literature_items", lambda: ITEMS)
    with closing(get_connection(pg_target)) as conn:
        with conn:
            initialize_schema(conn, version='postgres-v7')
            seed(conn, '2026-09-29T12:00:00Z')
            before = manifest(conn)
        real = PostgresConnection.execute
        def fail(self, statement, parameters=None):
            if statement.startswith('UPDATE postgres_storage'):
                raise RuntimeError('injected after reading transfer')
            return real(self, statement, parameters)
        monkeypatch.setattr(PostgresConnection, 'execute', fail)
        with pytest.raises(RuntimeError), conn:
            upgrade_schema(conn)
        assert verify_schema(conn, allow_legacy=True) == 'postgres-v7'
        assert manifest(conn) == before
