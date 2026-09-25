from contextlib import closing
from types import SimpleNamespace

from app.db import create_or_load_user, get_connection
from tests.test_attempt_content import bank
from tests.test_progress import record, reset_payload
from tests.test_web_auth import web, post, register, login


def test_progress_api_shared_telegram_history_and_guards(web):
    assert web.client.get('/web/progress/overview').status_code == 401
    assert web.client.get('/web/progress/mastery').status_code == 401
    register(web)
    csrf = login(web)
    assert post(web, 'progress/history', csrf=csrf).status_code == 409
    # The same actor is established by the real proof-based linking boundary.
    code = post(web, 'link/start', csrf=csrf).json()['code']
    web.auth.propose_telegram_link(code, SimpleNamespace(id=42, username=None, first_name='Original user', last_name=None))
    web.auth.confirm_telegram_link(code, 42)
    assert post(web, 'link/complete', csrf=csrf).status_code == 200
    with closing(get_connection(str(web.db))) as conn, conn:
        sid = record(conn)
        other = create_or_load_user(conn, 98, None, None, None)['id']
        foreign = record(conn, actor=other)
    overview = web.client.get('/web/progress/overview')
    assert overview.status_code == 200 and overview.json()['summary']['answered'] == 1
    mastery = web.client.get('/web/progress/mastery')
    assert mastery.status_code == 200
    assert mastery.json()['assessed_count'] == 1
    assert mastery.json()['items'][0]['status'] == 'insufficient_data'
    assert mastery.headers['cache-control'] == 'no-store'
    assert overview.headers['cache-control'] == 'no-store'
    assert post(web, 'progress/history').status_code == 403
    assert web.client.get('/web/progress/overview?user_id=2').status_code == 400
    assert web.client.get('/web/progress/overview', headers={'Origin': 'https://foreign.test'}).status_code == 403
    history = post(web, 'progress/history', {'user_id': other}, csrf=csrf).json()
    assert [item['session_id'] for item in history['items']] == [sid]
    assert post(web, 'progress/attempt', {'session_id': foreign}, csrf=csrf).status_code == 404
    assert post(web, 'progress/attempt', {'session_id': 999999}, csrf=csrf).status_code == 404
    assert post(web, 'progress/attempt', {'session_id': True}, csrf=csrf).status_code == 400
    errors = post(web, 'progress/errors', csrf=csrf).json()
    assert errors['total'] == 1 and errors['latest_session_id'] == sid
    payload = {'expected_session_id': sid, 'replace_active': False, 'question_count': 5}
    assert post(web, 'progress/train', payload).status_code == 403
    trained = post(web, 'progress/train', payload, csrf=csrf)
    assert trained.status_code == 200
    assert post(web, 'progress/train', payload, csrf=csrf).json()['error'] == 'practice_changed'
    question = trained.json()['runner_state']['current_question']
    # Reload/state resumes the persisted attempt; no new training state store.
    assert web.client.get('/web/quiz/state').json()['runner_state']['current_question'] == question
    answer = {key: question[key] for key in ('session_id', 'question_id')}
    assert post(web, 'quiz/answer', {**answer, 'selected_option_index': 0}, csrf=csrf).status_code == 200
    assert post(web, 'progress/errors', csrf=csrf).json()['total'] == 0
    assert web.client.get('/web/progress/overview').json()['summary']['accuracy'] == 50
    assert post(web, 'auth/logout', csrf=csrf).status_code == 200
    assert post(web, 'progress/attempt', {'session_id': sid}, csrf=csrf).status_code == 401


def test_empty_training_and_bad_payload_do_not_create_attempt(web):
    register(web)
    csrf = login(web)
    assert post(web, 'identity/new', csrf=csrf).status_code == 200
    for payload in ({}, {'expected_session_id': None, 'replace_active': True, 'question_count': True},
                    {'expected_session_id': -1, 'replace_active': False}):
        assert post(web, 'progress/train', payload, csrf=csrf).status_code == 400
    result = post(web, 'progress/train', {'expected_session_id': None, 'replace_active': False}, csrf=csrf)
    assert result.status_code == 409 and result.json()['error'] == 'no_errors'
    assert post(web, 'progress/history', csrf=csrf).json()['items'] == []


def test_reset_api_auth_csrf_actor_binding_and_readback(web):
    assert post(web, 'progress/reset-preview', {'scope': 'all'}).status_code == 401
    register(web)
    csrf = login(web)
    assert post(web, 'identity/new', csrf=csrf).status_code == 200
    with closing(get_connection(str(web.db))) as conn, conn:
        actor = conn.execute('SELECT user_id FROM web_accounts').fetchone()[0]
        own = record(conn, actor=actor)
        foreign = record(conn, actor=1)
    before = post(web, 'progress/reset-preview', {'scope': 'all', 'user_id': 1}, csrf=csrf)
    assert before.status_code == 200 and before.headers['cache-control'] == 'no-store'
    assert before.json()['answers'] == 1
    payload = {**reset_payload(before.json()), 'user_id': 1}
    assert post(web, 'progress/reset-confirm', payload).status_code == 403
    assert web.client.post('/web/progress/reset-confirm', json=payload, headers={'Origin': 'https://foreign.test', 'X-CSRF-Token': csrf}).status_code == 403
    assert post(web, 'progress/reset-confirm', {**payload, 'confirm': False}, csrf=csrf).status_code == 400
    assert post(web, 'progress/attempt', {'session_id': own}, csrf=csrf).status_code == 200
    assert post(web, 'progress/reset-confirm', payload, csrf=csrf).status_code == 200
    assert post(web, 'progress/reset-confirm', payload, csrf=csrf).status_code == 409
    assert post(web, 'progress/history', csrf=csrf).json()['items'] == []
    with closing(get_connection(str(web.db))) as conn:
        assert conn.execute('SELECT count(*) FROM quiz_answers WHERE session_id=?', (foreign,)).fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM web_accounts').fetchone()[0] == 1
    assert web.client.get('/web/auth/me').status_code == 200
