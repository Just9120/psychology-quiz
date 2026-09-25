from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import json
import logging
import secrets
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.auth_schema import migrate_auth_schema
from app.identity_schema import migrate_identity_schema
from app.db import get_connection
from app.miniapp_fastapi import create_app
from app.quiz_service import answer_quiz
from app.web_auth import AuthError, WebAuth, IDLE_TTL, SESSION_TTL
from app.web_config import WebSettings
from scripts.deployment_db import backup_and_rehearse, verify_preserved, user_state
from tests.test_attempt_content import bank, make_attempt, TOKEN

EMAIL = 'owner@example.test'
PASSWORD = 'A long private test passphrase'
NEW_PASSWORD = 'A different long test passphrase'
ORIGIN = 'https://pwa.example.test'
SETTINGS = WebSettings(ORIGIN, EMAIL, 'smtp.example.test', 465, EMAIL, 'synthetic-smtp-password', EMAIL)


class Mailbox:
    def __init__(self):
        self.messages = []
        self.fail = False

    def send(self, email, purpose, token):
        if self.fail:
            raise RuntimeError('SMTP secret must never appear in logs')
        self.messages.append((email, purpose, token))


@pytest.fixture
def web(bank):
    with closing(get_connection(str(bank))) as conn:
        migrate_identity_schema(conn)
        migrate_auth_schema(conn)
    now = [1800000000]
    mailbox = Mailbox()
    app = create_app(db_path=str(bank), bot_token=TOKEN, web_settings=SETTINGS, web_mailer=mailbox, web_clock=lambda: now[0])
    with TestClient(app, base_url=ORIGIN) as client:
        yield SimpleNamespace(db=bank, app=app, client=client, mailbox=mailbox, now=now, auth=app.state.web_auth)


def post(web, path, body=None, *, csrf=None, headers=None):
    request_headers = {'Origin': ORIGIN, **(headers or {})}
    if csrf is not None:
        request_headers['X-CSRF-Token'] = csrf
    request_headers.setdefault('Content-Type', 'application/json')
    return web.client.post('/web/'+path, content=json.dumps({} if body is None else body), headers=request_headers)


def register(web):
    assert post(web, 'auth/register', {'email': EMAIL}).status_code == 200
    token = web.mailbox.messages[-1][2]
    assert post(web, 'auth/verify', {'token': token, 'password': PASSWORD}).status_code == 200


def login(web):
    response = post(web, 'auth/login', {'email': EMAIL, 'password': PASSWORD})
    assert response.status_code == 200
    return web.client.get('/web/auth/me').json()['csrf_token']


def test_email_proof_precedes_account_password_and_login_cookie(web):
    assert post(web, 'auth/register', {'email': EMAIL, 'password': 'attacker-chosen-password'}).status_code == 200
    with closing(get_connection(str(web.db))) as conn:
        assert conn.execute('SELECT count(*) FROM web_accounts').fetchone()[0] == 0
        assert web.mailbox.messages[-1][2] not in '\n'.join(conn.iterdump())
    assert post(web, 'auth/login', {'email': EMAIL, 'password': 'attacker-chosen-password'}).status_code == 401
    proof = web.mailbox.messages[-1][2]
    assert post(web, 'auth/verify', {'token': proof, 'password': PASSWORD}).status_code == 200
    assert post(web, 'auth/verify', {'token': proof, 'password': PASSWORD}).status_code == 400
    assert post(web, 'auth/login', {'email': EMAIL, 'password': 'attacker-chosen-password'}).status_code == 401
    response = post(web, 'auth/login', {'email': EMAIL, 'password': PASSWORD})
    assert response.status_code == 200
    cookie = response.headers['set-cookie']
    assert all(part in cookie for part in ['__Host-psychology_session=', 'HttpOnly', 'Secure', 'SameSite=strict', 'Path=/'])
    assert 'Domain=' not in cookie
    assert response.json() == {'ok': True}  # Session secret never in JSON.
    assert web.client.get('/web/auth/me').json()['needs_identity'] is True
    with closing(get_connection(str(web.db))) as conn:
        stored = conn.execute('SELECT password_hash FROM web_accounts').fetchone()[0]
        assert stored.startswith('$argon2id$v=19$m=65536,t=3,p=1$')
        assert PASSWORD not in '\n'.join(conn.iterdump())


