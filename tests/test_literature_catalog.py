import copy
import json
from pathlib import Path

from app.content_publication import load_policy
from app.literature import load_literature_items
from app.literature import load_topic_registry
from scripts import validate_literature, validate_topics


def test_reviewed_catalog_preserves_ids_sources_and_explicit_work_groups():
    items = load_literature_items()
    assert len(items) == 130
    assert len({item['work_id'] for item in items}) == 114
    assert len({item['topic_id'] for item in items}) == 12
    assert len({item['source']['id'] for item in items}) == 14
    legacy_ids = {key.split(':', 1)[1] for key in load_policy().legacy if key.startswith('literature:')}
    assert len(legacy_ids) == 42
    assert legacy_ids <= {item['id'] for item in items}
    physiology = [item for item in items if item['topic_id'] == 'fiziologiya_cheloveka']
    vnd = [item for item in items if item['topic_id'] == 'fiziologiya_vnd']
    assert len(physiology) == len(vnd) == 15
    assert {item['work_id'] for item in physiology} == {item['work_id'] for item in vnd}
    ales = [item for item in items if item['title'] == 'Индивидуальное и семейное психологическое консультирование']
    assert len(ales) == 2 and len({item['work_id'] for item in ales}) == 1
    assert {item['year'] for item in ales} == {None, 1999}
    # A common textbook title alone cannot merge different authors' works.
    for title, expected in [('Организационная психология', 5), ('Психолингвистика', 4), ('Психология личности', 2)]:
        named = [item for item in items if item['title'] == title]
        assert len(named) == expected
        assert len({item['work_id'] for item in named}) == expected
    assert all(item['content_access'] == 'not_verified' for item in items)
    assert all(item['outbound_links'] == [] for item in items)
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
    monkeypatch.chdir(tmp_path)
    assert len(load_literature_items()) == 130
    assert 'family_psychology' in load_topic_registry()
