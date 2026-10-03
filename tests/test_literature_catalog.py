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
    assert len(items) == 166
    assert len({item['work_id'] for item in items}) == 149
    assert len({item['topic_id'] for item in items}) == 16
    assert all(set(item['source']) == {'citation'} for item in items)
    assert all(item['source']['citation'] for item in items)
    legacy_ids = {key.split(':', 1)[1] for key in load_policy().legacy if key.startswith('literature:')}
    assert len(legacy_ids) == 42
    assert legacy_ids <= {item['id'] for item in items}
    physiology = [item for item in items if item['topic_id'] == 'fiziologiya_cheloveka']
    vnd = [item for item in items if item['topic_id'] == 'fiziologiya_vnd']
    assert len(physiology) == 15 and len(vnd) == 18
    assert {item['work_id'] for item in vnd} - {item['work_id'] for item in physiology} == {
        'lit_huizinga_homo_ludens', 'lit_selye_stress_without_distress', 'lit_levine_waking_tiger'}
    assert {item['work_id'] for item in physiology} <= {item['work_id'] for item in vnd}
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
