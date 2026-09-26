from contextlib import closing

from app.glossary import GLOSSARY_TOPICS, load_glossary_entries
from app.glossary_projection import projected_questions
from app.db import get_connection
from app.quiz_service import prepare_quiz
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
