from contextlib import closing
from datetime import datetime
import json

from app import achievements, glossary_service as glossary, learning_goals, quiz_service
from app.db import create_or_load_user, get_connection, upsert_approved_questions
from app.glossary import GLOSSARY_TOPICS
from app.glossary_projection import projected_questions
from tests.test_attempt_content import bank
from tests.test_progress import record


def finish_glossary(conn, monkeypatch, at, *, actor=1, topic=None):
    monkeypatch.setattr(glossary, '_now', lambda: at)
    started = glossary.start(conn, actor, topic or GLOSSARY_TOPICS[0][0], 5)
    sid = started['session_id']
    snapshot = json.loads(conn.execute('SELECT snapshot FROM glossary_sessions WHERE id=?', (sid,)).fetchone()[0])
    for step, question in enumerate(snapshot['questions'], 1):
        glossary.answer(conn, actor, sid, question['correct_option_index'], step)
        glossary.advance(conn, actor, sid, step)
    return sid, snapshot


def study_goal(conn, actor=1, date='2026-09-25T12:00:00+00:00'):
    return learning_goals.overview(conn, actor, now=datetime.fromisoformat(date))['goals'][0]


def test_glossary_study_and_regularity_survive_restart_replay_and_actor_isolation(bank, monkeypatch):
    with closing(get_connection(str(bank))) as conn, conn:
        learning_goals.set_target(conn, 1, {'goal_kind': 'study', 'weekly_target': 1})
        first, _ = finish_glossary(conn, monkeypatch, '2026-09-14T12:00:00Z')
        second, snapshot = finish_glossary(conn, monkeypatch, '2026-09-21T12:00:00Z')
        foreign = create_or_load_user(conn, 991, None, None, None)['id']
        finish_glossary(conn, monkeypatch, '2026-09-21T12:00:00Z', actor=foreign)
        assert study_goal(conn)['completed'] == 1
        assert study_goal(conn)['reached'] is True
        result = achievements.refresh(conn, 1)
        assert {a['kind'] for a in result['achievements']} == {'new_topic', 'regularity'}
        assert not [a for a in achievements.refresh(conn, foreign)['achievements'] if a['kind'] == 'regularity']

        monkeypatch.setattr(glossary, '_now', lambda: '2026-10-19T12:00:00Z')
        glossary.answer(conn, 1, second, snapshot['questions'][-1]['correct_option_index'], 5)
        glossary.advance(conn, 1, second, 5)
        new = glossary.restart(conn, 1, first)['session_id']
        glossary.restart(conn, 1, first)  # Same child attempt, no new event.
        assert study_goal(conn)['completed'] == 1
        assert study_goal(conn, date='2026-10-20T12:00:00Z')['completed'] == 0
        assert achievements.refresh(conn, 1) == result
        assert conn.execute('SELECT status FROM glossary_sessions WHERE id=?', (new,)).fetchone()[0] == 'in_progress'


def test_mixed_attempts_count_once_and_share_glossary_topic_across_editions(bank, monkeypatch):
    with closing(get_connection(str(bank))) as conn, conn:
        first, snapshot = finish_glossary(conn, monkeypatch, '2026-09-14T12:00:00Z')
        entry = snapshot['questions'][0]['entry']
        external_id = f"glossary:{entry['topic_id']}:{entry['id']}"
        question = next(q for q in projected_questions() if q['id'] == external_id)
        # A later captured edition keeps the topic identity; answers/history of
        # the dedicated earlier attempt remain unchanged.
        upsert_approved_questions(conn, [{**question, 'explanation': 'Synthetic revised definition'}], authoritative=False)
        qid = conn.execute('SELECT id FROM questions WHERE external_id=?', (external_id,)).fetchone()[0]
        started = quiz_service.start_prepared_quiz(conn, actor_user_id=1,
            prepared=quiz_service.PreparedQuiz(None, (), None, (qid,)))
        sid = started['session']['session_id']
        quiz_service.answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=qid,
                                 selected_option_index=question['correct_option_index'])
        conn.execute("UPDATE quiz_sessions SET finished_at='2026-09-21T12:00:00Z' WHERE id=?", (sid,))
        finish_glossary(conn, monkeypatch, '2026-09-22T12:00:00Z')
        assert study_goal(conn)['completed'] == 2  # Two attempts, not six term answers.
        result = achievements.refresh(conn, 1)
        topics = [a for a in result['achievements'] if a['kind'] == 'new_topic']
        assert topics == [{'kind': 'new_topic', 'evidence_key': f"glossary:{entry['topic_id']}",
                           'earned_at': '2026-09-14T12:00:00+00:00'}]
        regularity = next(a for a in result['achievements'] if a['kind'] == 'regularity')
        assert regularity['earned_at'] == '2026-09-21T12:00:00+00:00'
        assert json.loads(conn.execute('SELECT snapshot FROM glossary_sessions WHERE id=?', (first,)).fetchone()[0]) == snapshot


