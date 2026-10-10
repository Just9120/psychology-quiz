"""Knowledge intent, source approval, graph and safe catalogue replacement."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts import obsidian_catalogue as catalogue
from scripts import obsidian_vault as exporter
from scripts.audit_public_assets import audit_assets, known_source_ids


def test_committed_knowledge_has_descriptive_files_and_semantic_links():
    files, counts = catalogue.render_published()
    manifest = catalogue.prepared_notes()
    generated = catalogue.ROOT / 'vault/generated'
    actual = {p.name: p.read_bytes() for p in generated.glob('*.md')}
    assert actual == files
    catalogue.validate_links(actual)
    state = json.loads((generated / exporter.STATE).read_text(encoding='utf-8'))
    assert state['files'] == {name: exporter._hash(data) for name, data in actual.items()}
    assert counts['atomic_notes'] == len(manifest['notes'])
    assert all(not name.startswith(('question-', 'work-', 'homework-', 'topic-')) for name in actual)
    assert 'Социальный характер.md' in actual
    fromm = actual['Социальный характер.md'].decode()
    assert 'Фромм' in fromm and '## Связи' in fromm
    assert all(label not in fromm for label in ('## Вопрос', '## Варианты', 'correct_option_index'))
    concepts = {item['title'] for item in manifest['notes']}
    assert all(set(item['links']) <= concepts for item in manifest['notes'])
    assert 'не полный пересказ' in actual['Границы базы.md'].decode()
    audit_assets([catalogue.ROOT / 'vault'], known_source_ids())
    assert 'vault/' in (catalogue.ROOT / '.dockerignore').read_text()
    assert 'content/vault-notes.json' in (catalogue.ROOT / '.dockerignore').read_text()


def test_prepared_notes_need_exact_source_review_not_just_status(tmp_path, monkeypatch):
    content = tmp_path / 'content'
    content.mkdir()
    (content / 'vault-notes.json').write_text('{"schema_version":2,"notes":[],"status":"approved"}')
    monkeypatch.setattr(catalogue, 'ROOT', tmp_path)
    with pytest.raises(exporter.VaultError, match='prepared_note_source_review_required'):
        catalogue.prepared_notes()


@pytest.mark.parametrize('change,error', [
    ('quiz', 'quiz_dump_forbidden'), ('dangling', 'public_vault_link_missing'),
    ('empty_relation', 'semantic_relation_required'), ('self_link', 'semantic_relation_required'),
    ('collision', 'duplicate_knowledge_title'), ('extra_private_field', 'knowledge_fields_required'),
    ('missing_summary', 'section_coverage_mismatch'), ('opaque_title', 'invalid_knowledge_note'),
])
def test_unreviewable_graph_and_dump_are_rejected(monkeypatch, change, error):
    manifest = copy.deepcopy(catalogue.prepared_notes())
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


@pytest.mark.parametrize('private', [False, True])
def test_unified_repository_identity_idempotency_and_owner_files(tmp_path, monkeypatch, private):
    monkeypatch.setattr(exporter, 'ROOT', tmp_path)
    monkeypatch.setattr(exporter, '_git_common_directory', lambda _: tmp_path)
    def run(command, **kwargs):
        if command[0] == 'git': return SimpleNamespace(stdout='https://github.com/Just9120/psychology-quiz.git')
        return SimpleNamespace(stdout=json.dumps({'full_name':'Just9120/psychology-quiz',
            'private':private, 'archived':False, 'permissions':{'push':True}}))
    monkeypatch.setattr(exporter.subprocess, 'run', run)
    files = {catalogue.ENTRY: '# База знаний\n'.encode()}
    monkeypatch.setattr(catalogue, 'render_published', lambda: (files, {}))
    vault = tmp_path / 'vault'; (vault / 'personal').mkdir(parents=True)
    personal = vault / 'personal/Моя заметка.md'; personal.write_text('Owner note')
    exporter.write_vault(vault, files, repository_vault=True, published_content=True)
    exporter.write_vault(vault, files, repository_vault=True, published_content=True)
    assert personal.read_text() == 'Owner note'
    with pytest.raises(exporter.VaultError, match='published_catalogue_required'):
        exporter.write_vault(vault, {catalogue.ENTRY:b'private dossier'}, repository_vault=True, published_content=True)
    (vault / 'generated' / catalogue.ENTRY).write_text('Owner edit')
    with pytest.raises(exporter.VaultError, match='generated_note_changed_by_owner'):
        exporter.write_vault(vault, files, repository_vault=True, published_content=True)
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
    personal = vault / 'personal/Моя заметка.md'; personal.write_text('My own knowledge')
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
        personal.write_text('[[question-old]]'); error='personal_link_migration_required'
    if obstacle == 'personal_path_link':
        personal.write_text('[[generated/question-old.md#Вопрос|Моя ссылка]]')
        error='personal_link_migration_required'
    if obstacle == 'personal_markdown_link':
        personal.write_text('[Моя ссылка](../generated/question-old.md#Вопрос)')
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


def test_unknown_repository_visibility_is_not_assumed(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, 'ROOT', tmp_path)
    vault = tmp_path / 'vault'; vault.mkdir()
    def run(command, **kwargs):
        return SimpleNamespace(stdout=('https://github.com/Just9120/psychology-quiz.git'
            if command[0]=='git' else json.dumps({'full_name':'Just9120/psychology-quiz',
                'archived':False,'permissions':{'push':True}})))
    monkeypatch.setattr(exporter.subprocess, 'run', run)
    with pytest.raises(exporter.VaultError, match='private_repository_required'):
        exporter._verify_repository_vault(vault,published_content=True)
