"""The downloadable Vault covers only approved editions and keeps private data out."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import obsidian_catalogue as catalogue
from scripts import obsidian_vault as exporter
from scripts.audit_public_assets import audit_assets, known_source_ids


def test_committed_vault_matches_every_published_edition_and_resolves_links():
    files, counts = catalogue.render_published()
    generated = catalogue.ROOT / 'vault/generated'
    actual = {p.name: p.read_bytes() for p in generated.glob('*.md')}
    assert all(actual.get(name) == data for name, data in files.items())
    assert all(data == catalogue.RETIRED_NOTE for name, data in actual.items() if name not in files)
    catalogue.validate_links(actual)
    state = json.loads((generated / exporter.STATE).read_text(encoding='utf-8'))
    assert state['files'] == {name: exporter._hash(data) for name, data in actual.items()}
    assert counts['questions'] == len(catalogue.published_questions())
    assert counts['terms'] == len(catalogue.published_glossary(catalogue.load_policy()))
    assert counts['works'] == len({item['work_id'] for item in catalogue.load_literature_items()})
    assert counts['homework'] == len(catalogue.load_homework())
    audit_assets([catalogue.ROOT / 'vault'], known_source_ids())
    assert 'vault/' in (catalogue.ROOT / '.dockerignore').read_text()


def test_question_and_case_preserve_correct_answer_explanation_and_boundaries():
    files, _ = catalogue.render_published()
    for item in catalogue.published_questions():
        note = files[catalogue.note_id('question', item['id']) + '.md'].decode()
        assert catalogue.text(item['options'][item['correct_option_index']]) in note
        assert catalogue.text(item['explanation']) in note
        if item.get('kind') == 'case':
            assert catalogue.text(item['case']['ambiguity']) in note
            assert all(catalogue.text(value) in note for value in item['case']['conditions'])
            assert all(catalogue.text(value) in note for value in item['case']['option_rationales'])
    # Absent concepts are explicitly unavailable, never invented linked notes.
    assert any('нет самостоятельного определения' in data.decode() for data in files.values())


def test_prepared_notes_need_exact_source_review_not_just_a_status(tmp_path, monkeypatch):
    content = tmp_path / 'content'
    content.mkdir()
    (content / 'vault-notes.json').write_text('{"schema_version":1,"notes":[],"status":"approved"}')
    monkeypatch.setattr(catalogue, 'ROOT', tmp_path)
    with pytest.raises(exporter.VaultError, match='prepared_note_source_review_required'):
        catalogue.prepared_notes()


@pytest.mark.parametrize('private', [False, True])
def test_safe_catalogue_can_use_unified_repo_without_changing_visibility(tmp_path, monkeypatch, private):
    monkeypatch.setattr(exporter, 'ROOT', tmp_path)
    monkeypatch.setattr(exporter, '_git_common_directory', lambda _: tmp_path)
    def run(command, **kwargs):
        if command[0] == 'git':
            return SimpleNamespace(stdout='https://github.com/Just9120/psychology-quiz.git')
        return SimpleNamespace(stdout=json.dumps({'full_name': 'Just9120/psychology-quiz',
            'private': private, 'archived': False, 'permissions': {'push': True}}))
    monkeypatch.setattr(exporter.subprocess, 'run', run)
    files = {'index.md': b'# Reviewed catalogue\n'}
    monkeypatch.setattr(catalogue, 'render_published', lambda: (files, {}))
    vault = tmp_path / 'vault'
    vault.mkdir()
    personal = vault / 'personal.md'
    personal.write_text('Owner note')
    exporter.write_vault(vault, files, repository_vault=True, published_content=True)
    exporter.write_vault(vault, files, repository_vault=True, published_content=True)
    assert personal.read_text() == 'Owner note'
    assert (vault / 'generated/index.md').read_bytes() == files['index.md']
    with pytest.raises(exporter.VaultError, match='published_catalogue_required'):
        exporter.write_vault(vault, {'index.md': b'private dossier'}, repository_vault=True, published_content=True)
    (vault / 'generated/index.md').write_text('Owner edit')
    with pytest.raises(exporter.VaultError, match='generated_note_changed_by_owner'):
        exporter.write_vault(vault, files, repository_vault=True, published_content=True)
    assert (vault / 'generated/index.md').read_text() == 'Owner edit'


def test_old_private_notes_cannot_be_retained_in_public_export(tmp_path, monkeypatch):
    files = {'index.md': b'# Approved\n'}
    monkeypatch.setattr(catalogue, 'render_published', lambda: (files, {}))
    vault = tmp_path / 'vault'
    vault.mkdir()
    monkeypatch.setattr(exporter, '_git_common_directory', lambda _: None)
    exporter.write_vault(vault, {'index.md': b'# Private\n', 'old.md': b'drive:private-source'})
    with pytest.raises(exporter.VaultError, match='private_provenance_in_public_vault'):
        exporter.write_vault(vault, files, published_content=True)
    assert (vault / 'generated/old.md').read_bytes() == b'drive:private-source'


def test_withdrawn_edition_keeps_links_without_republishing_old_claim(tmp_path, monkeypatch):
    old = {'index.md': b'# Approved\n', 'old.md': b'Previous approved claim'}
    current = {'index.md': b'# Approved\n'}
    monkeypatch.setattr(exporter, '_git_common_directory', lambda _: None)
    monkeypatch.setattr(catalogue, 'render_published', lambda: (old, {}))
    vault = tmp_path / 'vault'
    vault.mkdir()
    exporter.write_vault(vault, old, published_content=True)
    monkeypatch.setattr(catalogue, 'render_published', lambda: (current, {}))
    exporter.write_vault(vault, current, published_content=True)
    assert (vault / 'generated/old.md').read_bytes() == catalogue.RETIRED_NOTE
    assert (vault / 'generated/index.md').read_bytes() == current['index.md']


def test_unknown_repository_visibility_is_never_assumed(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, 'ROOT', tmp_path)
    vault = tmp_path / 'vault'
    vault.mkdir()
    def run(command, **kwargs):
        return SimpleNamespace(stdout=('https://github.com/Just9120/psychology-quiz.git'
            if command[0] == 'git' else json.dumps({'full_name': 'Just9120/psychology-quiz',
                'archived': False, 'permissions': {'push': True}})))
    monkeypatch.setattr(exporter.subprocess, 'run', run)
    with pytest.raises(exporter.VaultError, match='private_repository_required'):
        exporter._verify_repository_vault(vault, published_content=True)
