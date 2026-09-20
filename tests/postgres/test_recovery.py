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

from app.db import get_connection
from app.postgres_import import import_snapshot
from app.postgres_recovery import manifest, verify_user_state
from scripts.postgres_backup import backup_and_rehearse, read_verified_record
from scripts.postgres_test_support import test_target as validate_test_target
from tests.test_attempt_content import make_attempt


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

    def drop_restore_database(self, name):
        assert name in self.created
        with psycopg.connect(self.admin, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        self.created.remove(name)


@pytest.fixture
def native_runtime(source):
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
        import_snapshot(source, runtime.target)
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
    assert not native_runtime.created
    verify_user_state(before, native_runtime.manifest())
    with closing(get_connection(native_runtime.target)) as conn, conn:
        conn.execute("UPDATE user_literature_progress SET private_note='changed'")
    with pytest.raises(ValueError, match='user state'):
        verify_user_state(before, native_runtime.manifest())
    with path.with_name('database.dump').open('ab') as output: output.write(b'corrupt')
    with pytest.raises(ValueError, match='changed'): read_verified_record(path)


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
