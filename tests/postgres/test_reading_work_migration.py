from contextlib import closing

import pytest

from app.db import get_connection
from app.postgres_schema import initialize_schema
from app.reading_schema import migrate_reading_schema
from tests.test_reading_work_migration import ITEMS


def seed(conn, second_time):
    conn.execute("INSERT INTO users(id,first_name) VALUES(1,'Synthetic')")
    for item, status, time in [('one', 'read', '2026-09-01T12:00:00Z'), ('two', 'skipped', second_time)]:
        conn.execute("""INSERT INTO user_literature_progress
            (user_id,literature_id,reading_status,progress_percent,updated_at,private_note)
            VALUES(1,?,?,37,?,'private history')""", (item,status,time))


def test_postgres_reading_migration_preserves_history_and_is_idempotent(pg_target):
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn, version="postgres-v7")
        seed(conn, '2026-09-29T12:00:00Z')
        before = [tuple(row) for row in conn.execute('SELECT * FROM user_literature_progress ORDER BY id')]
        assert migrate_reading_schema(conn, ITEMS)['work_rows'] == 1
        assert [tuple(row) for row in conn.execute('SELECT * FROM user_literature_progress ORDER BY id')] == before
        assert conn.execute('SELECT reading_status FROM user_literature_work_progress').fetchone()[0] == 'deferred'
        conn.execute("UPDATE user_literature_work_progress SET reading_status='in_progress'")
        assert migrate_reading_schema(conn, ITEMS)['already_applied']
        assert conn.execute('SELECT reading_status FROM user_literature_work_progress').fetchone()[0] == 'in_progress'


def test_postgres_ambiguous_reading_migration_does_not_create_table(pg_target):
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn, version="postgres-v7")
        seed(conn, '2026-09-01T12:00:00Z')
        with pytest.raises(ValueError, match='conflict'):
            migrate_reading_schema(conn, ITEMS)
        assert conn.execute("SELECT to_regclass('user_literature_work_progress')").fetchone()[0] is None
        assert conn.execute('SELECT COUNT(*) FROM user_literature_progress').fetchone()[0] == 2
