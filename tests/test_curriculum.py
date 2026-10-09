from contextlib import closing
import copy
import json

import pytest

from app import curriculum, progress_service as progress
from app.attempt_content import capture_question
from app.content_publication import fingerprint, load_policy
from app.db import get_connection, start_quiz_session, upsert_approved_questions, create_or_load_user
from app.learning_schema import migrate_learning_schema
from app.identity_schema import migrate_identity_schema
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


def test_curriculum_overview_keeps_reviewed_cross_module_membership(bank, mapped, monkeypatch):
    mapped["disciplines"]["first"].update(module=None, modules=["module1", "module4"])
    monkeypatch.setattr("app.literature.load_topic_registry", lambda: {"first": {"module": "module1"}})
    with closing(get_connection(str(bank))) as conn:
        first = next(item for item in curriculum.overview(conn, 1)["disciplines"]
                     if item["scope"] == "discipline:first")
    assert first["module"] is None
    assert first["modules"] == ["module1", "module4"]


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


def test_unknown_answer_counts_as_topic_gap_and_daily_practice(bank, mapped):
    with closing(get_connection(str(bank))) as conn, conn:
        first = record(conn, choices=(-1,))
        later = record(conn, choices=(0,))
        foreign = create_or_load_user(conn, 91, None, None, None)["id"]
        record(conn, actor=foreign, choices=(-1,))
        conn.execute("UPDATE quiz_answers SET answered_at='2026-09-20 12:00:00' WHERE session_id=?", (first,))
        conn.execute("UPDATE quiz_answers SET answered_at='2026-09-21 12:00:00' WHERE session_id=?", (later,))

        stats = progress.overview(conn, 1)
        assert stats["summary"]["knowledge_gaps"] == 1
        assert (stats["summary"]["answered"], stats["summary"]["correct"]) == (2, 1)
        topic = stats["curriculum"]["disciplines"][0]["topics"][0]
        assert (topic["answered"], topic["correct"], topic["accuracy"]) == (2, 1, 50.0)
        assert [(day["day"], day["correct"], day["answered"]) for day in topic["days"]] == [
            ("2026-09-20", 0, 1), ("2026-09-21", 1, 1),
        ]
        assert [item["session_id"] for item in progress.history(conn, 1, scope=topic["scope"])["items"]] == [later, first]
        assert progress.attempt(conn, 1, first)["items"][0]["selected_option_text"] == "Не знаю"


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
    core = json.loads((curriculum.ROOT / 'content/curriculum.json').read_text(encoding='utf-8'))
    assert len(core['disciplines']) == 13 and len(catalog['editions']) == 940
    assert catalog['editions'] == core['editions']
    assert curriculum.load_reviewed_catalog() == core
    assert len(catalog['disciplines']) == 21 and len(catalog['topics']) == 168
    assert all(catalog['topics'][key] == value for key, value in core['topics'].items())
    private_bindings = curriculum.load_private_bindings(catalog)
    # Source-free lesson bindings can add learning contours outside the core graph.
    assert ({k: v['title'] for k, v in core['disciplines'].items()} | {
        'psychodiagnostics': 'Психодиагностика',
        'quantitative_methods': 'Количественные методы исследования',
        'family_psychology': 'Семейная психология',
        'turning_point': 'Точка поворота. 5 шагов',
        'social_psychology': 'Социальная психология',
        'organizational_psychology': 'Организационная психология',
        'developmental_psychology': 'Возрастная психология',
        'personality_psychology': 'Психология личности и индивидуальных различий',
        'psycholinguistics': 'Психолингвистика',
        'personal_brand': 'Личный бренд и самопрезентация',
        'professional_legal_ethics': 'Правовые и этические основы профессиональной деятельности психолога-консультанта',
        'bonus_lessons': 'Бонусные уроки',
    }) == {
        k: v['title'] for k, v in registry.items()
        if k != 'cases' and (any(contour in v['available_contours']
                                for contour in ('questions', 'glossary'))
                              or k in {'personality_psychology', 'social_psychology',
                                       'family_psychology', 'psycholinguistics'})
    }
    assert registry['cases']['title'] == 'Кейс' and 'cases' not in catalog['disciplines']
    with closing(get_connection(str(tmp_path / 'catalog.sqlite3'))) as conn, conn:
        conn.executescript((curriculum.ROOT / 'sql/schema.sql').read_text(encoding='utf-8'))
        migrate_identity_schema(conn)
        migrate_learning_schema(conn)
        upsert_approved_questions(conn, [v for k, v in items.items() if k.startswith('questions:')], authoritative=True)
        actual = {row['external_id']: capture_question(conn, row['id'])[1] for row in conn.execute('SELECT id,external_id FROM questions')}
        historical = set()
        retired = set()
        for sha, item in catalog['editions'].items():
            key = 'questions:' + item['external_id']
            topic = catalog['topics'][item['topic_id']]
            if item['item_sha256'] != fingerprint(items[key]):
                # Prior immutable editions remain mapped for historical attempts.
                if items[key]['status'] != 'approved':
                    retired.add(item['external_id'])
                    assert item['external_id'] not in actual
                    assert item['locator']
                    continue
                historical.add(item['external_id'])
                assert actual[item['external_id']] != sha
                assert item['locator']
                continue
            assert actual[item['external_id']] == sha
            if sha in private_bindings:
                certificate = private_bindings[sha]
                assert certificate['topic_id'] == item['topic_id']
                assert item['locator'] == ('private certificate:' if 'signature' in certificate else 'private review:') + key
                assert load_policy().can_publish('questions', items[key])
                assert registry[topic['discipline_id']]['title'] == items[key]['category']
                continue
            source = load_policy().sources[topic['source']['source_id']]
            if item['locator'] == 'private certificate:' + key:
                assert load_policy().can_publish('questions', items[key])
                assert item['item_sha256'] == fingerprint(items[key])
                assert registry[topic['discipline_id']]['title'] == items[key]['category']
                assert source['kind'] == 'learning_material' and source['readable'] is True
                assert all(topic['source'][field] == source[field]
                           for field in ('modified_time', 'snapshot_sha256'))
                continue
            review = reviews[key]
            assert fingerprint(items[key]) == item['item_sha256'] == review['item_sha256']
            assert review['source_support'] == 'supported'
            assert topic['discipline_id'] == review['discipline_id']
            assert source['kind'] == 'learning_material' and source['readable'] is True
            assert 'глоссар' not in source['title'].lower()
            assert any(all(e[k] == v for k, v in topic['source'].items()) and e['locator'] == item['locator'] for e in review['sources'])
        assert historical == {'m1_vnd_002', 'm1_intro_054', 'm2_exp_012', 'm2_exp_058',
                              'm1_vnd_034', 'm1_vnd_047', 'm1_vnd_048',
                              'm1_intro_035', 'm2_exp_030', 'm2_exp_046',
                              'm3_psychological_consulting_039',
                              'm1_phys_028', 'm1_phys_050', 'm1_phys_019',
                              'm1_phys_002', 'm1_phys_003', 'm1_phys_004',
                              'm1_phys_006', 'm1_phys_009', 'm1_phys_010',
                              'm1_phys_014', 'm1_phys_015', 'm1_phys_025',
                              'm1_phys_026', 'm1_phys_032', 'm1_phys_044',
                              'm1_phys_022', 'm1_phys_031', 'm1_phys_038',
                              'm1_phys_053', 'm1_phys_008', 'm1_phys_017', 'm1_gp_014', 'm1_phys_058', 'm1_phys_061'} | {
                                  f'm1_intro_{n:03}' for n in (
                                      1, 2, 3, 4, 5, 6, 8, 11, 12, 13, 14, 15, 16, 17, 18, 20,
                                      19, 21, 22, 24, 26, 27, 28, 29, 30, 33, 34, 36, 37, 38, 41, 42, 44, 46, 48)
                              } | {
                                  f'm1_gp_{n:03}' for n in (
                                      1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 21,
                                      23, 24, 25, 33, 35, 36, 37, 38, 41,
                                      32, 42, 43, 44, 45, 47, 48, 50, 52, 53, 56)
                              } | {
                                  f'm2_exp_{number:03}' for number in (
                                      6, 7, 8, 20, 21, 22, 23, 41, 42, 43,
                                      44, 45, 47, 48, 62, 63, 64, 66, 67, 68,
                                      69, 70, 71, 72, 73, 74, 75, 76, 77, 78,
                                      79, 80, 81, 94, 98, 100, 101, 102, 103,
                                      104, 106, 107, 110, 112, 113, 114, 116,
                                      117, 118)
                              } | {
                                  f'm2_exp_{number:03}' for number in (
                                      10, 11, 12, 13, 14, 15, 16, 17, 24,
                                      49, 50, 51, 52, 53, 54, 55, 56,
                                      57, 65, 108)
                              } | {
                                  f'm1_vnd_{number:03}' for number in (
                                      6, 7, 9, 10, 12, 13, 14, 16, 17, 21,
                                      22, 23, 24, 35, 39, 41, 42, 44, 45, 49)
                              } | {
                                  f'm3_psychological_consulting_{number:03}'
                                  for number in (2, 3, 10, 12, 20, 21, 23, 26, 27, 28, 29, 31, 32, 33, 35, 36,
                                                 37, 38, 40, 41, 42, 43, 44, 46, 47,
                                                 48, 49, 50, 52, 85, 86, 89)
                              } | {
                                  f'm3_psychological_consulting_{number:03}'
                                  for number in (54, 55, 56, 57, 61, 62, 63, 65, 66, 67,
                                                 69, 70, 71, 72, 77, 78, 80, 81, 97, 98, 101, 102)
                              } | {'m2_qual_008', 'm2_qual_028', 'm2_exp_095', 'm3_psychological_consulting_051'} | {
                                  f'm2_exp_{number:03}' for number in (4, 5, 40, 60, 61)
                              } | {
                                  f'm1_psyf_{number:03}' for number in (7, 13, 14, 27, 33)
                              } | {'m2_exp_029', 'm1_vnd_027', 'm1_vnd_018'} | {
                                  f'm1_phys_{number:03}' for number in (27, 39, 54)
                              } | {
                                  f'm2_qual_{number:03}'
                                  for number in (1, 2, 3, 6, 10, 17, 18, 24, 25, 26, 29, 42, 43)
                              } | {
                                  f'm2_exp_{number:03}'
                                  for number in (82, 83, 84, 85, 86, 87, 89, 90, 91, 92, 93, 109)
                              } | {
                                  'm1_gp_031', 'm1_gp_051', 'm1_intro_007',
                                  'm1_intro_009', 'm1_intro_010', 'm1_intro_025',
                                  'm1_intro_047', 'm1_intro_049', 'm1_phys_020',
                                  'm1_psyf_011', 'm1_psyf_021', 'm1_psyf_026',
                                  'm1_psyf_031', 'm1_psyf_034', 'm1_psyf_045',
                                  'm1_psyf_055', 'm1_psyf_061', 'm1_psyf_064',
                                  'm2_exp_001', 'm2_exp_002', 'm2_exp_003',
                                  'm2_exp_009', 'm2_exp_025', 'm2_exp_026',
                                  'm2_exp_031', 'm2_exp_034', 'm2_exp_035',
                                  'm2_exp_036', 'm2_exp_038', 'm2_exp_058',
                                  'm2_exp_059', 'm2_qual_004', 'm2_qual_014',
                                  'm2_qual_034', 'm2_qual_040', 'm2_qual_053',
                                  'm3_psychological_consulting_082',
                              }
        assert retired == {'m2_qual_009', 'm2_qual_013'}


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


