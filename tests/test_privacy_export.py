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


def populate_identity_fixture(conn):
    populate_copy_fixture(conn)
    for column in ('username', 'first_name', 'last_name', 'reading_mode', 'created_at', 'updated_at'):
        conn.execute(f'ALTER TABLE users ADD COLUMN {column} TEXT')
    conn.execute("UPDATE users SET username='mine',first_name='Owner',reading_mode='normal' WHERE id=1")
    conn.execute("UPDATE users SET username='other-private-name' WHERE id=2")
    conn.execute('DROP TABLE web_accounts')
    conn.execute('CREATE TABLE web_accounts(id INTEGER PRIMARY KEY,email TEXT,user_id INTEGER,enabled INTEGER,verified_at INTEGER,created_at INTEGER,password_hash TEXT)')
    conn.execute("INSERT INTO web_accounts VALUES(10,'mine@example.test',1,1,100,100,'secret-password-hash'),(20,'other-private-email@example.test',2,1,100,100,'other-hash')")
    conn.execute('CREATE TABLE web_profile_names(account_id INTEGER,display_name TEXT)')
    conn.execute("INSERT INTO web_profile_names VALUES(10,'My display name'),(20,'Other display name')")
    conn.execute('CREATE TABLE web_google_identities(subject TEXT,account_id INTEGER,created_at INTEGER)')
    conn.execute("INSERT INTO web_google_identities VALUES('my-google-subject',10,100),('other-google-subject',20,100)")
    conn.commit()


def test_optional_profile_copy_reads_only_allowlisted_fields_of_same_actor():
    with sqlite3.connect(':memory:') as conn:
        populate_identity_fixture(conn)
        before = conn.total_changes
        reads = []

        def authorize(action, table, column, database, trigger):
            if action == sqlite3.SQLITE_READ:
                reads.append((table, column))
                if column in {'password_hash', 'token_digest', 'digest', 'nonce', 'pkce_verifier'}:
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        conn.set_authorizer(authorize)
        output = StringIO()
        counts = write_learning_copy(conn, 1, output, expected_telegram_user_id=101, include_identity=True)
        value = json.loads(output.getvalue())
        assert value['schema_version'] == 2 and value['scope'] == 'profile_and_learning_data_copy'
        assert value['complete'] is True and value['row_counts'] == counts
        assert value['tables']['users'][0]['telegram_user_id'] == 101
        assert value['tables']['web_accounts'][0]['email'] == 'mine@example.test'
        assert value['tables']['web_profile_names'] == [{'account_id': 10, 'display_name': 'My display name'}]
        assert value['tables']['web_google_identities'] == [{'subject': 'my-google-subject', 'account_id': 10, 'created_at': 100}]
        assert 'credentials_and_authentication_state' in value['excluded']
        assert not any(marker in output.getvalue() for marker in ('other', 'secret-', 'private-source-locator', 'password_hash', 'token_digest'))
        assert ('web_accounts', 'email') in reads
        assert conn.total_changes == before and not conn.in_transaction
        conn.set_authorizer(None)
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            conn.execute('DELETE FROM users')


def test_operator_profile_copy_requires_explicit_flag_and_preserves_private_output(tmp_path, monkeypatch, capsys):
    import subprocess
    from scripts import export_learning_data as cli
    (tmp_path / 'data').mkdir()
    (tmp_path / '.gitignore').write_text('data/\n', encoding='utf-8')
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, capture_output=True)
    database = tmp_path / 'data/database.sqlite'
    with sqlite3.connect(database) as conn:
        populate_identity_fixture(conn)
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(cli, 'resolve_database_target', lambda **kwargs: str(database))
    target = tmp_path / 'data/profile-copy.json'
    args = ['--telegram-user-id', '101', '--verified-request', '--include-identity', '--output', str(target)]
    assert cli.main(args) == 0
    original = target.read_bytes()
    assert json.loads(original)['tables']['web_accounts'][0]['id'] == 10
    assert not any(marker in capsys.readouterr().out for marker in ('101', 'mine@example.test', 'my-google-subject'))
    assert cli.main(args) == 1 and target.read_bytes() == original
    with sqlite3.connect(database) as conn:
        assert conn.execute('SELECT count(*) FROM web_accounts').fetchone()[0] == 2


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