@pytest.mark.parametrize('scenario', ['invalid', 'expired', 'wrong-purpose', 'mail-failure'])
def test_email_proof_errors_never_create_account(web, scenario, caplog):
    caplog.set_level(logging.INFO)
    web.mailbox.fail = scenario == 'mail-failure'
    result = post(web, 'auth/register', {'email': EMAIL})
    if scenario == 'mail-failure':
        assert result.status_code == 503
        assert 'SMTP secret' not in caplog.text
        with closing(get_connection(str(web.db))) as conn:
            assert conn.execute('SELECT count(*) FROM web_mail_tokens').fetchone()[0] == 0
    else:
        token = web.mailbox.messages[-1][2]
        if scenario == 'invalid':
            token = secrets.token_urlsafe(32)
        if scenario == 'expired':
            web.now[0] += 3601
        endpoint = 'auth/reset' if scenario == 'wrong-purpose' else 'auth/verify'
        assert post(web, endpoint, {'token': token, 'password': PASSWORD}).status_code == 400
    with closing(get_connection(str(web.db))) as conn:
        assert conn.execute('SELECT count(*) FROM web_accounts').fetchone()[0] == 0


def test_non_owner_unknown_login_and_disabled_account_are_denied(web):
    response = post(web, 'auth/register', {'email': 'stranger@example.test'})
    assert response.json() == {'ok': True}
    assert web.mailbox.messages == []
    register(web)
    unknown = post(web, 'auth/login', {'email': 'stranger@example.test', 'password': PASSWORD})
    wrong = post(web, 'auth/login', {'email': EMAIL, 'password': 'wrong'})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
    login(web)
    with closing(get_connection(str(web.db))) as conn, conn:
        conn.execute('UPDATE web_accounts SET enabled=0')
    assert web.client.get('/web/auth/me').status_code == 401
    assert post(web, 'auth/login', {'email': EMAIL, 'password': PASSWORD}).status_code == 401


def test_student_pwa_flows_are_dormant_in_production_but_isolated_in_synthetic_policy(web):
    student = 'student@example.test'
    with closing(get_connection(str(web.db))) as conn, conn:
        owner_session = make_attempt(conn)
    assert post(web, 'auth/register', {'email': student}).status_code == 200
    assert web.mailbox.messages == []
    synthetic = create_app(db_path=str(web.db), bot_token=TOKEN,
        web_settings=replace(SETTINGS, student_access_enabled=True), web_mailer=web.mailbox,
        web_clock=lambda: web.now[0])
    with TestClient(synthetic, base_url=ORIGIN) as client:
        student_web = SimpleNamespace(db=web.db, client=client, mailbox=web.mailbox)
        assert post(student_web, 'auth/register', {'email': student}).status_code == 200
        token = web.mailbox.messages[-1][2]
        assert post(student_web, 'auth/verify', {'token': token, 'password': PASSWORD}).status_code == 200
        assert post(student_web, 'auth/login', {'email': student, 'password': PASSWORD}).status_code == 200
        me = client.get('/web/auth/me').json()
        assert me['role'] == 'student' and me['needs_identity'] is True
        assert post(student_web, 'identity/new', csrf=me['csrf_token']).status_code == 200
        assert client.get('/web/quiz/state').status_code == 200
        denied = post(student_web, 'quiz/answer', {'session_id': owner_session, 'question_id': 1, 'selected_option_index': 0}, csrf=me['csrf_token'])
        assert denied.status_code == 403
        assert client.get('/web/quiz/state').json()['runner_state']['state'] == 'setup'
        student_actor = client.get('/web/auth/me').json()['email']
        assert student_actor == student
        issued_cookie = client.cookies.get(SETTINGS.cookie_name)
    # A student session cannot be used after the production gate is closed.
    with closing(get_connection(str(web.db))) as conn:
        assert conn.execute('SELECT count(*) FROM web_accounts WHERE email=?', (student,)).fetchone()[0] == 1
    web.client.cookies.set(SETTINGS.cookie_name, issued_cookie)
    assert web.client.get('/web/auth/me').status_code == 401
    assert post(web, 'auth/login', {'email': student, 'password': PASSWORD}).status_code == 401


