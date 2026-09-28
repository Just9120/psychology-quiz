from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from threading import Barrier
import pytest

from app.db import get_connection, upsert_approved_questions, start_quiz_session, store_session_questions, save_quiz_answer
from app.miniapp_api import build_answer_response, build_state_response
from app.quiz_service import QuizSetupError, answer_quiz, prepare_quiz, start_prepared_quiz, start_confirmed_quiz, quiz_state
from app.progress_service import overview
from app.classic_quiz_handlers import claim_quiz_replacement
from app.repetition import quiz_queue
from datetime import date, timedelta
from tests.test_attempt_content import bank, make_attempt, TOKEN, OLD
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


def test_unknown_answer_is_durable_gap_with_feedback_and_due_review(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = make_attempt(conn, questions=(1,))
        saved = answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=1, selected_option_index=-1)
        assert saved['submission_status'] == 'accepted'
        assert saved['feedback']['knowledge_gap'] is True
        assert saved['feedback']['selected_option_text'] == 'Не знаю'
        assert saved['feedback']['correct_option_text'] == OLD['options'][0]
        assert answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=1,
                           selected_option_index=0)['submission_status'] == 'duplicate'
        assert conn.execute('SELECT selected_option_index,is_correct FROM quiz_answers').fetchone()[:] == (-1, 0)
    with closing(get_connection(str(bank))) as conn:
        assert quiz_state(conn, actor_user_id=1)['recent_answer_feedback']['knowledge_gap'] is True
        assert overview(conn, 1)['summary']['knowledge_gaps'] == 1
        assert quiz_queue(conn, 1, today=date.today() + timedelta(days=2))[0]['reason'] == 'error'


def test_personal_recommendations_require_fifty_distinct_questions(bank):
    items = [{**OLD, 'id': f'distinct-{index}', 'question': f'Distinct question {index}?'}
             for index in range(50)]
    with closing(get_connection(str(bank))) as conn, conn:
        upsert_approved_questions(conn, items, authoritative=True)
        ids = [row[0] for row in conn.execute("SELECT id FROM questions WHERE status='approved' ORDER BY id")]
        sid = start_quiz_session(conn, 1, 1)
        store_session_questions(conn, sid, ids)
        for qid in ids[:49]:
            save_quiz_answer(conn, sid, qid, 1)
        before = overview(conn, 1)['recommendations']
        assert before == {'eligible': False, 'distinct_questions': 49, 'items': []}
        save_quiz_answer(conn, sid, ids[49], 1)
        after = overview(conn, 1)['recommendations']
        assert after['eligible'] is True and after['distinct_questions'] == 50
        assert after['items'][0]['topic'] == OLD['category']
        repeated = start_quiz_session(conn, 1, 1)
        store_session_questions(conn, repeated, ids[:1])
        save_quiz_answer(conn, repeated, ids[0], 1)
        assert overview(conn, 1)['recommendations']['distinct_questions'] == 50
        upsert_approved_questions(conn, [{**items[0], 'question': 'Revised distinct question?'}])
        revised = start_quiz_session(conn, 1, 1)
        store_session_questions(conn, revised, ids[:1])
        save_quiz_answer(conn, revised, ids[0], 1)
        assert overview(conn, 1)['recommendations']['distinct_questions'] == 50
        assert overview(conn, 2)['recommendations']['eligible'] is False


def test_recommendation_threshold_retains_answered_glossary_term_after_removal(bank, monkeypatch):
    from app import glossary_service, repetition
    from tests.test_glossary_runtime import make_glossary_entry

    entries = [make_glossary_entry(str(index), f'Meaning {index}') for index in range(5)]
    monkeypatch.setattr(glossary_service, 'GLOSSARY_TOPICS', [('fixture_topic', 'Fixture')])
    monkeypatch.setattr(glossary_service, 'load_glossary_entries', lambda _: entries)
    items = [{**OLD, 'id': f'distinct-{index}', 'question': f'Distinct question {index}?'}
             for index in range(49)]
    with closing(get_connection(str(bank))) as conn, conn:
        upsert_approved_questions(conn, items, authoritative=True)
        ids = [row[0] for row in conn.execute("SELECT id FROM questions WHERE status='approved' ORDER BY id")]
        sid = start_quiz_session(conn, 1, 1)
        store_session_questions(conn, sid, ids)
        for qid in ids:
            save_quiz_answer(conn, sid, qid, 1)
        assert overview(conn, 1)['recommendations']['distinct_questions'] == 49
        question = glossary_service.start(conn, 1, 'fixture_topic', 5)['current_question']
        glossary_service.answer(conn, 1, question['session_id'], -1, question['step_id'])
        monkeypatch.setattr(repetition, 'load_glossary_entries', lambda _: [])
        result = overview(conn, 1)['recommendations']
        assert result['eligible'] is True and result['distinct_questions'] == 50
        assert overview(conn, 2)['recommendations']['distinct_questions'] == 0


def test_new_quiz_requires_confirmation_of_current_actor_attempt(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        prepared = prepare_quiz(conn, {'quiz_mode': 'all', 'category_ids': [],
                                      'question_count': None, 'difficulty': 'any'})
        first = start_confirmed_quiz(conn, actor_user_id=1, prepared=prepared, payload={})
        sid = first['session']['session_id']
        for payload in ({}, {'replace_active': True, 'expected_session_id': sid + 1}):
            with pytest.raises(QuizSetupError):
                start_confirmed_quiz(conn, actor_user_id=1, prepared=prepared, payload=payload)
            assert quiz_state(conn, actor_user_id=1)['runner_state']['session']['session_id'] == sid
        second = start_confirmed_quiz(conn, actor_user_id=1, prepared=prepared,
                                      payload={'replace_active': True, 'expected_session_id': sid})
        assert second['session']['session_id'] != sid
        assert conn.execute('SELECT status FROM quiz_sessions WHERE id=?', (sid,)).fetchone()[0] == 'abandoned'


def test_chat_replacement_is_actor_scoped_and_requires_current_attempt(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = make_attempt(conn, questions=(1,))
        assert claim_quiz_replacement(conn, 2, sid) is False
        assert claim_quiz_replacement(conn, 1, None) is False
        assert claim_quiz_replacement(conn, 1, sid + 1) is False
        assert conn.execute('SELECT status FROM quiz_sessions WHERE id=?', (sid,)).fetchone()[0] == 'in_progress'
        assert claim_quiz_replacement(conn, 1, sid) is True
        assert conn.execute('SELECT status FROM quiz_sessions WHERE id=?', (sid,)).fetchone()[0] == 'abandoned'
