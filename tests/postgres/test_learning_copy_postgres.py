"""Read-only learning copy must use the same PostgreSQL actor boundaries."""
from contextlib import closing
from io import StringIO
import json
import subprocess

from app.db import get_connection
from app.postgres_schema import initialize_schema
from app.privacy_export import write_learning_copy
from scripts import export_learning_data as cli


def test_learning_copy_postgres_consistent_scope(pg_target):
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn)
        conn.execute("INSERT INTO users(id,telegram_user_id) VALUES(1,101),(2,202)")
        conn.execute("INSERT INTO quiz_sessions(id,user_id) VALUES(11,1),(22,2)")
        conn.execute("INSERT INTO web_accounts(id,email,user_id,password_hash,verified_at,created_at) VALUES(10,'mine@example.test',1,'secret-hash',100,100),(20,'other-private@example.test',2,'other-hash',100,100)")
        conn.execute("INSERT INTO web_profile_names(account_id,display_name) VALUES(10,'My display name'),(20,'Other display name')")
        conn.execute("INSERT INTO web_google_identities(subject,account_id,created_at) VALUES('my-google-subject',10,100),('other-google-subject',20,100)")
    with closing(get_connection(pg_target)) as conn:
        output = StringIO()
        counts = write_learning_copy(conn, 1, output)
        result = json.loads(output.getvalue())
        assert result["complete"] is True
        assert counts["quiz_sessions"] == 1
        assert [row["id"] for row in result["tables"]["quiz_sessions"]] == [11]
        assert result["tables"]["quiz_answers"] == []
        assert not conn.in_transaction
        profile = StringIO()
        write_learning_copy(conn, 1, profile, expected_telegram_user_id=101, include_identity=True)
        copied = json.loads(profile.getvalue())
        assert copied['complete'] is True and copied['scope'] == 'profile_and_learning_data_copy'
        assert copied['tables']['web_accounts'][0]['email'] == 'mine@example.test'
        assert copied['tables']['web_profile_names'][0]['display_name'] == 'My display name'
        assert copied['tables']['web_google_identities'][0]['subject'] == 'my-google-subject'
        assert not any(marker in profile.getvalue() for marker in ('other-', 'secret-hash', 'password_hash'))
        assert conn.execute("SELECT count(*) FROM quiz_sessions").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 2


def test_operator_cli_postgres_ends_identity_lookup_before_read_only_copy(pg_target, tmp_path, monkeypatch, capsys):
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn)
        conn.execute("INSERT INTO users(id,telegram_user_id) VALUES(1,101),(2,202)")
        conn.execute("INSERT INTO quiz_sessions(id,user_id) VALUES(11,1),(22,2)")
    (tmp_path / 'data').mkdir()
    (tmp_path / '.gitignore').write_text('data/\n', encoding='utf-8')
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, capture_output=True)
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(cli, 'resolve_database_target', lambda **kwargs: pg_target)
    output = tmp_path / 'data/copy.json'
    args = ['--telegram-user-id', '101', '--verified-request', '--output', str(output)]
    assert cli.main(args) == 0
    original = output.read_bytes()
    copied = json.loads(original)
    assert copied['complete'] is True and copied['row_counts']['quiz_sessions'] == 1
    assert [row['id'] for row in copied['tables']['quiz_sessions']] == [11]
    assert '101' not in capsys.readouterr().out
    assert cli.main(args) == 1 and output.read_bytes() == original
    with closing(get_connection(pg_target)) as conn:
        assert [row[0] for row in conn.execute('SELECT id FROM users ORDER BY id')] == [1, 2]
        assert [row[0] for row in conn.execute('SELECT id FROM quiz_sessions ORDER BY id')] == [11, 22]