def test_runtime_config_rejects_enabling_student_pwa_without_approved_policy(monkeypatch):
    monkeypatch.setenv('PWA_ENABLED', 'true')
    monkeypatch.setenv('PWA_STUDENT_ACCESS_ENABLED', 'true')
    with pytest.raises(RuntimeError, match='approved age/privacy policy'):
        WebSettings.from_env()


@pytest.mark.parametrize('kind', ['missing-origin', 'wrong-origin', 'no-csrf', 'bad-csrf', 'unicode-csrf', 'form', 'cross-site'])
def test_csrf_origin_content_type_guards_prevent_state_changes(web, kind):
    register(web)
    csrf = login(web)
    headers = {'Origin': ORIGIN, 'X-CSRF-Token': csrf}
    if kind == 'missing-origin': headers.pop('Origin')
    if kind == 'wrong-origin': headers['Origin'] = 'https://hostile.example.test'
    if kind == 'no-csrf': headers.pop('X-CSRF-Token')
    if kind == 'bad-csrf': headers['X-CSRF-Token'] = 'wrong'
    # ASGI headers are latin-1; service must also reject arbitrary Unicode safely.
    if kind == 'unicode-csrf':
        with web.auth.transaction() as conn, pytest.raises(AuthError) as error:
            web.auth.authenticate(conn, web.client.cookies.get(SETTINGS.cookie_name), csrf='я', mutation=True)
        assert error.value.status == 403
        return
    if kind == 'cross-site': headers['Sec-Fetch-Site'] = 'cross-site'
    if kind == 'form':
        response = web.client.post('/web/identity/new', data={'x': 'y'}, headers=headers)
        assert response.status_code == 415
    else:
        response = web.client.post('/web/identity/new', json={}, headers=headers)
        assert response.status_code == 403
    assert web.client.get('/web/auth/me').json()['needs_identity'] is True


def test_logout_recovery_expiry_and_process_restart_revoke_sessions(web):
    register(web)
    csrf = login(web)
    old_cookie = web.client.cookies.get(SETTINGS.cookie_name)
    restarted = create_app(db_path=str(web.db), bot_token=TOKEN, web_settings=SETTINGS, web_mailer=web.mailbox, web_clock=lambda: web.now[0])
    with TestClient(restarted, base_url=ORIGIN) as client:
        client.cookies.set(SETTINGS.cookie_name, old_cookie)
        assert client.get('/web/auth/me').status_code == 200
    assert post(web, 'auth/logout', csrf=csrf).status_code == 200
    with web.auth.transaction() as conn, pytest.raises(AuthError):
        web.auth.authenticate(conn, old_cookie)
    login(web)
    session1 = web.client.cookies.get(SETTINGS.cookie_name)
    login(web)
    session2 = web.client.cookies.get(SETTINGS.cookie_name)
    assert session1 != session2
    assert post(web, 'auth/recover', {'email': EMAIL}).status_code == 200
    token = web.mailbox.messages[-1][2]
    assert post(web, 'auth/reset', {'token': token, 'password': NEW_PASSWORD}).status_code == 200
    assert post(web, 'auth/reset', {'token': token, 'password': NEW_PASSWORD}).status_code == 400
    for cookie in (session1, session2):
        with web.auth.transaction() as conn, pytest.raises(AuthError):
            web.auth.authenticate(conn, cookie)
    assert post(web, 'auth/login', {'email': EMAIL, 'password': PASSWORD}).status_code == 401
    assert post(web, 'auth/login', {'email': EMAIL, 'password': NEW_PASSWORD}).status_code == 200
    web.now[0] += IDLE_TTL
    assert web.client.get('/web/auth/me').status_code == 401