def test_week_boundaries_use_utc_completion_not_last_answer_or_updated_time(bank, monkeypatch):
    with closing(get_connection(str(bank))) as conn, conn:
        finish_glossary(conn, monkeypatch, '2026-09-21T00:15:00+03:00')  # Sunday UTC.
        sid = record(conn)
        conn.execute("UPDATE quiz_sessions SET finished_at='2026-09-28T00:15:00+03:00' WHERE id=?", (sid,))  # Sunday UTC.
        monkeypatch.setattr(glossary, '_now', lambda: '2026-09-27T23:59:00Z')
        current = glossary.start(conn, 1, GLOSSARY_TOPICS[0][0], 5)
        sid = current['session_id']
        questions = json.loads(conn.execute('SELECT snapshot FROM glossary_sessions WHERE id=?', (sid,)).fetchone()[0])['questions']
        for step, question in enumerate(questions, 1):
            glossary.answer(conn, 1, sid, question['correct_option_index'], step)
            if step < 5:
                glossary.advance(conn, 1, sid, step)
        assert study_goal(conn)['completed'] == 1  # Last answer alone is not completion.
        monkeypatch.setattr(glossary, '_now', lambda: '2026-09-28T00:01:00Z')
        glossary.advance(conn, 1, sid, 5)
        assert study_goal(conn)['completed'] == 1
        assert study_goal(conn, date='2026-09-28T01:00:00Z')['completed'] == 1


def test_legacy_completion_is_preserved_before_restart_but_unknown_time_is_not_invented(bank, monkeypatch):
    with closing(get_connection(str(bank))) as conn, conn:
        sid, _ = finish_glossary(conn, monkeypatch, '2026-09-21T12:00:00Z')
        state = json.loads(conn.execute('SELECT state FROM glossary_sessions WHERE id=?', (sid,)).fetchone()[0])
        state.pop('completed_at')  # Existing completed, never restarted record.
        conn.execute('UPDATE glossary_sessions SET state=? WHERE id=?', (json.dumps(state), sid))
        assert study_goal(conn)['completed'] == 1
        monkeypatch.setattr(glossary, '_now', lambda: '2026-10-19T12:00:00Z')
        child = glossary.restart(conn, 1, sid)['session_id']
        saved = json.loads(conn.execute('SELECT state FROM glossary_sessions WHERE id=?', (sid,)).fetchone()[0])
        assert saved['completed_at'] == '2026-09-21T12:00:00Z'
        assert study_goal(conn)['completed'] == 1
        saved.pop('completed_at')  # Pre-fix record already restarted: original date lost.
        conn.execute('UPDATE glossary_sessions SET state=? WHERE id=?', (json.dumps(saved), sid))
        assert study_goal(conn)['completed'] == 0
        assert study_goal(conn, date='2026-10-20T12:00:00Z')['completed'] == 0
        glossary.restart(conn, 1, child)  # Abandoned incomplete child is never counted.
        assert study_goal(conn, date='2026-10-20T12:00:00Z')['completed'] == 0


def test_existing_regularity_is_not_duplicated_when_old_glossary_history_becomes_visible(bank, monkeypatch):
    with closing(get_connection(str(bank))) as conn, conn:
        for at in ('2026-09-28T12:00:00Z', '2026-10-05T12:00:00Z'):
            sid = record(conn)
            conn.execute('UPDATE quiz_sessions SET finished_at=? WHERE id=?', (at, sid))
        previous = [a for a in achievements.refresh(conn, 1)['achievements'] if a['kind'] == 'regularity']
        assert len(previous) == 1
        for at in ('2026-09-14T12:00:00Z', '2026-09-21T12:00:00Z'):
            finish_glossary(conn, monkeypatch, at)
        current = [a for a in achievements.refresh(conn, 1)['achievements'] if a['kind'] == 'regularity']
        assert current == previous
