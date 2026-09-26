from contextlib import closing
from dataclasses import asdict
from datetime import date
import json

from app.glossary import GLOSSARY_TOPICS, load_glossary_entries
from app.glossary_projection import projected_questions
from app.db import (create_or_load_user, get_connection, start_quiz_session,
                    store_session_questions, upsert_approved_questions)
from app.mastery import glossary_states, quiz_states
from app.quiz_service import answer_quiz, prepare_quiz
from app.repetition import queue
from scripts import init_db, seed_questions
from scripts.audit_question_bank import build_report, has_blockers


def test_published_glossary_projection_is_stable_and_contains_only_approved_terms():
    first = projected_questions()
    assert first == projected_questions()
    assert len(first) == sum(len(load_glossary_entries(topic_id) or []) for topic_id, _ in GLOSSARY_TOPICS)
    assert len({item['id'] for item in first}) == len(first)
    by_id = {item['id']: item for item in first}
    for topic_id, title in GLOSSARY_TOPICS:
        for entry in load_glossary_entries(topic_id) or []:
            item = by_id[f'glossary:{topic_id}:{entry.id}']
            assert item['kind'] == 'glossary' and item['status'] == 'approved'
            assert item['category'] == title and item['explanation'] == entry.definition
            assert item['source_ref'] in entry.source_refs
            assert len(item['options']) == len(set(item['options'])) == 4
            assert item['options'][item['correct_option_index']] == entry.short_definition


def test_canonical_seed_serves_glossary_alongside_theory_and_case_without_parity_drift(tmp_path, monkeypatch):
    target = tmp_path / 'quiz.sqlite3'
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('DB_PATH', str(target))
    assert init_db.main() == 0
    assert seed_questions.main() == 0
    with closing(get_connection(str(target))) as conn:
        before = [(row[0], row[1]) for row in conn.execute(
            "SELECT id,external_id FROM questions WHERE kind='glossary' ORDER BY external_id")]
        assert len(before) == len(projected_questions())
        assert {row[0] for row in conn.execute("SELECT DISTINCT kind FROM questions WHERE status='approved'")} == {
            'theory', 'glossary', 'case'}
        for mode in ('all', 'adaptive'):
            prepared = prepare_quiz(conn, {
                'quiz_mode': mode, 'category_ids': [], 'question_count': 5,
                'difficulty': 'any', 'content_kinds': ['theory', 'glossary', 'case'],
            }, actor_user_id=1)
            selected_kinds = {conn.execute('SELECT kind FROM questions WHERE id=?', (qid,)).fetchone()[0]
                              for qid in prepared.question_ids}
            assert len(prepared.question_ids) == 5
            assert selected_kinds == {'theory', 'glossary', 'case'}
    assert not has_blockers(build_report(str(target)))
    assert seed_questions.main() == 0
    with closing(get_connection(str(target))) as conn:
        assert [(row[0], row[1]) for row in conn.execute(
            "SELECT id,external_id FROM questions WHERE kind='glossary' ORDER BY external_id")] == before
    assert not has_blockers(build_report(str(target)))


def test_legacy_and_shared_quiz_answers_form_one_private_term_schedule(tmp_path, monkeypatch):
    target = tmp_path / 'quiz.sqlite3'
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('DB_PATH', str(target))
    assert init_db.main() == seed_questions.main() == 0
    topic_id, title = GLOSSARY_TOPICS[0]
    entry = load_glossary_entries(topic_id)[0]
    external_id = f'glossary:{topic_id}:{entry.id}'
    with closing(get_connection(str(target))) as conn, conn:
        actor = create_or_load_user(conn, 742, None, None, None)['id']
        other = create_or_load_user(conn, 743, None, None, None)['id']
        question_id = conn.execute('SELECT id FROM questions WHERE external_id=?',
                                   (external_id,)).fetchone()[0]
        legacy_answer = {'1': {'response': {'feedback': {'is_correct': True}},
                               'answered_at': '2026-09-01T10:00:00Z'}}
        conn.execute('''INSERT INTO glossary_sessions
            (id,user_id,topic_id,topic_title,status,snapshot,state,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)''',
            ('legacy-term', actor, topic_id, title, 'completed',
             json.dumps({'questions': [{'entry': asdict(entry)}]}),
             json.dumps({'answers': legacy_answer}),
             '2026-09-01T10:00:00Z', '2026-09-01T10:00:00Z'))
        correct = conn.execute('''SELECT option_index FROM question_options
            WHERE question_id=? AND is_correct=1''', (question_id,)).fetchone()[0]
        for day in (4, 11):
            session_id = start_quiz_session(conn, actor, None)
            store_session_questions(conn, session_id, [question_id])
            assert answer_quiz(conn, actor_user_id=actor, session_id=session_id,
                               question_id=question_id,
                               selected_option_index=correct)['submission_status'] == 'accepted'
            conn.execute('UPDATE quiz_answers SET answered_at=? WHERE session_id=?',
                         (f'2026-09-{day:02d}T10:00:00Z', session_id))
        items = [item for item in queue(conn, actor, today=date(2026, 9, 20))['items']
                 if item.get('term_id') == entry.id]
        assert len(items) == 1
        assert items[0]['kind'] == 'glossary' and items[0]['question_id'] == question_id
        assert items[0]['correct_streak'] == 3 and items[0]['due_on'] == '2026-09-25'
        term = next(item for item in glossary_states(conn, actor)['items']
                    if item['term_id'] == entry.id)
        assert term['status'] == 'mastered'
        assert not any(item['question_id'] == question_id for item in quiz_states(conn, actor)['items'])
        assert queue(conn, other, today=date(2026, 9, 20))['items'] == []
        assert glossary_states(conn, other)['items'] == []
        original = next(item for item in projected_questions() if item['id'] == external_id)
        upsert_approved_questions(conn, [{**original, 'explanation': 'Новая редакция определения'}])
        revised = next(item for item in queue(conn, actor, today=date(2026, 9, 20))['items']
                       if item.get('term_id') == entry.id)
        assert revised['reason'] == 'new_edition'
        assert next(item for item in glossary_states(conn, actor)['items']
                    if item['term_id'] == entry.id)['status'] == 'insufficient_data'
