"""Native PostgreSQL dump/restore of a whole disposable database, not a mock."""
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit, urlunsplit, unquote
import uuid

import psycopg
from psycopg import sql
import pytest

from app.db import get_connection, upsert_approved_questions
from app.deletion_journal import initialize, recorded_deletion, recovery_records
from app.postgres_import import import_snapshot
from app.postgres_recovery import manifest, verify_user_state
from app.postgres_schema import upgrade_schema
from app.privacy_data import confirm_learning_data_deletion, prepare_learning_data_deletion, replay_learning_deletions
from scripts.postgres_backup import backup_and_rehearse, read_verified_record, rehearse_user_recovery
from scripts.postgres_test_support import test_target as validate_test_target
from tests.test_attempt_content import make_attempt, NEW, OTHER
from tests.postgres.conftest import remove_learning_schema


class NativeRuntime:
    def __init__(self, admin, target, native_bin, container):
        self.admin, self.target = admin, target
        self.native_bin, self.container = native_bin, container
        self.created = set()

    def require_stopped_writers(self):
        # This fixture's exclusive database has no application processes.
        pass

    def identity(self):
        return {"database": urlsplit(self.target).path[1:], "environment": "isolated-test"}

    def manifest(self, database=None):
        target = self.target if database is None else urlunsplit(urlsplit(self.target)._replace(path='/' + database))
        with closing(get_connection(target)) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            return manifest(conn)

    def tool(self, name, arguments, *, output=None, source=None):
        parsed = urlsplit(self.admin)
        env = {**os.environ, 'PGPASSWORD': unquote(parsed.password)}
        if self.container:
            command = ['docker', 'exec', '-i', '-e', 'PGPASSWORD', self.container, name]
            connection = ['--username', unquote(parsed.username)]
        else:
            command = [str(Path(self.native_bin) / (name + ('.exe' if os.name == 'nt' else '')))]
            connection = ['--host', parsed.hostname, '--port', str(parsed.port), '--username', unquote(parsed.username)]
        result = subprocess.run(command + connection + arguments, env=env, stdin=source,
                                stdout=output or subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        # Never include URI, environment or driver error containing values.
        assert result.returncode == 0, name + ' failed'

    def dump(self, path):
        with path.open('xb') as output:
            self.tool('pg_dump', ['--dbname', urlsplit(self.target).path[1:], '--format=custom', '--no-owner', '--no-acl'], output=output)

    def create_restore_database(self, name):
        assert name.startswith('psychology_restore_') and len(name) == len('psychology_restore_') + 32
        with psycopg.connect(self.admin, autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE DATABASE {} OWNER {} TEMPLATE template0').format(
                sql.Identifier(name), sql.Identifier(unquote(urlsplit(self.target).username))))
        self.created.add(name)

    def restore(self, path, database):
        assert database in self.created
        with path.open('rb') as source:
            self.tool('pg_restore', ['--dbname', database, '--role', unquote(urlsplit(self.target).username),
                                    '--exit-on-error', '--single-transaction', '--no-owner', '--no-acl'], source=source)

    def rebuild_restore_content(self, name):
        assert name in self.created
        target = urlunsplit(urlsplit(self.target)._replace(path='/' + name))
        with closing(get_connection(target)) as conn, conn:
            upgrade_schema(conn)
            upsert_approved_questions(conn, [NEW, OTHER], authoritative=True)
        with closing(get_connection(target)) as conn:
            assert conn.execute(
                "SELECT question_text FROM questions WHERE external_id=?", (NEW['id'],)
            ).fetchone()[0] == NEW['question']
            snapshots = conn.execute(
                "SELECT content_snapshot FROM quiz_session_questions ORDER BY session_id,order_index"
            ).fetchall()
            assert snapshots and any('Original question?' in row[0] for row in snapshots)
            assert all('Edited question?' not in row[0] for row in snapshots)

    def drop_restore_database(self, name):
        assert name in self.created
        with psycopg.connect(self.admin, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        self.created.remove(name)


@pytest.fixture(params=['postgres-v1', 'postgres-v2', 'postgres-v9'])
def native_runtime(source, request):
    admin, target = os.environ.get('POSTGRES_TEST_ADMIN_DSN'), os.environ.get('POSTGRES_TEST_DSN')
    native_bin, container = os.environ.get('POSTGRES_TEST_NATIVE_BIN'), os.environ.get('POSTGRES_TEST_CONTAINER')
    if not admin or not target or not (native_bin or container):
        if os.environ.get('CI'): pytest.fail('Required native PostgreSQL recovery fixture unavailable')
        pytest.skip('Native recovery needs isolated test admin and PostgreSQL 18 client tools')
    a, t = validate_test_target(admin), validate_test_target(target)
    assert a.hostname in {'localhost', '127.0.0.1'} and (a.hostname, a.port) == (t.hostname, t.port)
    name = 'psychology_test_recovery_' + uuid.uuid4().hex
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {} OWNER {} TEMPLATE template0').format(sql.Identifier(name), sql.Identifier(unquote(t.username))))
    runtime = NativeRuntime(admin, urlunsplit(t._replace(path='/' + name)), native_bin, container)
    try:
        with closing(get_connection(str(source))) as conn, conn:
            make_attempt(conn)
            conn.execute("INSERT INTO users(id,first_name) VALUES(901,'deleted high water')")
            conn.execute('DELETE FROM users WHERE id=901')
            conn.execute("INSERT INTO web_accounts(email,password_hash,user_id,verified_at,created_at) VALUES('test@example.invalid','synthetic-hash',1,1,1)")
            conn.execute("INSERT INTO web_sessions VALUES('session',1,1,9999999999,1)")
            conn.execute("INSERT INTO web_mail_tokens VALUES('mail','test@example.invalid','recover',1,9999999999)")
            remove_learning_schema(conn)
            if request.param == 'postgres-v1':
                conn.execute('DROP TABLE glossary_sessions')
                conn.execute("DELETE FROM schema_migrations WHERE version='glossary-v1'")
            else:
                conn.execute("INSERT INTO glossary_sessions VALUES('session',1,'topic','Title','in_progress','{}','{}','now','now')")
        import_snapshot(source, runtime.target)
        if request.param == 'postgres-v9':
            with closing(get_connection(runtime.target)) as conn, conn:
                upgrade_schema(conn)
                conn.execute("INSERT INTO web_google_identities VALUES('synthetic-google-subject',1,1)")
                conn.execute("""INSERT INTO web_oauth_challenges
                    (state_digest,browser_digest,nonce,pkce_verifier,purpose,account_id,session_digest,expires_at)
                    VALUES('synthetic-state','synthetic-browser','synthetic-nonce',
                           'synthetic-verifier','link',1,'session',9999999999)""")
        yield runtime
    finally:
        for owned in list(runtime.created): runtime.drop_restore_database(owned)
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))


