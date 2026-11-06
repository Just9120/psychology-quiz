"""Private package integrity, real renderer gates and personal-file preservation."""
import hashlib
import io
import json
import stat
import zipfile

import pytest

from scripts import obsidian_catalogue as catalogue
from scripts import obsidian_vault as exporter
from scripts import vault_package as package


@pytest.fixture
def reviewed(tmp_path, monkeypatch, vault_reviewed_payload):
    monkeypatch.setattr(exporter, '_git_common_directory', lambda _: None)
    path = tmp_path / 'private-reviewed.json'; path.write_bytes(vault_reviewed_payload)
    return path


def test_package_opens_and_updates_without_changing_personal_files(reviewed, tmp_path):
    archive = tmp_path / 'vault.zip'
    result = package.create_package(reviewed, archive)
    files, payload, metadata = package.read_package(archive, result['sha256'])
    assert payload == reviewed.read_bytes()
    assert result['counts'] == {'atomic_notes': 2, 'summaries': 1, 'markdown_files': 5}
    assert metadata['reviewed_notes_sha256'] == hashlib.sha256(payload).hexdigest()
    vault = tmp_path / 'opened'; vault.mkdir()
    # A verified archive can be unzipped as an ordinary portable Obsidian folder.
    with zipfile.ZipFile(archive) as source:
        source.extractall(vault)
    (vault / 'Дневник').mkdir()
    (vault / 'Дневник/Сегодня.md').write_text(
        '[[Уточнение запроса#Связи]]\n'
        '[Основание](../generated/Рабочая%20гипотеза.md#Основание)', encoding='utf-8')
    (vault / '.obsidian').mkdir()
    (vault / '.obsidian/workspace.json').write_bytes(b'{"owner":true}')
    (vault / 'attachment.bin').write_bytes(bytes(range(256)))
    personal = {p.relative_to(vault): p.read_bytes() for p in vault.rglob('*')
                if p.is_file() and p.relative_to(vault).parts[0] != 'generated'}
    receipt = package.apply_package(archive, result['sha256'], vault)
    assert receipt['unmanaged_paths_written'] == 0
    assert {name: (vault / name).read_bytes() for name in personal} == personal
    assert {p.name: p.read_bytes() for p in (vault / 'generated').glob('*.md')} == files
    assert not (vault / '.vault-generated-backup').exists()
    with pytest.raises(exporter.VaultError, match='new_private_package_required'):
        package.create_package(reviewed, archive)


def test_digest_is_required_and_approval_cannot_be_self_declared(reviewed, tmp_path):
    archive = tmp_path / 'vault.zip'
    result = package.create_package(reviewed, archive)
    with pytest.raises(exporter.VaultError, match='private_package_digest_mismatch'):
        package.read_package(archive, '0' * 64)
    reviewed.write_bytes(reviewed.read_bytes() + b' ')
    with pytest.raises(exporter.VaultError, match='prepared_note_source_review_required'):
        package.create_package(reviewed, tmp_path / 'unreviewed.zip')
    assert not (tmp_path / 'unreviewed.zip').exists()


@pytest.mark.parametrize('change', ['traversal', 'symlink', 'duplicate', 'body', 'manifest', 'missing'])
def test_rehashed_tampered_archive_cannot_update_vault(reviewed, tmp_path, change):
    archive = tmp_path / 'vault.zip'
    package.create_package(reviewed, archive)
    with zipfile.ZipFile(archive) as original:
        members = {entry.filename: original.read(entry) for entry in original.infolist()}
    if change == 'body': members['generated/Уточнение запроса.md'] = b'Unreviewed content'
    if change == 'manifest': members[package.REVIEWED] += b' '
    if change == 'missing': del members['generated/Рабочая гипотеза.md']
    if change in {'body', 'manifest', 'missing'}:
        # Even an attacker who recomputes the archive and member checksums
        # cannot make a different edition pass the independently pinned review.
        metadata = json.loads(members[package.METADATA])
        metadata['files'] = {name: package.sha256(body) for name, body in members.items()
                             if name != package.METADATA}
        members[package.METADATA] = json.dumps(metadata).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as altered:
        for name, body in members.items(): altered.writestr(name, body)
        if change == 'traversal': altered.writestr('../personal.md', b'Overwrite')
        if change == 'duplicate': altered.writestr('README.MD', b'Conflicting name')
        if change == 'symlink':
            entry = zipfile.ZipInfo('generated/Injected.md')
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            altered.writestr(entry, '../../personal.md')
    data = buffer.getvalue(); archive.write_bytes(data)
    vault = tmp_path / 'existing'; vault.mkdir()
    owner = vault / 'personal.md'; owner.write_bytes(b'Owner file')
    with pytest.raises(exporter.VaultError):
        package.apply_package(archive, package.sha256(data), vault)
    assert owner.read_bytes() == b'Owner file'
    assert not (vault / 'generated').exists()


def test_owner_edited_generated_content_is_preserved(reviewed, tmp_path):
    archive = tmp_path / 'vault.zip'; result = package.create_package(reviewed, archive)
    vault = tmp_path / 'existing'; vault.mkdir()
    package.apply_package(archive, result['sha256'], vault)
    owner = vault / 'generated/Уточнение запроса.md'; owner.write_bytes(b'Owner addition')
    with pytest.raises(exporter.VaultError, match='generated_note_changed_by_owner'):
        package.apply_package(archive, result['sha256'], vault)
    assert owner.read_bytes() == b'Owner addition'
