"""Knowledge intent, source approval, graph and safe catalogue replacement."""
import copy
import hashlib
import json

import pytest

from scripts import obsidian_catalogue as catalogue
from scripts import obsidian_vault as exporter


def test_knowledge_has_descriptive_files_and_semantic_links(vault_reviewed_payload):
    files, counts = catalogue.render_reviewed_payload(vault_reviewed_payload)
    manifest = catalogue.reviewed_notes_payload(vault_reviewed_payload)
    catalogue.validate_links(files)
    assert counts['atomic_notes'] == len(manifest['notes'])
    assert all(not name.startswith(('question-', 'work-', 'homework-', 'topic-')) for name in files)
    note = files['Уточнение запроса.md'].decode()
    assert '[[Рабочая гипотеза]]' in note and '## Связи' in note
    assert all(label not in note for label in ('## Вопрос', '## Варианты', 'correct_option_index'))
    concepts = {item['title'] for item in manifest['notes']}
    assert all(set(item['links']) <= concepts for item in manifest['notes'])
    assert 'не полный пересказ' in files['Границы базы.md'].decode()
    assert 'vault/' in (catalogue.ROOT / '.dockerignore').read_text()
    assert 'content/vault-notes.json' in (catalogue.ROOT / '.dockerignore').read_text()


def test_prepared_notes_need_exact_source_review_not_just_status(tmp_path, monkeypatch):
    content = tmp_path / 'content'
    content.mkdir()
    (content / 'vault-notes.json').write_text('{"schema_version":2,"notes":[],"status":"approved"}', encoding="utf-8")
    monkeypatch.setattr(catalogue, 'ROOT', tmp_path)
    with pytest.raises(exporter.VaultError, match='prepared_note_source_review_required'):
        catalogue.reviewed_notes_payload((content / 'vault-notes.json').read_bytes())


def test_private_manifest_is_explicit_and_has_no_repository_fallback():
    with pytest.raises(exporter.VaultError, match='private_reviewed_manifest_required'):
        catalogue.prepared_notes()


def test_ready_knowledge_is_absent_from_repository_and_container_context():
    assert not (catalogue.ROOT / 'content/vault-notes.json').exists()
    assert not (catalogue.ROOT / 'vault/generated').exists()
    ignored = (catalogue.ROOT / '.gitignore').read_text(encoding='utf-8')
    assert 'content/vault-notes.json' in ignored
    assert 'generated/' in (catalogue.ROOT / 'vault/.gitignore').read_text(encoding='utf-8')
    excluded = (catalogue.ROOT / '.dockerignore').read_text(encoding='utf-8')
    assert 'vault/' in excluded and 'data/' in excluded


@pytest.mark.parametrize('change,error', [
    ('quiz', 'quiz_dump_forbidden'), ('dangling', 'public_vault_link_missing'),
    ('empty_relation', 'semantic_relation_required'), ('self_link', 'semantic_relation_required'),
    ('collision', 'duplicate_knowledge_title'), ('extra_private_field', 'knowledge_fields_required'),
    ('missing_summary', 'section_coverage_mismatch'), ('opaque_title', 'invalid_knowledge_note'),
])
def test_unreviewable_graph_and_dump_are_rejected(monkeypatch, change, error, vault_reviewed_payload):
    manifest = json.loads(vault_reviewed_payload)
    item = manifest['notes'][0]
    if change == 'quiz': item['body'] = '## Вопрос\n' + item['body']
    if change == 'dangling': item['links'] = {'Несуществующее понятие': 'Отношение.'}
    if change == 'empty_relation': item['links'] = {next(iter(item['links'])): ''}
    if change == 'self_link': item['links'] = {item['title']: 'Ссылка на себя.'}
    if change == 'collision': manifest['notes'].append(copy.deepcopy(item))
    if change == 'extra_private_field': item['source_id'] = 'private'
    if change == 'missing_summary': manifest['coverage']['summaries'].pop(item['section'])
    if change == 'opaque_title': item['title'] = 'question-ad1e210ccc6eb6be972d'
    monkeypatch.setattr(catalogue, 'prepared_notes', lambda: manifest)
    with pytest.raises(exporter.VaultError, match=error): catalogue.render_published()


@pytest.mark.parametrize('name', ['../Заметка.md', 'C:\\Заметка.md', 'AUX.md', 'Название..md',
                                  '[[Заметка]].md', 'Название?.md', 'А' * 111 + '.md'])
def test_filename_cannot_escape_directory_or_break_portability(name):
    assert not exporter.valid_generated_name(name)


def test_private_vault_idempotency_and_owner_files(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, '_git_common_directory', lambda _: None)
    files = {catalogue.ENTRY: '# База знаний\n'.encode()}
    monkeypatch.setattr(catalogue, 'render_published', lambda: (files, {}))
    vault = tmp_path / 'vault'; (vault / 'personal').mkdir(parents=True)
    personal = vault / 'personal/Моя заметка.md'; personal.write_text('Owner note', encoding="utf-8")
    exporter.write_vault(vault, files, published_content=True)
    exporter.write_vault(vault, files, published_content=True)
    assert personal.read_text() == 'Owner note'
    with pytest.raises(exporter.VaultError, match='published_catalogue_required'):
        exporter.write_vault(vault, {catalogue.ENTRY:b'private dossier'}, published_content=True)
    (vault / 'generated' / catalogue.ENTRY).write_text('Owner edit', encoding="utf-8")
    with pytest.raises(exporter.VaultError, match='generated_note_changed_by_owner'):
        exporter.write_vault(vault, files, published_content=True)
    assert (vault / 'generated' / catalogue.ENTRY).read_text() == 'Owner edit'


