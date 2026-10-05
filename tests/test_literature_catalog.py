import copy
import json
from pathlib import Path

from app import literature
from app.content_publication import load_policy
from app.literature import load_access_links, load_literature_items
from app.literature import load_topic_registry
from scripts import validate_literature, validate_topics


def test_topic_module_membership_requires_primary_module_and_unique_course_modules(monkeypatch):
    original = json.loads(Path('content/topics.json').read_text(encoding='utf-8'))
    for invalid in ([], ['module1', 'module1'], ['module8'], ['module3'], 'module1'):
        topics = copy.deepcopy(original)
        topics[0]['modules'] = invalid
        monkeypatch.setattr(validate_topics, 'load_json', lambda *_: topics)
        assert any('modules must contain unique course modules' in error
                   for error in validate_topics.validate())


def test_reviewed_catalog_preserves_ids_sources_and_explicit_work_groups():
    items = load_literature_items()
    assert len(items) == 237
    assert len({item['work_id'] for item in items}) == 209
    assert len({item['topic_id'] for item in items}) == 17
    for work in ('lit_anna_freud_ego_defence', 'lit_frankl_man_search_meaning'):
        entries = [item for item in items if item['work_id'] == work]
        assert len(entries) == 2 and len({item['topic_id'] for item in entries}) == 2
        assert len({item['title'] for item in entries}) == 1
    assert all(set(item['source']) == {'citation'} for item in items)
    assert all(item['source']['citation'] for item in items)
    prize = next(item for item in items if item['id'] == 'lit_rybina_muradyan_coach_turning_point')
    assert prize['reading_level'] == 'applied' and prize['importance'] == 'additional'
    assert prize['importance_source'] == 'agent' and prize['metadata_warnings']
    for entry in items:
        if entry['id'] in {'lit_rybina_muradyan_coach_psycholinguistics', 'lit_muradyan_atlant_game', 'lit_muradyan_atlant_game_turning_point', 'lit_zatulovski_everyday_cybernetics'}:
            assert entry['reading_level'] == ('deepening' if entry['id'] == 'lit_zatulovski_everyday_cybernetics' else 'applied')
            assert entry['importance'] == 'additional' and entry['importance_source'] == 'agent'
            assert entry['metadata_warnings']
    masterpiece = next(item for item in items if item['id'] == 'lit_masterstvo_psychological_counseling')
    assert masterpiece['authors'] == [] and masterpiece['metadata_warnings']
    assert masterpiece['importance'] == 'additional' and masterpiece['importance_source'] == 'teacher'
    from app.literature_service import reading_next_step
    assert reading_next_step([prize], {}, items)['basis'] == 'agent'
    biography = next(item for item in items if item['id'] == 'lit_zatulovski_everyday_cybernetics')
    assert biography['authors'] == ['Затуловски Ю.'] and biography['importance_source'] == 'agent'
    assert reading_next_step([biography], {}, items)['basis'] == 'agent'
    legacy_ids = {key.split(':', 1)[1] for key in load_policy().legacy if key.startswith('literature:')}
    assert len(legacy_ids) == 42
    assert legacy_ids <= {item['id'] for item in items}
    physiology = [item for item in items if item['topic_id'] == 'fiziologiya_cheloveka']
    vnd = [item for item in items if item['topic_id'] == 'fiziologiya_vnd']
    assert len(physiology) == 17 and len(vnd) == 25
    assert {item['work_id'] for item in vnd} - {item['work_id'] for item in physiology} == {
        'lit_huizinga_homo_ludens', 'lit_selye_stress_without_distress', 'lit_levine_waking_tiger',
        'lit_consult_lecture_01', 'lit_course_mention_selye_stress_is_life',
        'lit_danilova_krylova_higher_nervous_activity', 'lit_ekman_psychology_of_emotions',
        'lit_gordon_effective_parent_training', 'lit_ilyin_individual_differences',
        'psf_sapolsky_psihologiya_stressa'}
    assert {item['work_id'] for item in physiology} - {item['work_id'] for item in vnd} == {
        'lit_bulgakov_heart_of_a_dog', 'lit_sechenov_reflexes_of_brain'}
    ales = [item for item in items if item['title'] == 'Индивидуальное и семейное психологическое консультирование']
    assert len(ales) == 2 and len({item['work_id'] for item in ales}) == 1
    assert {item['year'] for item in ales} == {None, 1999}
    # A common textbook title alone cannot merge different authors' works.
    for title, expected in [('Организационная психология', 5), ('Психолингвистика', 3), ('Психология личности', 2)]:
        named = [item for item in items if item['title'] == title]
        assert len(named) == expected
        assert len({item['work_id'] for item in named}) == expected
    assert all(item['content_access'] == 'not_verified' for item in items)
    assert all(item['learning_outcomes'] == [] and item['estimated_minutes'] is None for item in items)
    assert any(not item['authors'] and item['metadata_warnings'] for item in items)
    assert validate_topics.validate() == []
    assert validate_literature.validate() == []


