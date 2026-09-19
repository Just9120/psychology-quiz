from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from threading import Barrier

from app.db import get_connection
from app.miniapp_api import build_answer_response, build_state_response
from app.quiz_service import answer_quiz, prepare_quiz, start_prepared_quiz, quiz_state
from tests.test_attempt_content import bank, make_attempt, TOKEN
from tests.test_miniapp_api import _make_init_data


def test_independent_actor_quiz_without_telegram_and_restart(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        actor = conn.execute('INSERT INTO users DEFAULT VALUES').lastrowid
        prepared = prepare_quiz(conn, {'quiz_mode': 'all', 'category_ids': [], 'question_count': None, 'difficulty': 'any'})
        state = start_prepared_quiz(conn, actor_user_id=actor, prepared=prepared)
        sid = state['session']['session_id']
        question = state['current_question']['question_id']
        answer_quiz(conn, actor_user_id=actor, session_id=sid, question_id=question, selected_option_index=0)
    # New connection represents a fresh API process: no in-memory actor/attempt state.
    with closing(get_connection(str(bank))) as conn, conn:
        restored = quiz_state(conn, actor_user_id=actor)
        assert restored['runner_state']['progress']['answered_count'] == 1
        assert restored['recent_answer_feedback']['selected_option_index'] == 0
        assert quiz_state(conn, actor_user_id=1)['runner_state']['state'] == 'setup'
        forbidden = answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=question, selected_option_index=0)
        assert forbidden == {'ok': True, 'submission_status': 'forbidden'}


def test_cross_client_conflicting_concurrent_answers_return_one_recorded_result(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = make_attempt(conn, questions=(1,))
    barrier = Barrier(2)
    def telegram():
        barrier.wait()
        status, _, body = build_answer_response(str(bank), TOKEN, _make_init_data(TOKEN, {'id': 42, 'first_name': 'Original user'}), json.dumps({
            'session_id': sid, 'question_id': 1, 'selected_option_index': 0}).encode())
        assert status == 200
        return json.loads(body)
    def web():
        barrier.wait()
        with closing(get_connection(str(bank))) as conn, conn:
            return answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=1, selected_option_index=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tg_future, web_future = pool.submit(telegram), pool.submit(web)
        results = [tg_future.result(), web_future.result()]
    assert {result['submission_status'] for result in results} == {'accepted', 'duplicate'}
    assert results[0]['feedback'] == results[1]['feedback']
    assert all(result['runner_state']['state'] == 'completed' for result in results)
    with closing(get_connection(str(bank))) as conn, conn:
        assert conn.execute('SELECT count(*) FROM quiz_answers').fetchone()[0] == 1
        saved = conn.execute('SELECT selected_option_index,is_correct FROM quiz_answers').fetchone()
        assert conn.execute('SELECT score FROM quiz_sessions WHERE id=?', (sid,)).fetchone()[0] == saved['is_correct']
        # Final-answer lost reply, different retry choice, and backend restart.
        retry = answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=1, selected_option_index=1-saved[0])
        assert retry['submission_status'] == 'duplicate'
        assert retry['feedback']['selected_option_index'] == saved[0]
    status, _, body = build_state_response(str(bank), TOKEN, _make_init_data(TOKEN, {'id': 42, 'first_name': 'Original user'}))
    assert status == 200
    assert json.loads(body)['runner_state']['state'] == 'completed'


def test_future_question_cannot_be_answered_before_current(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = make_attempt(conn)
        result = answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=2, selected_option_index=0)
        assert result['submission_status'] == 'stale_question'
        assert conn.execute('SELECT count(*) FROM quiz_answers').fetchone()[0] == 0
