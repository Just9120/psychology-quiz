from contextlib import closing
import json

import pytest

from app import curriculum
from app.attempt_content import capture_question, get_attempt_content
from app.db import get_connection, upsert_approved_questions
from app.quiz_service import prepare_quiz, QuizSetupError, quiz_setup_options
from app.study_navigation import question_scopes
from tests.test_attempt_content import bank, make_attempt, OLD, OTHER, NEW


TOPIC = 't_0123456789ab'


@pytest.fixture
def mapped(bank, monkeypatch):
    with closing(get_connection(str(bank))) as conn:
        sha = capture_question(conn, 1)[1]
    catalog = {'disciplines': {'original': {'title': OLD['category'], 'modules': ['module2', 'module3']}},
               'topics': {TOPIC: {'title': 'Уточнение запроса', 'discipline_id': 'original',
                                  'source': {'source_id': 'private-source-do-not-export'}}},
               'editions': {sha: {'topic_id': TOPIC}}}
    monkeypatch.setattr(curriculum, 'load_catalog', lambda: catalog)
    return bank


def test_current_exact_edition_has_reviewed_topic_and_multimodule_paths_without_private_fields(mapped):
    with closing(get_connection(str(mapped))) as conn:
        navigation, scopes = question_scopes(conn)
        item = next(item for item in navigation if item['category_id'] == 1)
        assert item == {'category_id': 1, 'discipline_id': 'original', 'title': OLD['category'],
                        'modules': ['module2', 'module3'],
                        'topics': [{'id': TOPIC, 'title': 'Уточнение запроса', 'question_count': 1}]}
        assert scopes[TOPIC] == {1} and scopes['unclassified:2'] == {2}
        public = json.dumps(quiz_setup_options(conn), ensure_ascii=False)
        assert 'private-source' not in public and 'snapshot_sha256' not in public
        assert quiz_setup_options(conn)['categories'][0].keys() == {'id', 'name', 'topic_id', 'module'}


def test_topic_filter_limits_bank_wide_pool_and_does_not_rewrite_old_snapshots(mapped):
    with closing(get_connection(str(mapped))) as conn, conn:
        sid = make_attempt(conn)
        before = get_attempt_content(conn, sid, 1)
        payload = {'quiz_mode': 'all', 'category_ids': [], 'question_count': 5,
                   'difficulty': 'any', 'topic_ids': [TOPIC]}
        assert prepare_quiz(conn, payload).question_ids == (1,)
        upsert_approved_questions(conn, [NEW, OTHER], authoritative=True)
        navigation, scopes = question_scopes(conn)
        assert TOPIC not in scopes and scopes['unclassified:1'] == {1}
        assert get_attempt_content(conn, sid, 1) == before
        with pytest.raises(QuizSetupError, match='invalid_setup'):
            prepare_quiz(conn, payload)


@pytest.mark.parametrize('topics,categories', [([], []), ([TOPIC, TOPIC], []),
    (['source-secret'], []), ([TOPIC], [2]), (['unclassified:999'], []),
    ([True], []), ([{'id': TOPIC}], [])])
def test_malformed_unknown_or_out_of_discipline_scope_cannot_create_attempt(mapped, topics, categories):
    with closing(get_connection(str(mapped))) as conn, conn:
        with pytest.raises(QuizSetupError, match='invalid_setup'):
            prepare_quiz(conn, {'quiz_mode': 'all', 'category_ids': categories,
                               'question_count': 5, 'difficulty': 'any', 'topic_ids': topics})
        assert conn.execute('SELECT count(*) FROM quiz_sessions').fetchone()[0] == 0


def test_legacy_setup_and_unclassified_leaf_remain_available(mapped):
    with closing(get_connection(str(mapped))) as conn, conn:
        payload = {'quiz_mode': 'all', 'category_ids': [], 'question_count': None, 'difficulty': 'any'}
        assert set(prepare_quiz(conn, payload).question_ids) == {1, 2}
        assert prepare_quiz(conn, dict(payload, topic_ids=['unclassified:2'])).question_ids == (2,)
        conn.execute("UPDATE questions SET status='draft' WHERE id=2")
        assert 'unclassified:2' not in question_scopes(conn)[1]


def test_topic_selection_respects_count_without_kind_filter_and_adaptive_never_leaks_other_topics(mapped):
    with closing(get_connection(str(mapped))) as conn, conn:
        documents = [dict(OLD, id=f'scoped-{index}') for index in range(8)]
        upsert_approved_questions(conn, [OLD, OTHER, *documents], authoritative=True)
        for row in conn.execute('SELECT id FROM questions WHERE category_id=1'):
            curriculum.load_catalog()['editions'][capture_question(conn, row[0])[1]] = {'topic_id': TOPIC}
        payload = {'quiz_mode': 'all', 'category_ids': [], 'question_count': 5,
                   'difficulty': 'any', 'topic_ids': [TOPIC]}
        selected = prepare_quiz(conn, payload).question_ids
        assert len(selected) == 5 and 2 not in selected
        adaptive = prepare_quiz(conn, dict(payload, quiz_mode='adaptive', content_kinds=['theory']), actor_user_id=1)
        assert len(adaptive.question_ids) == 5 and 2 not in adaptive.question_ids