def test_changed_bibliography_requires_new_review_and_missing_metadata_is_explicit():
    item = json.loads(Path('content/literature/family_psychology.json').read_text(encoding='utf-8'))[0]
    assert load_policy().can_publish('literature', item)
    changed = copy.deepcopy(item)
    changed['title'] += ' invented'
    assert not load_policy().can_publish('literature', changed)
    changed['authors'] = []
    changed['metadata_warnings'] = []
    changed['source'] = {}
    errors = []
    validate_literature.validate_entry(changed, 'test', item['topic_id'], {item['topic_id']}, {}, errors)
    assert any('unknown authors' in error for error in errors)
    assert any('complete bibliographic source' in error for error in errors)


def test_catalog_paths_do_not_depend_on_process_working_directory(tmp_path, monkeypatch):
    expected_items = load_literature_items()
    expected_topics = load_topic_registry()
    monkeypatch.chdir(tmp_path)
    assert load_literature_items() == expected_items
    assert load_topic_registry() == expected_topics
    assert 'family_psychology' in load_topic_registry()


def test_catalog_reuses_approved_content_without_sharing_mutable_response(monkeypatch):
    literature._published_literature_items.cache_clear()
    original_load = literature._load_json_file
    reads = []

    def tracked_load(path):
        if path.parent == literature.LITERATURE_DIR:
            reads.append(path)
        return original_load(path)

    monkeypatch.setattr(literature, '_load_json_file', tracked_load)
    try:
        first = load_literature_items()
        assert reads
        first[0]['title'] = 'changed by caller'
        first[0]['source']['citation'] = 'changed by caller'
        first[0]['access_links'].clear()
        second = load_literature_items()
        assert len(reads) == len(list(literature.LITERATURE_DIR.glob('*.json')))
        assert second[0]['title'] != 'changed by caller'
        assert second[0]['source']['citation'] != 'changed by caller'
    finally:
        literature._published_literature_items.cache_clear()


def test_importance_taxonomy_requires_reviewed_value():
    item = json.loads(Path('content/literature/family_psychology.json').read_text(encoding='utf-8'))[0]
    for importance in ('basic', 'important', 'additional', 'advanced', None):
        changed = copy.deepcopy(item)
        changed['importance'] = importance
        changed['importance_source'] = 'teacher' if importance else None
        errors = []
        validate_literature.validate_entry(changed, 'test', item['topic_id'], {item['topic_id']}, {}, errors)
        assert not any('importance must be' in error for error in errors)
        assert not any('must be set together' in error for error in errors)
    changed['importance'] = 'high'
    errors = []
    validate_literature.validate_entry(changed, 'test', item['topic_id'], {item['topic_id']}, {}, errors)
    assert any('importance must be' in error for error in errors)


def test_verified_outbound_versions_are_work_scoped_and_never_claim_owned_access():
    links = load_access_links()
    assert set(links) == {
        'vygotsky_myshlenie_i_rech', 'lit_0199865ad8d23ecb', 'lit_819808cf97ad8eb5',
        'gippenreiter_vvedenie_v_obschuyu_psihologiyu', 'nurkova_berezanskaya_obschaya_psihologiya',
        'rubinstein_osnovy_obschey_psihologii', 'lit_consult_lecture_01', 'lit_consult_lecture_02',
        'lit_5505760c8ef8c4b8', 'lit_8c4dd1a3c39ecbcf',
        'lit_4f9768a778fe2a01', 'lit_25a5d2f1c7ba76e1',
    }
    assert {link['format'] for link in links['vygotsky_myshlenie_i_rech']} == {'text', 'audio'}
    assert {link['format'] for link in links['lit_0199865ad8d23ecb']} == {'text'}
    assert {link['format'] for link in links['lit_819808cf97ad8eb5']} == {'text', 'audio'}
    assert all(link['access'] == 'provider_terms' for link in links['vygotsky_myshlenie_i_rech'])
    items = load_literature_items()
    assert all(item['access_links'] == links[item['work_id']] for item in items if item['work_id'] in links)
    assert all(item['access_links'] == [] for item in items if item['work_id'] not in links)
    # One publisher collection must not merge its two independently studied works.
    from app.literature_service import reading_summary
    collected = [item for item in items if item['id'] in {'lit_4f9768a778fe2a01', 'lit_25a5d2f1c7ba76e1'}]
    assert len({item['work_id'] for item in collected}) == 2
    assert collected[0]['access_links'] == collected[1]['access_links']
    assert {offer['format'] for offer in collected[0]['access_links']} == {'text', 'audio'}
    summary = reading_summary(collected, {collected[0]['id']: {'reading_status': 'read'}})
    assert summary['total'] == 2 and summary['read'] == 1
    assert all(item['content_access'] == 'not_verified' for item in collected)
    assert all(any('сборнику' in warning for warning in item['metadata_warnings']) for item in collected)