def test_absolute_expiry_even_when_session_kept_active(web):
    register(web)
    login(web)
    with closing(get_connection(str(web.db))) as conn, conn:
        conn.execute('UPDATE web_sessions SET last_seen_at=?', (web.now[0]+SESSION_TTL,))
    web.now[0] += SESSION_TTL
    assert web.client.get('/web/auth/me').status_code == 401


def test_login_rate_limit_survives_restart_and_expires(web):
    for _ in range(10):
        assert post(web, 'auth/login', {'email': 'unknown@example.test', 'password': 'wrong'}).status_code == 401
    restarted = WebAuth(str(web.db), SETTINGS, web.mailbox, clock=lambda: web.now[0])
    with pytest.raises(AuthError) as error:
        restarted.login('unknown@example.test', 'wrong')
    assert error.value.status == 429
    web.now[0] += 60
    assert post(web, 'auth/login', {'email': 'unknown@example.test', 'password': 'wrong'}).status_code == 401


def test_link_requires_both_confirmations_preserves_history_and_blocks_replay(web):
    with closing(get_connection(str(web.db))) as conn, conn:
        sid = make_attempt(conn)
        answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=1, selected_option_index=0)
        before = {k: v for k,v in user_state(conn).items() if not k.startswith('web_')}
    register(web)
    csrf = login(web)
    token = post(web, 'link/start', csrf=csrf).json()['code']
    assert post(web, 'link/complete', csrf=csrf).status_code == 400
    telegram = SimpleNamespace(id=42, username=None, first_name='Original user', last_name=None)
    assert web.auth.propose_telegram_link(token, telegram) == EMAIL
    assert post(web, 'link/complete', csrf=csrf).status_code == 400
    with pytest.raises(AuthError):
        web.auth.confirm_telegram_link(token, 9999)
    web.auth.confirm_telegram_link(token, 42)
    confirmed = web.client.get('/web/auth/me').json()
    assert confirmed['link_confirmed'] is True
    assert confirmed['link_target'] == {'telegram_id':42,'username':None,'display_name':'Original user'}
    assert post(web, 'link/complete', csrf=csrf).status_code == 200
    assert post(web, 'link/complete', csrf=csrf).status_code == 400
    with pytest.raises(AuthError):
        web.auth.confirm_telegram_link(token, 42)
    me = web.client.get('/web/auth/me').json()
    assert me['telegram_linked'] is True and me['needs_identity'] is False
    state = web.client.get('/web/quiz/state').json()
    assert state['runner_state']['progress']['answered_count'] == 1
    assert state['recent_answer_feedback']['selected_option_index'] == 0
    with closing(get_connection(str(web.db))) as conn:
        assert conn.execute('SELECT user_id FROM web_accounts').fetchone()[0] == 1
        assert {k: v for k,v in user_state(conn).items() if not k.startswith('web_')} == before


@pytest.mark.parametrize('invalidate', ['expiry', 'logout', 'recovery', 'different-session', 'fresh-actor'])
def test_link_invalidated_by_lifecycle_and_session_binding(web, invalidate):
    register(web)
    csrf = login(web)
    token = post(web, 'link/start', csrf=csrf).json()['code']
    telegram = SimpleNamespace(id=42, username=None, first_name='Original user', last_name=None)
    web.auth.propose_telegram_link(token, telegram)
    web.auth.confirm_telegram_link(token, 42)
    if invalidate == 'expiry': web.now[0] += 601
    if invalidate == 'logout': post(web, 'auth/logout', csrf=csrf)
    if invalidate == 'recovery':
        post(web, 'auth/recover', {'email': EMAIL})
        post(web, 'auth/reset', {'token': web.mailbox.messages[-1][2], 'password': NEW_PASSWORD})
    if invalidate == 'different-session': csrf = login(web)
    if invalidate == 'fresh-actor': post(web, 'identity/new', csrf=csrf)
    assert post(web, 'link/complete', csrf=csrf).status_code in {400,401}
    with closing(get_connection(str(web.db))) as conn:
        actor = conn.execute('SELECT user_id FROM web_accounts').fetchone()[0]
        assert actor is None if invalidate != 'fresh-actor' else actor != 1


