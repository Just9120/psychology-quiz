from contextlib import closing
from types import SimpleNamespace

from app.db import get_connection
from app.glossary import GLOSSARY_TOPICS
from tests.test_miniapp_api import _make_init_data
from tests.test_attempt_content import bank, TOKEN
from tests.test_web_auth import web, post, register, login


def test_shared_glossary_actor_and_web_auth_guards(web):
    assert web.client.get('/web/glossary/state').status_code == 401
    register(web)
    csrf = login(web)
    assert web.client.get('/web/glossary/state').status_code == 409
    code = post(web, 'link/start', csrf=csrf).json()['code']
    web.auth.propose_telegram_link(code, SimpleNamespace(id=42, username=None, first_name='Original user', last_name=None))
    web.auth.confirm_telegram_link(code, 42)
    assert post(web, 'link/complete', csrf=csrf).status_code == 200
    assert web.client.get('/web/glossary/options').status_code == 200
    payload = {'topic_id': GLOSSARY_TOPICS[0][0], 'question_count': 5, 'actor': 999}
    assert post(web, 'glossary/setup', payload).status_code == 403
    assert post(web, 'glossary/setup', payload, csrf=csrf, headers={'Origin':'https://foreign.test'}).status_code == 403
    started = post(web, 'glossary/setup', payload, csrf=csrf)
    assert started.status_code == 200 and started.headers['cache-control'] == 'no-store'
    q = started.json()['glossary_state']['current_question']
    headers = {'Authorization': 'tma ' + _make_init_data(TOKEN, {'id':42})}
    other = {'Authorization': 'tma ' + _make_init_data(TOKEN, {'id':99})}
    submit = {'mode':'glossary', 'action':'answer', 'session_id':q['session_id'], 'step_id':1, 'selected_option_index':0}
    assert web.client.post('/miniapp/answer', headers=other, json=submit).status_code == 409
    answer = web.client.post('/miniapp/answer', headers=headers, json=submit)
    assert answer.status_code == 200
    restored = web.client.get('/web/glossary/state').json()['glossary_state']
    assert restored['feedback'] == answer.json()['glossary_state']['feedback']
    assert restored['current_question'] == q
    assert post(web, 'glossary/answer', submit, csrf=csrf).json()['glossary_state'] == answer.json()['glossary_state']
    before = post(web, 'progress/reset-preview', {'scope':'all','topic':None}, csrf=csrf).json()
    assert before['glossary_answers'] == 1
    advanced = post(web, 'glossary/next', {'session_id':q['session_id'],'step_id':1}, csrf=csrf)
    assert advanced.status_code == 200
    saved = web.client.post('/miniapp/answer', headers=headers, json={'mode':'glossary','action':'state'}).json()['glossary_state']
    assert saved == advanced.json()['glossary_state']
    with closing(get_connection(str(web.db))) as conn:
        assert conn.execute('SELECT user_id FROM glossary_sessions').fetchone()[0] == 1