def test_reading_prerequisites_reject_cycles_between_works_and_their_associations():
    def entry(work, prerequisites=()):
        return {"work_id": work, "prerequisites": list(prerequisites)}
    entries = {"a": entry("a"), "a-list": entry("a", ["b"]),
               "b": entry("b", ["a"]), "c": entry("c", ["b"])}
    assert validate_literature.validate_prerequisite_graph(entries)
    entries["b"]["prerequisites"] = []
    assert validate_literature.validate_prerequisite_graph(entries) == []
    entries["a-list"]["prerequisites"] = ["a"]
    assert validate_literature.validate_prerequisite_graph(entries)


def test_reading_prerequisite_graph_handles_long_valid_sequence_without_recursion():
    entries = {str(i): {"work_id": str(i), "prerequisites": [str(i-1)] if i else []}
               for i in range(1500)}
    assert validate_literature.validate_prerequisite_graph(entries) == []


def test_curated_offers_allow_multiple_text_providers_and_reject_wrong_targets(monkeypatch):
    import pytest
    base = {"format": "text", "provider": "Литрес", "url": "https://www.litres.ru/book/author/book-1/", "access": "provider_terms", "checked_at": "2026-09-30"}
    publisher = {**base, "provider": "Юрайт", "url": "https://urait.ru/bcode/582490"}
    raw = {"schema_version": 1, "works": {"work": [base, publisher]}}
    monkeypatch.setattr(literature, '_load_json_file', lambda path: raw)
    try:
        literature.load_access_links.cache_clear()
        assert literature.load_access_links()['work'] == [base, publisher]
        invalid = [
            {**publisher, "provider": "Unknown"},
            {**publisher, "format": "audio"},
            {**publisher, "url": "https://urait.ru.evil.example/bcode/582490"},
            {**publisher, "url": "https://urait.ru@evil.example/bcode/582490"},
            {**publisher, "url": "https://urait.ru/bcode/582490?redirect=elsewhere"},
            {**publisher, "url": "https://urait.ru/account"},
            {**publisher, "url": "http://urait.ru/bcode/582490"},
        ]
        for offer in invalid:
            raw['works']['work'] = [offer]
            literature.load_access_links.cache_clear()
            with pytest.raises(ValueError):
                literature.load_access_links()
        raw['works']['work'] = [base, dict(base)]
        literature.load_access_links.cache_clear()
        with pytest.raises(ValueError):
            literature.load_access_links()
    finally:
        literature.load_access_links.cache_clear()


def test_history_books_preserve_shared_work_and_do_not_recommend_uncertain_identity():
    from app.literature_service import reading_next_step, reading_summary

    all_items = load_literature_items()
    by_id = {item['id']: item for item in all_items}
    anthology = [by_id['lit_lebon_psychology_peoples_masses'],
                 by_id['lit_social_history02_lebon']]
    uncertain = by_id['lit_course_mention_lebon_crowd']
    states = {item['id']: {'reading_status': 'read'} for item in anthology}
    summary = reading_summary([*anthology, uncertain], states)
    assert summary['total'] == 2 and summary['read'] == 1
    assert summary['conflicts'] == 0
    assert uncertain['work_id'] != anthology[0]['work_id']
    assert reading_next_step([uncertain], states, all_items) is None
    started = {**states, uncertain['id']: {'reading_status': 'in_progress'}}
    continuation = reading_next_step([uncertain], started, all_items)
    assert continuation['kind'] == 'continue'
    assert continuation['item']['id'] == uncertain['id']
    for item_id in ('lit_social_history02_wundt', 'lit_social_history02_freud',
                    'lit_social_history02_miller_dollard', 'lit_social_history02_sighele'):
        item = by_id[item_id]
        assert reading_next_step([item], {}, all_items) is None
        prerequisites = {entry['id']: {'reading_status': 'read'} for entry in all_items
                         if entry['work_id'] == by_id['lit_caa8d94a943aae0d']['work_id']}
        recommended = reading_next_step([item], prerequisites, all_items)
        assert recommended['kind'] == 'start' and recommended['basis'] == 'agent'
        assert recommended['item']['id'] == item_id
