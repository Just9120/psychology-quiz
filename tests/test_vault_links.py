"""A managed update must not silently break ordinary personal navigation."""
import pytest

from scripts import obsidian_vault as vault
from scripts.vault_links import personal_link_breaks


OLD = {'Заметка.md': '# Заметка\n\n## Условия работы\n\nТекст. ^case-1\n'.encode()}


@pytest.mark.parametrize('link', [
    '[[Заметка#Условия работы|Условия]]',
    '[[generated/Заметка.md#Условия работы]]',
    '[Условия](generated/Заметка.md#Условия%20работы)',
    '[Условия](generated/Заметка.md#условия-работы)',
    '[[Заметка#^case-1]]',
    '[[заметка#Условия работы]]',
    '[Условия][ref]\n\n[ref]: generated/Заметка.md#Условия%20работы',
])
def test_root_personal_anchor_break_stops_update(tmp_path, link):
    (tmp_path / 'Мои заметки.md').write_text(link, encoding='utf-8')
    assert not personal_link_breaks(tmp_path, OLD, OLD)
    assert personal_link_breaks(tmp_path, OLD, {'Заметка.md': b'# Replaced\n'})


def test_nested_markdown_and_wiki_paths(tmp_path):
    folder = tmp_path / 'Дневник'; folder.mkdir()
    path = folder / 'Сегодня.md'
    path.write_text('[Связь](../generated/Заметка.md)\n[[Заметка]]', encoding='utf-8')
    assert personal_link_breaks(tmp_path, OLD, {})
    assert not personal_link_breaks(tmp_path, OLD, OLD)


def test_nested_heading_and_preexisting_broken_anchor(tmp_path):
    old = {'Заметка.md': '# Заметка\n## Родитель\n### Детали\n'.encode()}
    note = tmp_path / 'Личное.md'
    note.write_text('[[Заметка#Родитель#Детали]]', encoding='utf-8')
    assert personal_link_breaks(tmp_path, old, OLD)
    note.write_text('[[Заметка#Никогда не было]]', encoding='utf-8')
    assert not personal_link_breaks(tmp_path, old, OLD)
    assert personal_link_breaks(tmp_path, old, {})


def test_setext_heading_is_also_protected(tmp_path):
    (tmp_path / 'Личное.md').write_text('[[Заметка#Условия работы]]', encoding='utf-8')
    previous = {'Заметка.md': 'Условия работы\n---------------\nТекст.\n'.encode()}
    assert not personal_link_breaks(tmp_path, previous, previous)
    assert personal_link_breaks(tmp_path, previous, {'Заметка.md': b'# Changed\n'})


def test_external_examples_and_personal_targets_not_a_managed_dependency(tmp_path):
    (tmp_path / 'Личное.md').write_text(
        '[Website](https://example.test/Заметка.md#Раздел)\n'
        '`[[Заметка]]`\n```md\n[[Заметка]]\n```\n[[Другая личная заметка]]', encoding='utf-8')
    assert not personal_link_breaks(tmp_path, OLD, {})


def test_writer_checks_links_before_any_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(vault, '_git_common_directory', lambda _: None)
    initial = {'index.md': b'# Index\n', **OLD}
    vault.write_vault(tmp_path, initial)
    personal = tmp_path / 'Не в personal.md'
    personal.write_text('[[Заметка#^case-1]]', encoding='utf-8')
    settings = tmp_path / '.obsidian'; settings.mkdir()
    (settings / 'bookmarks.json').write_bytes(b'{"owner":true}')
    before = {p.relative_to(tmp_path).as_posix(): p.read_bytes()
              for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(vault.VaultError, match='personal_link_migration_required'):
        vault.write_vault(tmp_path, {'index.md': b'# Index\n', 'Заметка.md': b'# Changed\n'})
    assert before == {p.relative_to(tmp_path).as_posix(): p.read_bytes()
                      for p in tmp_path.rglob('*') if p.is_file()}
    assert not (tmp_path / '.vault-generated-backup').exists()