def test_source_free_lesson_mapping_requires_label_and_exact_private_review(tmp_path, monkeypatch):
    from tests.test_private_publication_certificate import fixture_review
    from scripts.sign_private_publication import create_review_receipt
    from app.content_publication import PublicationPolicy
    public, dossier = fixture_review()
    tid = "t_abcdef012345"
    dossier["curriculum_topic_id"] = tid
    dossier["curriculum_link"] = {"source_id": "fixture", "topic_id": tid,
                                  "lesson_id": tid, "format": "lecture"}
    receipt = create_review_receipt("questions", public, dossier)
    edition = {"external_id": public["id"], "topic_id": tid,
               "item_sha256": fingerprint(public), "locator": "private review:questions:" + public["id"]}
    core = {"schema_version": 1, "disciplines": {"one": {"title": "Discipline"}},
            "topics": {}, "editions": {"a" * 64: edition}}
    labels = {"schema_version": 1, "disciplines": {},
              "topics": {tid: {"title": "Existing reviewed lesson", "discipline_id": "one"}}}
    root = tmp_path / "repo"
    (root / "content").mkdir(parents=True)
    monkeypatch.setattr(curriculum, "ROOT", root)
    monkeypatch.setattr("app.content_publication.load_policy", lambda: PublicationPolicy(
        {}, {}, {}, receipts={"questions:" + public["id"]: receipt}))
    def write(name, value):
        (root / "content" / name).write_text(json.dumps(value), encoding="utf-8")
        curriculum.load_reviewed_catalog.cache_clear()
        curriculum.load_catalog.cache_clear()
    write("curriculum.json", core)
    write("curriculum-labels.json", labels)
    write("curriculum-bindings.json", {"schema_version": 1, "items": {"a" * 64: receipt}})
    catalog = curriculum.load_catalog()
    assert catalog["topics"][tid] == labels["topics"][tid] and "source" not in catalog["topics"][tid]
    assert catalog["editions"]["a" * 64] == edition
    write("curriculum-bindings.json", {"schema_version": 1, "items": {}})
    with pytest.raises(ValueError, match="Missing current private curriculum binding"):
        curriculum.load_catalog()
    write("curriculum-bindings.json", {"schema_version": 1, "items": {"a" * 64: receipt}})
    write("curriculum-labels.json", {**labels, "topics": {}})
    with pytest.raises(ValueError, match="Invalid curriculum edition"):
        curriculum.load_catalog()
    write("curriculum-labels.json", labels)
    write("curriculum.json", {**core, "editions": {"a" * 64: {**edition, "item_sha256": "b" * 64}}})
    with pytest.raises(ValueError, match="Invalid private curriculum binding"):
        curriculum.load_catalog()
    curriculum.load_reviewed_catalog.cache_clear()
    curriculum.load_catalog.cache_clear()
