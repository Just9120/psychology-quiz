from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import sqlite3
from threading import Barrier
from types import SimpleNamespace

import pytest

from app.database import IntegrityError, OperationalError, PostgresConnection
from app.db import get_connection, create_or_load_user, get_owner_stats, upsert_approved_questions
from app.postgres_import import import_snapshot
from app.postgres_schema import initialize_schema, verify_schema, table_columns
from app.quiz_service import answer_quiz, prepare_quiz, start_prepared_quiz
from app.web_auth import AuthError, WebAuth, digest
from tests.test_attempt_content import make_attempt, NEW
from tests.test_web_auth import EMAIL, PASSWORD, SETTINGS, Mailbox, post, login


def test_every_row_identity_sequence_and_snapshot_survive_import(source, pg_target):
    with closing(get_connection(str(source))) as conn, conn:
        sid = make_attempt(conn)
        answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=1, selected_option_index=0)
        upsert_approved_questions(conn, [NEW])
        conn.execute("INSERT INTO users(id,first_name) VALUES(900,'deleted')")
        conn.execute("DELETE FROM users WHERE id=900")
        conn.execute("INSERT INTO web_accounts(email,password_hash,user_id,verified_at,created_at) VALUES(?,?,1,1,1)", (EMAIL, 'synthetic-encoded'))
        conn.execute("INSERT INTO web_sessions VALUES('session-digest',1,1,9999999999,1)")
        conn.execute("INSERT INTO web_mail_tokens VALUES('mail-digest',?,'recover',1,9999999999)", (EMAIL,))
        conn.execute("INSERT INTO web_link_tokens VALUES('link-digest',1,'session-digest',1,1,9999999999)")
        conn.execute("INSERT INTO web_auth_limits VALUES('login',1,2)")
        conn.execute("UPDATE user_literature_progress SET private_note=?", ("Личная заметка: ? 100% ' \"",))
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    report = import_snapshot(source, pg_target)
    assert report['result'] == 'imported'
    assert report['sequences']['users'] == 900
    assert import_snapshot(source, pg_target)['result'] == 'already_verified'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    with closing(sqlite3.connect(source)) as old, closing(get_connection(pg_target)) as conn, conn:
        for table, fields in table_columns(conn).items():
            if table == 'postgres_storage': continue
            query = f'SELECT {",".join(fields)} FROM {table}'
            assert {tuple(row) for row in old.execute(query)} == {tuple(row) for row in conn.execute(query)}, table
        assert create_or_load_user(conn, 999, None, None, None)['id'] == 901
        assert get_owner_stats(conn)['total_quiz_answers'] == 1
        original = conn.execute('SELECT content_snapshot FROM quiz_session_questions LIMIT 1').fetchone()[0]
        assert 'Original question?' in original
    with pytest.raises(ValueError, match='changed'):
        import_snapshot(source, pg_target)


@pytest.mark.parametrize('damage', ['extra-column', 'missing-table', 'corrupt-snapshot', 'foreign-key'])
def test_invalid_source_leaves_empty_target_and_source_unchanged(source, pg_target, damage):
    with closing(sqlite3.connect(source)) as conn, conn:
        if damage == 'extra-column': conn.execute('ALTER TABLE users ADD COLUMN unknown TEXT')
        if damage == 'missing-table': conn.execute('DROP TABLE web_auth_limits')
        if damage == 'corrupt-snapshot':
            conn.execute("INSERT INTO quiz_sessions(user_id) VALUES(1)")
            conn.execute("INSERT INTO quiz_session_questions(session_id,question_id,order_index,content_snapshot) VALUES(1,1,1,'corrupt')")
        if damage == 'foreign-key': conn.execute("INSERT INTO quiz_sessions(user_id) VALUES(999)")
    before = source.read_bytes()
    with pytest.raises(ValueError): import_snapshot(source, pg_target)
    assert source.read_bytes() == before
    with closing(get_connection(pg_target)) as conn:
        assert table_columns(conn) == {}