def test_native_restore_preserves_every_table_sequence_and_schema(native_runtime, tmp_path):
    before = native_runtime.manifest()
    path = backup_and_rehearse(native_runtime, tmp_path / 'backups')
    record = read_verified_record(path)
    assert record['before'] == before == native_runtime.manifest()
    assert before['sequences']['users'] == 901
    if 'web_google_identities' in before['tables']:
        with closing(get_connection(native_runtime.target)) as conn:
            assert conn.execute('SELECT subject FROM web_google_identities').fetchone()[0] == 'synthetic-google-subject'
            assert conn.execute('SELECT pkce_verifier FROM web_oauth_challenges').fetchone()[0] == 'synthetic-verifier'
    assert not native_runtime.created
    verify_user_state(before, native_runtime.manifest())
    with closing(get_connection(native_runtime.target)) as conn, conn:
        conn.execute("UPDATE user_literature_progress SET private_note='changed'")
    with pytest.raises(ValueError, match='user state'):
        verify_user_state(before, native_runtime.manifest())
    with path.with_name('database.dump').open('ab') as output: output.write(b'corrupt')
    with pytest.raises(ValueError, match='changed'): read_verified_record(path)



def test_native_restored_history_survives_current_content_rebuild(native_runtime, tmp_path):
    before = native_runtime.manifest()
    backup_path = backup_and_rehearse(native_runtime, tmp_path / 'backups')
    path = rehearse_user_recovery(native_runtime, backup_path, tmp_path / 'rehearsals')
    record = json.loads(path.read_text())
    assert record['phase'] == 'verified'
    assert record['after']['tables']['questions'] != before['tables']['questions']
    verify_user_state(before, record['after'])
    assert native_runtime.manifest() == before
    assert not native_runtime.created


