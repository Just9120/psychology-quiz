import sqlite3

import pytest

from app.reading_schema import migrate_reading_schema, plan_legacy_reading

ITEMS = [{"id": "one", "work_id": "book"}, {"id": "two", "work_id": "book"}]


def legacy(user, item, status, time):
    return {"user_id": user, "literature_id": item, "reading_status": status,
            "progress_percent": 37, "started_at": "2026-01-01T00:00:00Z",
            "completed_at": None, "updated_at": time, "last_opened_at": time,
            "private_note": "private retained history", "remind_at": "later"}


def make_connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO users VALUES(1)")
    conn.execute("INSERT INTO users VALUES(2)")
    conn.execute("CREATE TABLE schema_migrations(version TEXT PRIMARY KEY)")
    conn.execute("""CREATE TABLE user_literature_progress (
        user_id INTEGER, literature_id TEXT, reading_status TEXT,
        progress_percent INTEGER, started_at TEXT, completed_at TEXT,
        updated_at TEXT, last_opened_at TEXT, private_note TEXT, remind_at TEXT)""")
    conn.commit()
    return conn


def add(conn, row):
    fields = tuple(row)
    conn.execute(f"INSERT INTO user_literature_progress ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                 tuple(row.values()))


def test_migration_preserves_every_legacy_field_and_actor_and_never_replays():
    with make_connection() as conn:
        add(conn, legacy(1, "one", "in_progress", "2026-09-01T12:00:00Z"))
        add(conn, legacy(1, "two", "revisit", "2026-09-29T12:00:00Z"))
        add(conn, legacy(2, "one", "read", "2026-09-29 12:00:00"))
        add(conn, legacy(2, "unknown", "skipped", "2026-09-29T12:00:00Z"))
        before = [tuple(row) for row in conn.execute("SELECT * FROM user_literature_progress")]
        result = migrate_reading_schema(conn, ITEMS)
        assert result == {"already_applied": False, "legacy_rows_preserved": 4,
                          "work_rows": 2, "unknown_association_rows_preserved": 1}
        assert [tuple(row) for row in conn.execute("SELECT * FROM user_literature_progress")] == before
        states = list(conn.execute("SELECT user_id,reading_status,source_literature_id FROM user_literature_work_progress ORDER BY user_id"))
        assert [tuple(row) for row in states] == [(1, "deferred", "two"), (2, "read", "one")]
        conn.execute("UPDATE user_literature_work_progress SET reading_status='not_started' WHERE user_id=1")
        assert migrate_reading_schema(conn, ITEMS) == {"already_applied": True}
        assert conn.execute("SELECT reading_status FROM user_literature_work_progress WHERE user_id=1").fetchone()[0] == 'not_started'
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE user_literature_work_progress SET reading_status='skipped'")


@pytest.mark.parametrize('latest', ['2026-09-01T12:00:00Z', 'invalid'])
def test_ambiguous_time_prevents_ddl_and_all_writes(latest):
    with make_connection() as conn:
        add(conn, legacy(1, 'one', 'read', '2026-09-01T12:00:00Z'))
        add(conn, legacy(1, 'two', 'skipped', latest))
        with pytest.raises(ValueError, match='conflict'):
            migrate_reading_schema(conn, ITEMS)
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='user_literature_work_progress'").fetchone()
        assert conn.execute("SELECT COUNT(*) FROM user_literature_progress").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 0


def test_empty_database_and_bad_identity_do_not_invent_history():
    with make_connection() as conn:
        assert migrate_reading_schema(conn, ITEMS)['work_rows'] == 0
        assert conn.execute("SELECT COUNT(*) FROM user_literature_progress").fetchone()[0] == 0
    with pytest.raises(ValueError, match='Ambiguous'):
        plan_legacy_reading([], ITEMS + [{"id": "one", "work_id": "different"}])
    planned, unknown = plan_legacy_reading([
        legacy(1, 'one', 'revisit', 'invalid'), legacy(1, 'two', 'skipped', 'invalid')], ITEMS)
    assert planned[0]['reading_status'] == 'deferred' and unknown == 0


def test_canonical_sqlite_tuple_rows_are_supported():
    with make_connection() as conn:
        add(conn, legacy(1, 'one', 'revisit', '2026-09-29T12:00:00Z'))
        conn.row_factory = None
        assert migrate_reading_schema(conn, ITEMS)['work_rows'] == 1
        assert conn.execute('SELECT reading_status FROM user_literature_work_progress').fetchone() == ('deferred',)


def test_all_previous_postgres_ddl_digests_remain_immutable():
    from app.postgres_schema import ddl_digest
    expected = {'postgres-v1': '3dee171633ea5f4d4242d1d5024dfd8b5ecb5c1464e3e910ce51e8c23540b8ee', 'postgres-v2': '736fb2576f0cbfc3b700874591a2df9cab1cd9eb0b45a1c6383f9eaa064edd1d', 'postgres-v3': 'bc7a2cebab89934703096e6b47e083980ac1157c838b78fc881147f0fdea3014', 'postgres-v4': '5171f45f8d6fc9574462cd2f79e7fea599b0f97675e5e4054f5e3bc5341f7fa1', 'postgres-v5': '3ca29571e3b004ad78de1ec019c9f07380c1743b400f80675713070f8e962ecf', 'postgres-v6': '88a03be14e1247c61640b39f06fe0f662de9706b09cee4e637dceadb140a7a6d', 'postgres-v7': 'bb1f068161e0ed023f04fc90aaad89d4fc971ffb5a7cd8ec6d2ee69c03b38828'}
    assert {version: ddl_digest(version) for version in expected} == expected