def test_old_private_notes_cannot_be_retained_in_public_export(tmp_path, monkeypatch):
    files = {catalogue.ENTRY: '# База знаний\n'.encode()}
    monkeypatch.setattr(catalogue, 'render_published', lambda: (files, {}))
    vault = tmp_path / 'vault'; vault.mkdir()
    monkeypatch.setattr(exporter, '_git_common_directory', lambda _: None)
    exporter.write_vault(vault, {'index.md':b'# Private\n', 'old.md':b'drive:private-source'})
    with pytest.raises(exporter.VaultError, match='private_provenance_in_public_vault'):
        exporter.write_vault(vault, files, published_content=True)
    assert (vault / 'generated/old.md').read_bytes() == b'drive:private-source'


def test_withdrawn_concept_keeps_link_without_old_claim(tmp_path, monkeypatch):
    old = {catalogue.ENTRY:'# База знаний\n'.encode(), 'Понятие.md':b'Previous approved claim'}
    current = {catalogue.ENTRY:old[catalogue.ENTRY]}
    monkeypatch.setattr(exporter, '_git_common_directory', lambda _: None)
    monkeypatch.setattr(catalogue, 'render_published', lambda: (old, {}))
    vault = tmp_path / 'vault'; vault.mkdir()
    exporter.write_vault(vault, old, published_content=True)
    monkeypatch.setattr(catalogue, 'render_published', lambda: (current, {}))
    exporter.write_vault(vault, current, published_content=True)
    assert (vault / 'generated/Понятие.md').read_bytes() == catalogue.RETIRED_NOTE


@pytest.mark.parametrize('obstacle', ['none', 'owner_edit', 'unknown_file', 'unknown_state',
                                    'personal_link', 'personal_path_link', 'personal_markdown_link'])
def test_explicit_migration_replaces_only_known_unchanged_catalogue(tmp_path, monkeypatch, obstacle):
    old = {'index.md':b'# Old index\n', 'question-old.md':b'Old quiz'}
    current = {catalogue.ENTRY:'# База знаний\n'.encode()}
    monkeypatch.setattr(exporter, '_git_common_directory', lambda _: None)
    monkeypatch.setattr(catalogue, 'render_published', lambda: (old, {}))
    vault = tmp_path / 'vault'; (vault / 'personal').mkdir(parents=True)
    personal = vault / 'personal/Моя заметка.md'; personal.write_text('My own knowledge', encoding="utf-8")
    exporter.write_vault(vault, old, published_content=True)
    state = vault / 'generated' / exporter.STATE
    monkeypatch.setattr(catalogue, 'LEGACY_STATE_SHA256', hashlib.sha256(state.read_bytes()).hexdigest())
    monkeypatch.setattr(catalogue, 'render_published', lambda: (current, {}))
    error = None
    if obstacle == 'owner_edit':
        (vault / 'generated/question-old.md').write_bytes(b'My edit'); error='generated_note_changed_by_owner'
    if obstacle == 'unknown_file':
        (vault / 'generated/personal.md').write_bytes(b'Mine'); error='unowned_generated_file'
    if obstacle == 'unknown_state':
        state.write_bytes(state.read_bytes()+b'\n'); error='unknown_catalogue_migration'
    if obstacle == 'personal_link':
        personal.write_text('[[question-old]]', encoding="utf-8"); error='personal_link_migration_required'
    if obstacle == 'personal_path_link':
        personal.write_text('[[generated/question-old.md#Вопрос|Моя ссылка]]', encoding="utf-8")
        error='personal_link_migration_required'
    if obstacle == 'personal_markdown_link':
        personal.write_text('[Моя ссылка](../generated/question-old.md#Вопрос)', encoding="utf-8")
        error='personal_link_migration_required'
    before = {p.name:p.read_bytes() for p in (vault / 'generated').iterdir()}
    personal_before = personal.read_bytes()
    if error:
        with pytest.raises(exporter.VaultError, match=error):
            exporter.write_vault(vault, current, published_content=True, replace_catalogue=True)
        assert {p.name:p.read_bytes() for p in (vault / 'generated').iterdir()} == before
    else:
        exporter.write_vault(vault, current, published_content=True, replace_catalogue=True)
        assert not (vault / 'generated/question-old.md').exists()
        assert (vault / 'generated' / catalogue.ENTRY).read_bytes() == current[catalogue.ENTRY]
        exporter.write_vault(vault, current, published_content=True)
    assert personal.read_bytes() == personal_before


def test_repository_export_does_not_infer_permission_from_visibility(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, 'ROOT', tmp_path)
    vault = tmp_path / 'vault'; vault.mkdir()
    def forbidden(*args, **kwargs):
        raise AssertionError('Repository visibility cannot authorize a Vault export')
    monkeypatch.setattr(exporter.subprocess, 'run', forbidden)
    with pytest.raises(exporter.VaultError, match='private_package_delivery_required'):
        exporter._verify_repository_vault(vault,published_content=True)
