from contextlib import closing
import copy
import json

import pytest

from app import curriculum, progress_service as progress
from app.attempt_content import capture_question
from app.content_publication import fingerprint, load_policy
from app.db import get_connection, start_quiz_session, upsert_approved_questions, create_or_load_user
from app.quiz_service import answer_quiz
from scripts.validate_learning_reviews import inventory
from tests.test_attempt_content import bank, OLD, OTHER, NEW
from tests.test_progress import record
from tests.test_web_auth import web, post, register, login
from types import SimpleNamespace


@pytest.fixture
def mapped(bank, monkeypatch):
    source = {"source_id": "synthetic", "modified_time": "2026-09-21", "snapshot_sha256": "a" * 64}
    data = {"schema_version": 1, "disciplines": {"first": {"title": OLD["category"]}, "second": {"title": OTHER["category"]}},
            "topics": {"t_111111111111": {"title": "Первая тема", "discipline_id": "first", "source": source},
                       "t_222222222222": {"title": "Вторая тема", "discipline_id": "second", "source": source}}, "editions": {}}
    with closing(get_connection(str(bank))) as conn:
        for qid, topic, q in ((1, "t_111111111111", OLD), (2, "t_222222222222", OTHER)):
            data["editions"][capture_question(conn, qid)[1]] = {"external_id": q["id"], "topic_id": topic,
                                                              "item_sha256": fingerprint(q), "locator": "section 1"}
    curriculum.validate_catalog(data)
    monkeypatch.setattr(curriculum, "load_catalog", lambda: data)
    return data


def test_curriculum_preserves_editions_and_explicit_unknown_history(bank, mapped):
    with closing(get_connection(str(bank))) as conn, conn:
        mixed = record(conn, qids=(1, 2), choices=(0, 1))
        foreign = create_or_load_user(conn, 91, None, None, None)["id"]
        record(conn, actor=foreign, choices=(0,))
        encoded, digest = capture_question(conn, 1)
        legacy = start_quiz_session(conn, 1, None)
        conn.execute("""INSERT INTO quiz_session_questions
            (session_id,question_id,order_index,content_snapshot,content_sha256,snapshot_provenance)
            VALUES (?,1,1,?,?,'legacy_backfill_current')""", (legacy, encoded, digest))
        answer_quiz(conn, actor_user_id=1, session_id=legacy, question_id=1, selected_option_index=0)
        upsert_approved_questions(conn, [NEW, OTHER])
        changed = record(conn, choices=(0,))
        stats = progress.overview(conn, 1)
        assert stats["summary"]["answered"] == 4
        first, second = stats["curriculum"]["disciplines"]
        assert (first["answered"], first["correct"], first["unmapped_answers"]) == (2, 1, 1)
        assert first["topics"][0]["answered"] == 1
        assert second["answered"] == 1
        assert stats["curriculum"]["unmapped"]["answered"] == 2
        assert [x["session_id"] for x in progress.history(conn, 1, scope="topic:t_111111111111")["items"]] == [mixed]
        assert [x["session_id"] for x in progress.history(conn, 1, scope="discipline:first")["items"]] == [changed, mixed]
        assert [x["session_id"] for x in progress.history(conn, 1, scope="unmapped")["items"]] == [changed, legacy]
        # A filter selects whole attempts; their other answers remain available.
        assert len(progress.attempt(conn, 1, mixed)["items"]) == 2
        assert progress.attempt(conn, 1, mixed)["items"][0]["curriculum"]["topic_title"] == "Первая тема"
        assert progress.attempt(conn, 1, legacy)["items"][0]["curriculum"]["discipline_id"] is None
        assert progress.attempt(conn, 1, changed)["items"][0]["curriculum"]["topic_id"] is None