def test_import_failure_rolls_back_and_retry_succeeds(source, pg_target, monkeypatch):
    real = PostgresConnection.executemany
    def fail_after_users(self, statement, parameters):
        if statement.startswith('INSERT INTO "questions"'):
            raise OperationalError('08006')
        return real(self, statement, parameters)
    with monkeypatch.context() as patch:
        patch.setattr(PostgresConnection, 'executemany', fail_after_users)
        with pytest.raises(OperationalError): import_snapshot(source, pg_target)
    with closing(get_connection(pg_target)) as conn:
        assert table_columns(conn) == {}
    assert import_snapshot(source, pg_target)['result'] == 'imported'


def test_target_drift_and_nonempty_data_are_never_overwritten(source, pg_target):
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn)
        conn.execute("INSERT INTO users(first_name) VALUES('existing')")
    with pytest.raises(ValueError, match='empty target'): import_snapshot(source, pg_target)
    with closing(get_connection(pg_target)) as conn, conn:
        assert conn.execute('SELECT first_name FROM users').fetchone()[0] == 'existing'
        conn.execute('ALTER TABLE users DROP CONSTRAINT users_telegram_user_id_key')
    with pytest.raises(ValueError, match='drift'): import_snapshot(source, pg_target)


def test_snapshot_guard_and_driver_errors_hide_data(bank):
    with closing(get_connection(bank)) as conn, conn:
        make_attempt(conn)
    with closing(get_connection(bank)) as conn:
        with pytest.raises(IntegrityError) as error:
            conn.execute("UPDATE quiz_session_questions SET content_snapshot=?", ('private-secret',))
        assert 'private-secret' not in str(error.value)
        assert error.value.sqlstate == '23514'
        conn.rollback()
        verify_schema(conn)


def test_concurrent_setups_leave_one_active_attempt(bank):
    barrier = Barrier(2)
    def setup():
        with closing(get_connection(bank)) as conn, conn:
            prepared = prepare_quiz(conn, {'quiz_mode':'all','category_ids':[],'question_count':None,'difficulty':'any'})
            barrier.wait()
            return start_prepared_quiz(conn, actor_user_id=1, prepared=prepared)['session']['session_id']
    with ThreadPoolExecutor(2) as pool:
        ids = list(pool.map(lambda _: setup(), range(2)))
    assert len(set(ids)) == 2
    with closing(get_connection(bank)) as conn:
        assert sorted(row[0] for row in conn.execute('SELECT status FROM quiz_sessions')) == ['abandoned','in_progress']


def test_concurrent_mail_proof_is_consumed_once_and_session_cap_keeps_new_session(web):
    post(web, 'auth/register', {'email':EMAIL})
    token = web.mailbox.messages[-1][2]
    def consume():
        try:
            web.auth.set_password(token, PASSWORD, 'register')
            return 'ok'
        except AuthError as error: return error.code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(lambda _: consume(), range(2))) == ['invalid_token','ok']
    for _ in range(12):
        web.now[0] += 61  # bypass only elapsed rate-limit windows, not the limit itself
        session = web.auth.login(EMAIL, PASSWORD)
    with closing(get_connection(web.db)) as conn, conn:
        assert conn.execute('SELECT count(*) FROM web_sessions').fetchone()[0] == 10
        assert web.auth.authenticate(conn, session)['email'] == EMAIL
    # A replacement API instance sees the same durable login/session.
    restarted = WebAuth(web.db, SETTINGS, Mailbox(), clock=lambda:web.now[0])
    with restarted.transaction() as conn:
        assert restarted.authenticate(conn, session)['email'] == EMAIL


def test_canonical_init_seed_and_read_only_parity_on_postgres(pg_target, monkeypatch):
    from scripts import init_db, seed_questions
    from scripts.audit_question_bank import build_report, has_blockers, read_only_connection
    from app.database import DatabaseError
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn)
    monkeypatch.setenv('DATABASE_URL', pg_target)
    monkeypatch.setenv('DB_PATH', 'must-not-be-created.sqlite3')
    assert init_db.main() == 0
    assert seed_questions.main() == 0
    report = build_report(pg_target)
    assert report['sqlite']['backend'] == 'postgresql'
    assert report['sqlite']['schema_check'] == 'ok'
    assert report['approved_question_count'] > 0
    assert not has_blockers(report)
    assert pg_target not in str(report)
    with closing(read_only_connection(pg_target)) as conn:
        with pytest.raises(DatabaseError) as error:
            conn.execute('DELETE FROM users')
        assert error.value.sqlstate == '25006'


