from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from app.db import create_or_load_user, get_connection, upsert_approved_questions, save_quiz_answer
from app.identity_schema import migrate_identity_schema
from scripts.deployment_db import backup_and_rehearse, verify_preserved, user_state
from scripts import init_db
from tests.test_attempt_content import OLD, make_attempt


def legacy_db(path):
    with closing(get_connection(str(path))) as conn, conn:
        schema = Path('sql/schema.sql').read_text(encoding='utf-8').replace(
            'telegram_user_id INTEGER UNIQUE', 'telegram_user_id INTEGER NOT NULL UNIQUE')
        conn.executescript(schema)
        create_or_load_user(conn, 42, 'legacy', 'Name', 'Surname')
        upsert_approved_questions(conn, [OLD])
        sid = make_attempt(conn, questions=(1,))
        save_quiz_answer(conn, sid, 1, 0)
        conn.execute("INSERT INTO user_literature_progress(user_id,literature_id,reading_status,updated_at,private_note) VALUES(1,'book','read','then','private')")
        conn.execute("UPDATE sqlite_sequence SET seq=90 WHERE name='users'")
        conn.execute("CREATE INDEX custom_user_name ON users(username)")
        conn.execute("CREATE TRIGGER custom_user_guard BEFORE UPDATE OF first_name ON users WHEN NEW.first_name='forbidden' BEGIN SELECT RAISE(ABORT, 'guard'); END")


def test_migration_backup_restore_preserves_all_legacy_data_and_supports_web_users(tmp_path, monkeypatch):
    path = tmp_path / 'quiz.sqlite3'
    legacy_db(path)
    backup = backup_and_rehearse(path, tmp_path / 'backups')
    monkeypatch.setattr(init_db, 'resolve_db_path', lambda: str(path))
    assert init_db.main() == 0
    verify_preserved(path, backup)
    assert init_db.main() == 0
    verify_preserved(path, backup)
    with closing(get_connection(str(path))) as conn, conn:
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert conn.execute('PRAGMA foreign_key_check').fetchone() is None
        assert conn.execute('SELECT count(*) FROM schema_migrations').fetchone()[0] == 1
        user = create_or_load_user(conn, 42, 'legacy', 'Name', 'Surname')
        assert user['id'] == 1
        web1 = conn.execute('INSERT INTO users DEFAULT VALUES').lastrowid
        web2 = conn.execute('INSERT INTO users DEFAULT VALUES').lastrowid
        assert (web1, web2) == (91, 92)
        assert conn.execute('SELECT telegram_user_id FROM users WHERE id=?', (web1,)).fetchone()[0] is None
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('INSERT INTO users(telegram_user_id) VALUES(42)')
        with pytest.raises(sqlite3.IntegrityError, match='guard'):
            conn.execute("UPDATE users SET first_name='forbidden' WHERE id=1")
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='custom_user_name'").fetchone()


def test_mid_migration_failure_rolls_back_schema_data_and_restores_fk(tmp_path):
    path = tmp_path / 'quiz.sqlite3'
    legacy_db(path)
    with closing(get_connection(str(path))) as conn:
        before = user_state(conn)
        schema = conn.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()[0]
        def deny_drop(action, name, *_):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_DROP_TABLE and name == 'users' else sqlite3.SQLITE_OK
        conn.set_authorizer(deny_drop)
        with pytest.raises(sqlite3.DatabaseError):
            migrate_identity_schema(conn)
        conn.set_authorizer(None)
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert user_state(conn) == before
        assert conn.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()[0] == schema
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name IN ('users_identity_v1','schema_migrations')").fetchall()
        migrate_identity_schema(conn)
        assert user_state(conn) == before


def test_migration_refuses_callers_pending_transaction(tmp_path):
    path = tmp_path / 'quiz.sqlite3'
    legacy_db(path)
    with closing(get_connection(str(path))) as conn:
        conn.execute("UPDATE users SET username='pending'")
        with pytest.raises(RuntimeError, match='separate transaction'):
            migrate_identity_schema(conn)
        assert conn.in_transaction
        conn.rollback()
        assert conn.execute('SELECT username FROM users').fetchone()[0] == 'legacy'


def test_fresh_database_migration_and_multiple_independent_users(tmp_path):
    with closing(get_connection(str(tmp_path / 'new.sqlite3'))) as conn:
        conn.executescript(Path('sql/schema.sql').read_text(encoding='utf-8'))
        migrate_identity_schema(conn)
        conn.execute('INSERT INTO users DEFAULT VALUES')
        conn.execute('INSERT INTO users DEFAULT VALUES')
        conn.commit()
        migrate_identity_schema(conn)
        assert conn.execute('SELECT count(*) FROM users WHERE telegram_user_id IS NULL').fetchone()[0] == 2