def test_occupied_identity_and_cross_user_data_cannot_be_claimed(web):
    register(web)
    csrf = login(web)
    token = post(web, 'link/start', csrf=csrf).json()['code']
    with closing(get_connection(str(web.db))) as conn, conn:
        conn.execute('INSERT INTO web_accounts(email,password_hash,user_id,verified_at,created_at) VALUES(?,?,?,?,?)',
                     ('other@example.test','unused-synthetic-hash',1,web.now[0],web.now[0]))
        sid = make_attempt(conn)
    telegram = SimpleNamespace(id=42, username=None, first_name='Original user', last_name=None)
    with pytest.raises(AuthError, match='identity_unavailable'):
        web.auth.propose_telegram_link(token, telegram)
    assert post(web, 'identity/new', {'telegram_user_id': 42, 'user_id': 1}, csrf=csrf).status_code == 200
    assert web.client.get('/web/quiz/state').json()['runner_state']['state'] == 'setup'
    response = post(web, 'quiz/answer', {'session_id':sid,'question_id':1,'selected_option_index':0,'user_id':1}, csrf=csrf)
    assert response.status_code == 403 and 'feedback' not in response.json()
    with closing(get_connection(str(web.db))) as conn:
        assert conn.execute('SELECT count(*) FROM quiz_answers').fetchone()[0] == 0


def test_concurrent_token_consumption_and_migration_preserve_auth_data(web, tmp_path):
    post(web, 'auth/register', {'email': EMAIL})
    token = web.mailbox.messages[-1][2]
    def consume():
        try:
            web.auth.set_password(token, PASSWORD, 'register')
            return 'ok'
        except AuthError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: consume(), range(2)))
    assert sorted(outcomes) == ['invalid_token', 'ok']
    csrf = login(web)
    post(web, 'link/start', csrf=csrf)
    backup = backup_and_rehearse(web.db, tmp_path / 'auth-backup')
    with closing(get_connection(str(web.db))) as conn:
        migrate_auth_schema(conn)
    verify_preserved(web.db, backup)
    with closing(get_connection(str(web.db))) as conn, conn:
        conn.execute('UPDATE web_accounts SET password_hash=?', ('changed',))
    with pytest.raises(RuntimeError, match='pre-existing user state'):
        verify_preserved(web.db, backup)


def test_auth_api_errors_limits_and_logs_do_not_echo_secrets(web, caplog):
    caplog.set_level(logging.INFO)
    secret = 'private-marker-123'
    for action, body, status in [('auth/login', [], 400), ('auth/login', {'password': '\ud800'*16}, 401),
                                  ('quiz/answer', {}, 401), ('unknown', {'secret':secret}, 404)]:
        result = post(web, action, body)
        assert result.status_code == status
        assert result.headers['cache-control'] == 'no-store'
        assert 'access-control-allow-origin' not in result.headers
    assert post(web, 'auth/login?token='+secret, {'password':secret}).status_code == 400
    assert web.client.post('/web/auth/login', content='x'*16385, headers={'Origin':ORIGIN,'Content-Type':'application/json'}).status_code == 413
    assert web.client.post('/web/auth/login', content='{', headers={'Origin':ORIGIN,'Content-Type':'application/json'}).status_code == 400
    # Exercise real access logger's installed filter with a secret in a raw URL.
    logging.getLogger('uvicorn.access').info('%s %s %s %s %s', 'private-ip', 'POST', '/web/auth/login?token='+secret, '1.1', 400)
    assert secret not in caplog.text and 'private-ip' not in caplog.text
    assert PASSWORD not in caplog.text


def test_disabled_web_routes_do_not_touch_database(bank):
    with TestClient(create_app(db_path=str(bank), bot_token=TOKEN)) as client:
        assert client.get('/web/auth/me').status_code == 404
        assert client.post('/web/auth/register', json={'email':EMAIL}).status_code == 404
