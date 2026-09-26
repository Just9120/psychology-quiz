from contextlib import closing
from types import SimpleNamespace

from app.db import get_connection, upsert_approved_questions
from app.glossary import GLOSSARY_TOPICS
from app.glossary_projection import projected_questions
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


def test_projected_term_quiz_answer_and_review_are_shared_by_linked_clients(web):
    register(web)
    csrf = login(web)
    code = post(web, 'link/start', csrf=csrf).json()['code']
    web.auth.propose_telegram_link(code, SimpleNamespace(
        id=42, username=None, first_name='Original user', last_name=None))
    web.auth.confirm_telegram_link(code, 42)
    assert post(web, 'link/complete', csrf=csrf).status_code == 200
    item = projected_questions()[0]
    with closing(get_connection(str(web.db))) as conn, conn:
        upsert_approved_questions(conn, [item])
        question_id = conn.execute('SELECT id FROM questions WHERE external_id=?',
                                   (item['id'],)).fetchone()[0]
    headers = {'Authorization': 'tma ' + _make_init_data(TOKEN, {'id': 42})}
    other = {'Authorization': 'tma ' + _make_init_data(TOKEN, {'id': 99})}
    setup = post(web, 'quiz/setup', {
        'quiz_mode': 'all', 'category_ids': [], 'question_count': 5,
        'difficulty': 'any', 'content_kinds': ['glossary'],
    }, csrf=csrf)
    assert setup.status_code == 200
    current = setup.json()['runner_state']['current_question']
    assert current['question_id'] == question_id
    session_id = current['session_id']
    telegram_state = web.client.get('/miniapp/state', headers=headers)
    assert telegram_state.status_code == 200
    assert telegram_state.json()['runner_state']['current_question'] == current
    assert web.client.get('/miniapp/state', headers=other).json()['runner_state']['state'] == 'setup'
    answer = web.client.post('/miniapp/answer', headers=headers, json={
        'session_id': session_id, 'question_id': question_id,
        'selected_option_index': item['correct_option_index'],
    })
    assert answer.status_code == 200
    assert answer.json()['feedback']['explanation'] == item['explanation']
    assert 'source_ref' not in answer.json()['feedback']
    assert web.client.get('/web/quiz/state').json()['recent_answer_feedback'] == {
        **answer.json()['feedback'], 'question_id': question_id,
    }
    web_review = web.client.get('/web/progress/review').json()
    telegram_review = web.client.get('/miniapp/learning/review', headers=headers).json()
    assert web_review == telegram_review
    topic_id = item['id'].split(':')[1]
    entry_id = item['id'].split(':', 2)[2]
    assert [row['question_id'] for row in web_review['items']
            if row.get('topic_id') == topic_id and row.get('term_id') == entry_id] == [question_id]
    assert web.client.get('/miniapp/learning/review', headers=other).json()['items'] == []