@pytest.mark.skipif(os.name != "posix", reason="The production journal uses POSIX durability and locking")
def test_native_restore_replays_only_confirmed_post_backup_deletions(native_runtime, tmp_path, monkeypatch):
    runtime = native_runtime
    journal_path = tmp_path / "deletions"
    monkeypatch.setenv("LEARNING_DELETION_JOURNAL", str(journal_path))
    with closing(get_connection(runtime.target)) as conn, conn:
        upgrade_schema(conn)
        conn.execute("INSERT INTO users (id, telegram_user_id) VALUES (902, 100902)")
        conn.execute("INSERT INTO user_learning_goals VALUES (902, 'study', 3, '2026-11-08T00:00:00Z')")
    initialize(journal_path, cluster="1234", database=runtime.identity()["database"])
    with closing(get_connection(runtime.target)) as conn:
        point = recovery_records(journal_path, conn, cluster="1234")
    backup = backup_and_rehearse(runtime, tmp_path / "backups", deletion_point=point)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        with closing(get_connection(runtime.target)) as conn, conn:
            with recorded_deletion(conn, 100902):
                conn.execute("DELETE FROM user_learning_goals WHERE user_id=902")
                raise RuntimeError("simulated interruption")
    with closing(get_connection(runtime.target)) as conn:
        assert recovery_records(journal_path, conn, cluster="1234", point=point)[1] == set()
        assert conn.execute("SELECT count(*) FROM user_learning_goals WHERE user_id=902").fetchone()[0] == 1
    with closing(get_connection(runtime.target)) as conn, conn:
        token = prepare_learning_data_deletion(conn, 902)["confirmation_token"]
        assert confirm_learning_data_deletion(conn, 902, token)["ok"]
    live = runtime.manifest()

    def replay(name, restored_point, expected):
        with closing(get_connection(runtime.target)) as conn:
            state, actors = recovery_records(journal_path, conn, cluster="1234", point=restored_point)
        target = urlunsplit(urlsplit(runtime.target)._replace(path="/" + name))
        with closing(get_connection(target)) as conn, conn:
            assert manifest(conn) == expected
            assert conn.execute("SELECT count(*) FROM user_learning_goals WHERE user_id=902").fetchone()[0] == 1
            assert replay_learning_deletions(conn, state, actors) == 1
            assert replay_learning_deletions(conn, state, actors) == 1
            after = manifest(conn)
            assert after["tables"]["user_learning_goals"] == live["tables"]["user_learning_goals"]
            assert after["tables"]["quiz_sessions"] == live["tables"]["quiz_sessions"]
            assert after["tables"]["web_accounts"] == live["tables"]["web_accounts"]
            assert after["tables"]["users"] == live["tables"]["users"]
        return {"status": "verified", "actors_reconciled": 1}

    path = rehearse_user_recovery(runtime, backup, tmp_path / "rehearsals", replay_deletions=replay)
    assert json.loads(path.read_text())["deletion_reconciliation"] == {"status": "verified", "actors_reconciled": 1}
    assert runtime.manifest() == live
    assert not runtime.created


def test_failed_native_restore_preserves_source_and_cleans_only_owned_database(native_runtime, tmp_path, monkeypatch):
    before = native_runtime.manifest()
    real = native_runtime.restore
    def corrupted(path, database):
        path.write_bytes(b'not a PostgreSQL archive')
        real(path, database)
    monkeypatch.setattr(native_runtime, 'restore', corrupted)
    with pytest.raises(AssertionError, match='pg_restore failed'):
        backup_and_rehearse(native_runtime, tmp_path / 'backups')
    assert native_runtime.manifest() == before
    assert not native_runtime.created
    record = json.loads(next((tmp_path / 'backups').glob('*/record.json')).read_text())
    assert record['phase'] == 'failed' and record['restore_cleanup'] == 'removed'


def test_postgres_readiness_reports_real_backend_and_rejects_schema_drift(web):
    response = web.client.get('/readyz')
    assert response.status_code == 200
    assert response.json()['database_backend'] == 'postgresql'
    assert response.json()['database_version'].split()[0] == '18.6'
    with closing(get_connection(web.db)) as conn, conn:
        conn.execute('ALTER TABLE users ADD COLUMN unknown TEXT')
    response = web.client.get('/readyz')
    assert response.status_code == 503
    assert response.json()['error'] == 'database_unavailable'
    assert 'unknown' not in response.text and 'postgresql://' not in response.text