def test_curriculum_filters_paginate_and_keep_full_denominators(bank, mapped):
    with closing(get_connection(str(bank))) as conn, conn:
        sessions = [record(conn, choices=(i % 2,)) for i in range(23)]
        conn.execute("UPDATE quiz_answers SET answered_at='2026-09-20 01:00:00'")
        conn.execute("UPDATE quiz_answers SET answered_at='2026-09-21 01:00:00' WHERE session_id=?", (sessions[-1],))
        scope = "topic:t_111111111111"
        first = progress.history(conn, 1, scope=scope)
        second = progress.history(conn, 1, first["next_before"], scope=scope)
        assert [x["session_id"] for x in first["items"] + second["items"]] == list(reversed(sessions))
        assert second["next_before"] is None
        topic = progress.overview(conn, 1)["curriculum"]["disciplines"][0]["topics"][0]
        assert (topic["answered"], topic["correct"]) == (23, 12)
        assert [x["answered"] for x in topic["days"]] == [22, 1]
        empty = progress.overview(conn, 9999)["curriculum"]
        assert empty["disciplines"][0]["accuracy"] is None
        assert empty["unmapped"]["answered"] == 0
        for invalid in ([], {}, 1, "topic:missing", "discipline:first' OR 1=1"):
            with pytest.raises(progress.ProgressError, match="invalid_curriculum_scope"):
                progress.history(conn, 1, scope=invalid)


def test_catalog_is_grounded_in_exact_reviewed_primary_editions(tmp_path):
    catalog = curriculum.load_catalog()
    reviews = json.loads((curriculum.ROOT / 'content/learning-quality-reviews.json').read_text(encoding='utf-8'))['items']
    items = inventory()
    registry = {item['id']: item for item in json.loads((curriculum.ROOT / 'content/topics.json').read_text(encoding='utf-8'))}
    assert len(catalog['disciplines']) == 8 and len(catalog['editions']) == 297
    assert {k: v['title'] for k, v in catalog['disciplines'].items()} == {k: v['title'] for k, v in registry.items() if v['question_file']}
    with closing(get_connection(str(tmp_path / 'catalog.sqlite3'))) as conn, conn:
        conn.executescript((curriculum.ROOT / 'sql/schema.sql').read_text(encoding='utf-8'))
        upsert_approved_questions(conn, [v for k, v in items.items() if k.startswith('questions:')], authoritative=True)
        actual = {row['external_id']: capture_question(conn, row['id'])[1] for row in conn.execute('SELECT id,external_id FROM questions')}
        for sha, item in catalog['editions'].items():
            key = 'questions:' + item['external_id']
            review = reviews[key]
            topic = catalog['topics'][item['topic_id']]
            source = load_policy().sources[topic['source']['source_id']]
            assert actual[item['external_id']] == sha
            assert fingerprint(items[key]) == item['item_sha256'] == review['item_sha256']
            assert review['source_support'] == 'supported'
            assert topic['discipline_id'] == review['discipline_id']
            assert source['kind'] == 'learning_material' and source['readable'] is True
            assert 'глоссар' not in source['title'].lower()
            assert any(all(e[k] == v for k, v in topic['source'].items()) and e['locator'] == item['locator'] for e in review['sources'])


def test_catalog_rejects_orphan_and_ambiguous_identities(mapped):
    invalid = copy.deepcopy(mapped)
    invalid['topics'].clear()
    with pytest.raises(ValueError):
        curriculum.validate_catalog(invalid)


def test_curriculum_api_filters_verified_actor_and_rejects_invalid_scope(web, mapped):
    register(web)
    csrf = login(web)
    code = post(web, 'link/start', csrf=csrf).json()['code']
    web.auth.propose_telegram_link(code, SimpleNamespace(id=42, username=None, first_name='Original user', last_name=None))
    web.auth.confirm_telegram_link(code, 42)
    assert post(web, 'link/complete', csrf=csrf).status_code == 200
    with closing(get_connection(str(web.db))) as conn, conn:
        sid = record(conn)
        other = create_or_load_user(conn, 98, None, None, None)['id']
        record(conn, actor=other)
    payload = {'scope': 'topic:t_111111111111', 'user_id': other}
    result = post(web, 'progress/history', payload, csrf=csrf)
    assert result.status_code == 200
    assert result.headers['cache-control'] == 'no-store'
    assert [item['session_id'] for item in result.json()['items']] == [sid]
    assert post(web, 'progress/history', payload).status_code == 403
    assert post(web, 'progress/history', {'scope': ['unmapped']}, csrf=csrf).status_code == 400
    overview = web.client.get('/web/progress/overview').json()
    assert overview['curriculum']['disciplines'][0]['answered'] == 1
    invalid = copy.deepcopy(mapped)
    invalid['disciplines']['second']['title'] = OLD['category']
    with pytest.raises(ValueError):
        curriculum.validate_catalog(invalid)
