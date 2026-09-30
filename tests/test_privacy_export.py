"""Copy requests must not export another actor or authentication/source storage."""
from io import StringIO
import json
import sqlite3

import pytest

from app.privacy_data import LEARNING_TABLES, PrivacyError
from app.privacy_export import CHILD_TABLES, write_learning_copy


def populate_copy_fixture(conn):
    conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY,telegram_user_id INTEGER)")
    conn.execute("CREATE TABLE web_accounts(user_id INTEGER,password_hash TEXT)")
    conn.execute("CREATE TABLE user_data_deletion_challenges(user_id INTEGER,token_digest TEXT)")
    conn.execute("INSERT INTO users VALUES(1,101),(2,202)")
    conn.execute("INSERT INTO web_accounts VALUES(1,'secret-password-hash')")
    conn.execute("INSERT INTO user_data_deletion_challenges VALUES(1,'secret-token')")
    for table in LEARNING_TABLES:
        extra = ",content_snapshot TEXT" if table == "quiz_sessions" else ""
        conn.execute(f"CREATE TABLE {table}(id INTEGER PRIMARY KEY,user_id INTEGER,value TEXT{extra})")
        conn.execute(f"INSERT INTO {table}(id,user_id,value) VALUES(11,1,'mine'),(22,2,'other')")
    conn.execute("UPDATE quiz_sessions SET content_snapshot='private-source-locator'")
    for table in CHILD_TABLES:
        conn.execute(f"CREATE TABLE {table}(session_id INTEGER,value TEXT)")
        conn.execute(f"INSERT INTO {table} VALUES(11,'mine'),(22,'other')")
    conn.commit()


def test_learning_copy_is_complete_actor_scoped_and_read_only():
    conn = sqlite3.connect(":memory:")
    try:
        populate_copy_fixture(conn)
        before = conn.total_changes
        output = StringIO()
        counts = write_learning_copy(conn, 1, output)
        value = json.loads(output.getvalue())
        assert value["scope"] == "learning_data_copy" and value["complete"] is True
        assert set(counts) == set(LEARNING_TABLES) | set(CHILD_TABLES)
        assert counts == {table: 1 for table in counts} == value["row_counts"]
        assert all(rows[0]["value"] == "mine" for rows in value["tables"].values())
        assert not any(marker in output.getvalue() for marker in
                       ("other", "secret-password-hash", "secret-token", "private-source-locator"))
        assert conn.total_changes == before and not conn.in_transaction
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM users")
        conn.rollback()
        for actor in (False, "1", 0, -1):
            with pytest.raises(PrivacyError, match="invalid_actor"):
                write_learning_copy(conn, actor, StringIO())
        changed = StringIO()
        with pytest.raises(PrivacyError, match="identity_changed"):
            write_learning_copy(conn, 1, changed, expected_telegram_user_id=202)
        assert not changed.getvalue() and not conn.in_transaction
        unknown = StringIO()
        with pytest.raises(PrivacyError, match="unknown_actor"):
            write_learning_copy(conn, 99, unknown)
        assert not unknown.getvalue() and not conn.in_transaction
    finally:
        conn.close()


def test_learning_copy_refuses_active_transaction_and_preserves_it():
    conn = sqlite3.connect(":memory:")
    try:
        populate_copy_fixture(conn)
        conn.execute("UPDATE users SET telegram_user_id=303 WHERE id=1")
        with pytest.raises(PrivacyError, match="export_requires_new_transaction"):
            write_learning_copy(conn, 1, StringIO())
        assert conn.in_transaction
        assert conn.execute("SELECT telegram_user_id FROM users WHERE id=1").fetchone()[0] == 303
    finally:
        conn.close()

def test_operator_copy_creates_private_ignored_file_without_overwrite(tmp_path, monkeypatch, capsys):
    import subprocess
    from scripts import export_learning_data as cli
    (tmp_path / "data").mkdir()
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    database = tmp_path / "data/database.sqlite"
    with sqlite3.connect(database) as conn:
        populate_copy_fixture(conn)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "resolve_database_target", lambda **kwargs: str(database))
    target = tmp_path / "data/copy.json"
    args = ["--telegram-user-id", "101", "--verified-request", "--output", str(target)]
    assert cli.main(args) == 0
    original = target.read_bytes()
    assert json.loads(original)["complete"] is True
    if __import__("os").name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600
    assert "101" not in capsys.readouterr().out
    assert cli.main(args) == 1
    assert target.read_bytes() == original
    unknown = tmp_path / "data/unknown.json"
    assert cli.main(["--telegram-user-id", "909", "--verified-request", "--output", str(unknown)]) == 1
    assert not unknown.exists()
    public = tmp_path / "public.json"
    assert cli.main(["--telegram-user-id", "101", "--verified-request", "--output", str(public)]) == 1
    assert not public.exists()
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM quiz_sessions").fetchone()[0] == 2
