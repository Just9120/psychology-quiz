from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from app import glossary_service as glossary, learning_reset
from app.db import get_connection, create_or_load_user
from app.miniapp_fastapi import create_app
from tests.test_attempt_content import bank
from tests.test_glossary_runtime import make_glossary_entry
from tests.test_miniapp_api import _make_init_data
from tests.test_progress import reset_payload


def call(bank, operation, *args, actor=1, **kwargs):
    with closing(get_connection(str(bank))) as conn, conn:
        return operation(conn, actor, *args, **kwargs)


@pytest.fixture
def session(bank, monkeypatch):
    entries = [make_glossary_entry(str(i), f'Meaning {i}') for i in range(5)]
    monkeypatch.setattr(glossary, 'GLOSSARY_TOPICS', [('fixture_topic', 'Fixture')])
    monkeypatch.setattr(glossary, 'load_glossary_entries', lambda _: entries)
    return call(bank, glossary.start, 'fixture_topic', 5)['current_question']


def correct_index(question):
    expected = 'Meaning ' + question['term'].removeprefix('Term ')
    return next(option['option_index'] for option in question['options'] if option['option_text'] == expected)


def test_repeat_next_preserves_displayed_options_and_scoring(bank, session):
    sid, step = session['session_id'], session['step_id']
    for _ in range(4):
        assert call(bank, glossary.advance, sid, step)['current_question'] == session
    selected = correct_index(session)
    feedback = call(bank, glossary.answer, sid, selected, step)
    assert feedback['feedback']['is_correct'] is True
    feedback['feedback']['is_correct'] = False
    assert call(bank, glossary.answer, sid, selected, step)['feedback']['is_correct'] is True
    next_state = call(bank, glossary.advance, sid, step)
    assert next_state['current_question']['step_id'] == 2
    assert call(bank, glossary.advance, sid, step) == next_state


def test_concurrent_answer_and_next_commit_only_once(bank, session):
    sid, step, selected = session['session_id'], session['step_id'], correct_index(session)
    with ThreadPoolExecutor(max_workers=6) as pool:
        answers = list(pool.map(lambda _: call(bank, glossary.answer, sid, selected, step), range(12)))
        advances = list(pool.map(lambda _: call(bank, glossary.advance, sid, step), range(12)))
    assert all(answer == answers[0] for answer in answers)
    assert all(state == advances[0] for state in advances)
    with closing(get_connection(str(bank))) as conn:
        data = json.loads(conn.execute('SELECT state FROM glossary_sessions WHERE id=?', (sid,)).fetchone()[0])
        assert data['score'] == 1 and data['step'] == 2 and len(data['answers']) == 1


def test_delayed_old_operations_do_not_change_another_answered_step(bank, session):
    sid = session['session_id']
    first = call(bank, glossary.answer, sid, correct_index(session), 1)
    advance = call(bank, glossary.advance, sid, 1)
    second = advance['current_question']
    call(bank, glossary.answer, sid, correct_index(second), 2)
    assert call(bank, glossary.answer, sid, correct_index(session), 1) == first
    assert call(bank, glossary.advance, sid, 1) == advance
    assert call(bank, glossary.state)['feedback']['step_id'] == 2
    assert call(bank, glossary.advance, sid, 2)['current_question']['step_id'] == 3


def test_conflicting_answer_wrong_owner_and_future_step_are_rejected(bank, session):
    sid, selected = session['session_id'], correct_index(session)
    with closing(get_connection(str(bank))) as conn, conn:
        other = create_or_load_user(conn, 43, None, None, None)['id']
    for actor, choice, step in [(other, selected, 1), (1, selected, 2), (1, True, 1), (1, selected, True)]:
        with pytest.raises(glossary.GlossaryError):
            call(bank, glossary.answer, sid, choice, step, actor=actor)
    with pytest.raises(glossary.GlossaryError):
        call(bank, glossary.advance, sid, 1, actor=other)
    call(bank, glossary.answer, sid, selected, 1)
    with pytest.raises(glossary.GlossaryError):
        call(bank, glossary.answer, sid, (selected + 1) % 4, 1)


def test_complete_result_and_restart_retries_are_stable(bank, session):
    sid, question = session['session_id'], session
    for step in range(1, 6):
        call(bank, glossary.answer, sid, correct_index(question), step)
        state = call(bank, glossary.advance, sid, step)
        question = state.get('current_question')
    assert state['state'] == 'completed' and state['result'] == {'score': 5, 'total_questions': 5}
    assert call(bank, glossary.advance, sid, 5) == state
    with ThreadPoolExecutor(max_workers=6) as pool:
        restarted = list(pool.map(lambda _: call(bank, glossary.restart, sid), range(12)))
    assert all(item == restarted[0] for item in restarted)
    with closing(get_connection(str(bank))) as conn:
        assert conn.execute('SELECT count(*) FROM glossary_sessions').fetchone()[0] == 2