def test_connection_failure_has_no_secret_or_sqlite_fallback(tmp_path):
    target = 'postgresql://synthetic:private-password@127.0.0.1:1/psychology_test'
    with pytest.raises(OperationalError) as error:
        get_connection(target)
    assert 'private-password' not in str(error.value)
    assert '127.0.0.1' not in str(error.value)


def test_existing_session_mail_proof_and_telegram_link_continue_after_import(source, pg_target):
    mailbox = Mailbox()
    now = lambda: 1800000000
    old = WebAuth(str(source), SETTINGS, mailbox, clock=now)
    old.request_mail(EMAIL, 'register')
    old.set_password(mailbox.messages[-1][2], PASSWORD, 'register')
    session = old.login(EMAIL, PASSWORD)
    with old.transaction() as conn:
        account = old.authenticate(conn, session)
        code = old.start_link(conn, account)
    old.propose_telegram_link(code, SimpleNamespace(id=42, username=None, first_name='Original user', last_name=None))
    old.confirm_telegram_link(code, 42)
    old.request_mail(EMAIL, 'recover')
    recovery = mailbox.messages[-1][2]
    source_bytes = source.read_bytes()
    import_snapshot(source, pg_target)
    new = WebAuth(pg_target, SETTINGS, Mailbox(), clock=now)
    with new.transaction() as conn:
        account = new.authenticate(conn, session)
        assert new.account_state(conn, account, session)['link_confirmed'] is True
        new.complete_link(conn, account)
    assert new.login(EMAIL, PASSWORD)
    new.set_password(recovery, 'Replacement synthetic password', 'recover')
    with new.transaction() as conn:
        with pytest.raises(AuthError, match='unauthorized'): new.authenticate(conn, session)
    assert source.read_bytes() == source_bytes


def test_literature_progress_persists_and_isolates_actors(bank):
    from fastapi.testclient import TestClient
    from app.literature import load_literature_items
    from app.miniapp_fastapi import create_app
    from tests.test_attempt_content import TOKEN
    from tests.test_miniapp_api import _make_init_data
    item = load_literature_items()[0]['id']
    headers = {'Authorization':'tma '+_make_init_data(TOKEN, {'id':42,'first_name':'Original user'})}
    with TestClient(create_app(db_path=bank, bot_token=TOKEN)) as client:
        for status, percent, expected in [('in_progress',40,40),('read',12,100),('not_started',None,0)]:
            response = client.post('/miniapp/literature/progress', headers=headers,
                json={'literature_id':item,'reading_status':status,'progress_percent':percent})
            assert response.status_code == 200
            state = response.json()['literature_progress']
            assert state['reading_status'] == status and state['progress_percent'] == expected
            assert 'private_note' not in state
        assert client.post('/miniapp/literature/progress', headers=headers,
            json={'literature_id':item,'reading_status':'in_progress','progress_percent':101}).status_code == 400
    with TestClient(create_app(db_path=bank, bot_token=TOKEN)) as restarted:
        states = restarted.get('/miniapp/literature/state',headers=headers).json()['literature_state']
        assert any(row['literature_id']==item and row['reading_status']=='not_started' for row in states)
        other = {'Authorization':'tma '+_make_init_data(TOKEN, {'id':777,'first_name':'Other'})}
        assert restarted.get('/miniapp/literature/state',headers=other).json()['literature_state'] == []


def test_import_rejects_sqlite_target_without_creating_it(source, tmp_path):
    target = tmp_path / 'not-a-postgres-target.sqlite3'
    with pytest.raises(ValueError, match='must be PostgreSQL'):
        import_snapshot(source, str(target))
    assert not target.exists()
