import copy
import json

from app import knowledge_coverage as knowledge
from app import owner_content


def test_exact_qualified_links_unmapped_and_empty_lessons_do_not_approve_sources():
    revision = {'modified_time': 'old', 'snapshot_sha256': 'a' * 64}
    catalog = {'disciplines': {'a': {'title': 'Дисциплина А'}, 'b': {'title': 'Дисциплина Б'}},
               'topics': {key: {'discipline_id': discipline, 'source': {'source_id': key, **revision}}
                          for key, discipline in [('one', 'a'), ('two', 'b'), ('empty', 'a')]}}
    registry = {'sources': [{'id': key, 'title': title, **revision} for key, title in
                            [('one', 'Практика №1'), ('two', 'Практика №1'), ('empty', 'Без заметок')]]}
    manifest = {'notes': [{'section': 'Раздел', 'sources': sources} for sources in
                          [['Дисциплина А — Практика №1'], ['Практика №1'], ['Неизвестный источник']]]}
    original = copy.deepcopy((manifest, catalog, registry))
    result = knowledge.project(manifest, catalog, registry)
    assert result['atomic_notes'] == 3 and result['unmapped_notes'] == 2
    assert result['lessons'] == {'one': 1, 'two': 0, 'empty': 0}
    assert result['disciplines'] == {'a': 1}
    assert (manifest, catalog, registry) == original
    # A new source edition cannot silently acquire the old publication's binding.
    registry['sources'][0]['snapshot_sha256'] = 'b' * 64
    assert knowledge.project(manifest, catalog, registry)['unmapped_notes'] == 3
    assert not any(key in json.dumps(result) for key in ('source_id', 'modified_time', 'snapshot_sha256'))


def test_release_knowledge_is_current_and_scientific_holds_are_independent(monkeypatch):
    from scripts.obsidian_catalogue import prepared_notes, REVIEWED_NOTES_SHA256
    monkeypatch.delenv('OWNER_SOURCE_SUMMARY_PATH', raising=False)
    before = owner_content.source_summary()
    result = knowledge.published_knowledge()
    registry = json.loads((knowledge.ROOT / 'content/source-corpus.json').read_text(encoding='utf-8'))
    assert result == knowledge.project(prepared_notes(), knowledge.load_reviewed_catalog(), registry) | {
        'package_sha256': REVIEWED_NOTES_SHA256, 'published_at': '2026-10-10'}
    assert result['state'] == 'PUBLISHED'
    assert result['atomic_notes'] == 387 and len(result['sections']) == 13
    assert result['unmapped_notes'] == 242
    assert len(result['lessons']) == 42 and all(count > 0 for count in result['lessons'].values())
    assert before['known_holds'] == 321 and before == owner_content.source_summary()


def test_changed_published_projection_fails_closed(tmp_path, monkeypatch):
    (tmp_path / 'content').mkdir()
    (tmp_path / 'content/knowledge-coverage.json').write_text('{"state":"PUBLISHED","private":"foreign"}')
    monkeypatch.setattr(knowledge, 'ROOT', tmp_path)
    assert knowledge.published_knowledge()['state'] == 'UNSET'
