from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from scripts.deployment_db import backup_and_rehearse, check_business, read_connection, verify_preserved
from app.attempt_content import ensure_attempt_snapshots
from scripts.deployment_db import check_runtime_config


def test_preflight_rejects_incomplete_pwa_before_runtime_changes(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:synthetic")
    monkeypatch.setenv("TELEGRAM_UPDATE_MODE", "polling")
    monkeypatch.setenv("PWA_ENABLED", "false")
    check_runtime_config()
    monkeypatch.setenv("PWA_ENABLED", "true")
    monkeypatch.delenv("PWA_ORIGIN", raising=False)
    with pytest.raises(RuntimeError, match="Missing PWA_ORIGIN"):
        check_runtime_config()


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "source.sqlite3"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(Path("sql/schema.sql").read_text(encoding="utf-8"))
        conn.execute("INSERT INTO users (telegram_user_id, first_name) VALUES (42, 'Private test name')")
        conn.execute("INSERT INTO categories (slug, name) VALUES ('test', 'Test')")
        conn.execute("INSERT INTO questions (external_id, category_id, question_text) VALUES ('q1', 1, 'Question')")
        conn.execute("INSERT INTO question_options (question_id, option_index, option_text, is_correct) VALUES (1, 0, 'Yes', 1), (1, 1, 'No', 0)")
        conn.execute("INSERT INTO quiz_sessions (user_id, category_id, score) VALUES (1, 1, 1)")
        conn.execute("INSERT INTO quiz_session_questions (session_id, question_id, order_index) VALUES (1, 1, 0)")
        conn.execute("INSERT INTO quiz_answers (session_id, question_id, selected_option_index, is_correct) VALUES (1, 1, 0, 1)")
        conn.execute("INSERT INTO user_literature_progress (user_id, literature_id, reading_status, updated_at, private_note) VALUES (1, 'lit', 'read', 'today', 'private note')")
        ensure_attempt_snapshots(conn)
    return path


def test_backup_rehearses_restore_preserves_original_and_all_user_data(database, tmp_path):
    original = database.read_bytes()
    backup = backup_and_rehearse(database, tmp_path / "backups")
    verify_preserved(database, backup)
    assert database.read_bytes() == original
    assert "Private test name" not in backup.with_name("manifest.json").read_text()
    with closing(read_connection(backup)) as conn:
        assert conn.execute("SELECT private_note FROM user_literature_progress").fetchone() == ("private note",)
        check_business(conn)
    assert not list(backup.parent.glob("restore-check-*"))
    assert backup_and_rehearse(database, tmp_path / "backups") != backup


def test_additive_migration_passes_but_changed_historical_answer_fails(database, tmp_path):
    backup = backup_and_rehearse(database, tmp_path / "backups")
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("ALTER TABLE quiz_session_questions ADD COLUMN snapshot TEXT")
        conn.execute("UPDATE quiz_session_questions SET snapshot='captured revision'")
    verify_preserved(database, backup)
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("UPDATE quiz_answers SET is_correct=0")
    with pytest.raises(RuntimeError, match="user state"):
        verify_preserved(database, backup)


def test_backup_rejects_foreign_key_corruption(database, tmp_path):
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("UPDATE quiz_answers SET session_id=999")
    with pytest.raises(RuntimeError, match="foreign key"):
        backup_and_rehearse(database, tmp_path / "backups")


def test_missing_database_is_not_silently_created(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        read_connection(missing)
    assert not missing.exists()


def test_business_smoke_rejects_invalid_serving_options(database):
    with closing(sqlite3.connect(database)) as conn, conn:
        conn.execute("UPDATE question_options SET is_correct=1")
        with pytest.raises(RuntimeError, match="options"):
            check_business(conn)


def test_preparatory_release_blocks_postgres_delivery_before_touching_sqlite(monkeypatch, tmp_path):
    from scripts.deployment_db import main
    missing = tmp_path / 'untouched.sqlite3'
    monkeypatch.setenv('DATABASE_URL', 'postgresql://synthetic:private@localhost/psychology_test')
    monkeypatch.setenv('DB_PATH', str(missing))
    monkeypatch.setattr('sys.argv', ['deployment_db.py', 'preflight'])
    with pytest.raises(RuntimeError, match='PostgreSQL cutover/delivery'):
        main()
    assert not missing.exists()