def test_saved_snapshot_survives_new_process_and_content_unavailable(bank, session, monkeypatch):
    sid = session['session_id']
    call(bank, glossary.answer, sid, correct_index(session), 1)
    expected = call(bank, glossary.state)
    # Use stdin for the target so a DSN is never a process argument or error log.
    code = "import sys,json; from contextlib import closing; from app.db import get_connection; from app.glossary_service import state;\nwith closing(get_connection(sys.stdin.read())) as c, c: print(json.dumps(state(c,1)))"
    result = subprocess.run([sys.executable, '-c', code], input=str(bank), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, 'isolated glossary reader failed'
    assert json.loads(result.stdout) == expected
    monkeypatch.setattr(glossary, 'load_glossary_entries', lambda _: None)
    assert call(bank, glossary.state) == expected
    assert call(bank, glossary.advance, sid, 1)['current_question']['step_id'] == 2


def test_confirmed_replacement_reset_and_lost_operations_preserve_other_data(bank, session):
    sid = session['session_id']
    call(bank, glossary.answer, sid, correct_index(session), 1)
    preview = call(bank, learning_reset.preview, {'scope': 'topic', 'topic': 'Fixture'})
    assert preview['glossary_answers'] == 1 and preview['attempts'] == 1
    for expected, confirmed in [(None, True), (sid, False)]:
        with pytest.raises(glossary.GlossaryError):
            call(bank, glossary.start, 'fixture_topic', 5, expected_session_id=expected, replace_active=confirmed)
    new = call(bank, glossary.start, 'fixture_topic', 5, expected_session_id=sid, replace_active=True)
    with pytest.raises(Exception, match='reset_changed'):
        call(bank, learning_reset.confirm, reset_payload(preview))
    preview = call(bank, learning_reset.preview, {'scope': 'topic', 'topic': 'Fixture'})
    assert preview['attempts'] == 2
    call(bank, learning_reset.confirm, reset_payload(preview))
    assert call(bank, glossary.state) == {'state': 'idle'}
    for old in (sid, new['session_id']):
        with pytest.raises(glossary.GlossaryError): call(bank, glossary.restart, old)
        with pytest.raises(glossary.GlossaryError): call(bank, glossary.answer, old, 0, 1)
    with closing(get_connection(str(bank))) as conn:
        assert conn.execute('SELECT private_note FROM user_literature_progress').fetchone()[0] == 'Private note'
        assert conn.execute('SELECT first_name FROM users WHERE id=1').fetchone()[0] == 'Original user'


def test_transaction_failure_rolls_back_answer(bank, session):
    with pytest.raises(RuntimeError):
        with closing(get_connection(str(bank))) as conn, conn:
            glossary.answer(conn, 1, session['session_id'], correct_index(session), 1)
            raise RuntimeError('simulated failure')
    assert call(bank, glossary.state)['current_question'] == session
    assert call(bank, glossary.state)['state'] == 'in_progress'


def test_topic_and_all_reset_preserve_foreign_glossary_and_rollback(bank, session, monkeypatch):
    monkeypatch.setattr(glossary, 'GLOSSARY_TOPICS', [('fixture_topic', 'Fixture'), ('second_topic', 'Second')])
    with closing(get_connection(str(bank))) as conn, conn:
        other = create_or_load_user(conn, 43, None, None, None)['id']
    foreign = call(bank, glossary.start, 'fixture_topic', 5, actor=other)
    second = call(bank, glossary.start, 'second_topic', 5,
                  expected_session_id=session['session_id'], replace_active=True)
    topic = call(bank, learning_reset.preview, {'scope': 'topic', 'topic': 'Fixture'})
    with pytest.raises(RuntimeError, match='interrupted'):
        with closing(get_connection(str(bank))) as conn, conn:
            learning_reset.confirm(conn, 1, reset_payload(topic))
            raise RuntimeError('interrupted reset')
    assert call(bank, learning_reset.preview, {'scope': 'topic', 'topic': 'Fixture'}) == topic
    call(bank, learning_reset.confirm, reset_payload(topic))
    assert call(bank, glossary.state) == second
    assert call(bank, glossary.state, actor=other) == foreign
    all_learning = call(bank, learning_reset.preview, {'scope': 'all'})
    call(bank, learning_reset.confirm, reset_payload(all_learning))
    assert call(bank, glossary.state) == {'state': 'idle'}
    assert call(bank, glossary.state, actor=other) == foreign
    with closing(get_connection(str(bank))) as conn:
        assert conn.execute('SELECT private_note FROM user_literature_progress').fetchone()[0] == 'Private note'


@pytest.mark.parametrize('dedicated', [False, True])
def test_api_retries_and_missing_step_are_consistent(bank, session, dedicated):
    token = '123:synthetic'
    client = TestClient(create_app(db_path=str(bank), bot_token=token))
    headers = {'Authorization': 'tma ' + _make_init_data(token, {'id': 42})}
    sid = session['session_id']
    def request(action, extra):
        path = f'/miniapp/glossary/{action}' if dedicated else '/miniapp/answer'
        return client.post(path, headers=headers, json={'mode': 'glossary', 'action': action, 'session_id': sid, **extra})
    for action in ('answer', 'next'):
        for step in (None, True, [], 0):
            response = request(action, {'selected_option_index': correct_index(session), 'step_id': step})
            assert response.status_code == 400 and response.json()['error'] == 'glossary_step_required'
    payload = {'step_id': 1, 'selected_option_index': correct_index(session)}
    answer = request('answer', payload)
    assert answer.status_code == 200 and answer.json()['glossary_state']['feedback']['is_correct']
    assert request('answer', payload).json() == answer.json()
    advanced = request('next', {'step_id': 1})
    assert advanced.status_code == 200
    assert request('next', {'step_id': 1}).json() == advanced.json()
    with closing(get_connection(str(bank))) as conn:
        assert conn.execute('SELECT first_name FROM users WHERE id=1').fetchone()[0] == 'Original user'
