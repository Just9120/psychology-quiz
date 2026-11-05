"""Private portable Vault packages; source review and owner-file guards stay active.

The archive carries the exact reviewed knowledge input, so verification and an
update do not need access to Drive sources or a public copy of the notes in Git.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import obsidian_catalogue as catalogue
from scripts.obsidian_vault import (STATE, VaultError, private_vault_location,
                                   valid_generated_name, write_vault)

REVIEWED = '.psychology-atlas-reviewed.json'
METADATA = '.psychology-atlas-package.json'
MAX_BYTES = 64 * 1024 * 1024
MAX_FILES = 5000
README = '''# PsychologyAtlas в Obsidian

Распакуйте этот закрытый архив в отдельную папку. В Obsidian выберите
«Открыть папку как хранилище» и укажите распакованную папку.
Начните с [Базы знаний](generated/База%20знаний.md).
Обычные Markdown и wikilinks работают без дополнительных плагинов.

Это датированная база по проверенным фрагментам источников. Границы и
удержанные утверждения описаны в [границах базы](generated/Границы%20базы.md).
Наличие заметки или тематической связи не подтверждает весь источник.

Личные заметки храните вне generated/, настройки — в .obsidian/.
Пакет не содержит личных заметок, настроек или учебной истории приложения.

Для обновления существующего хранилища используйте проверяемое обновление
по docs/obsidian-vault.md проекта. Не распаковывайте новый generated/
поверх прежнего: сначала должны быть проверены личные правки и ссылки.
Обновление меняет только управляемую папку, остальные файлы сохраняет.
Если оно остановилось, сохраните прежнюю папку и выясните причину.

Скрытые JSON в корне описывают скачанный пакет, а не личный прогресс.
'''.encode('utf-8')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _valid_member(name):
    if name in {REVIEWED, METADATA, 'README.md'}:
        return True
    if not name.startswith('generated/') or name.count('/') != 1:
        return False
    tail = name.removeprefix('generated/')
    return tail == STATE or valid_generated_name(tail)


def _zip_member(name, content):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info, content


def create_package(manifest: Path, destination: Path) -> dict:
    catalogue.prepared_notes(manifest)  # Require an ignored/private regular input.
    payload = manifest.read_bytes()
    files, counts = catalogue.render_reviewed_payload(payload)
    if destination.exists() or destination.is_symlink():
        raise VaultError('new_private_package_required')
    parent = destination.parent.resolve(strict=True)
    private_vault_location(parent)
    with tempfile.TemporaryDirectory(prefix='.vault-package-', dir=parent) as temporary:
        staging = Path(temporary)
        # Reuse the actual publication/privacy/managed-state checks, not a second
        # exporter that accepts a manifest's self-declared approval.
        write_vault(staging, files, published_content=True, reviewed_payload=payload)
        members = {'generated/' + path.name: path.read_bytes()
                   for path in (staging / 'generated').iterdir()}
        members.update({REVIEWED: payload, 'README.md': README})
        metadata = {'schema_version': 1, 'kind': 'PSYCHOLOGYATLAS_PRIVATE_VAULT',
                    'reviewed_notes_sha256': sha256(payload), 'counts': counts,
                    'files': {name: sha256(data) for name, data in sorted(members.items())}}
        members[METADATA] = (json.dumps(metadata, ensure_ascii=False, sort_keys=True,
                                       indent=2) + '\n').encode('utf-8')
        if len(members) > MAX_FILES or sum(map(len, members.values())) > MAX_BYTES:
            raise VaultError('vault_package_too_large')
        archive_path = staging / 'vault.zip'
        with zipfile.ZipFile(archive_path, 'w') as archive:
            for name, data in sorted(members.items()):
                info, data = _zip_member(name, data)
                archive.writestr(info, data, compresslevel=6)
        data = archive_path.read_bytes()
        digest = sha256(data)
        read_package_bytes(data, digest)
        # Exclusive creation protects unknown files and concurrent exports.
        with destination.open('xb') as output:
            destination.chmod(0o600)
            output.write(data)
        if destination.read_bytes() != data:
            raise VaultError('private_package_write_readback_failed')
    return {'sha256': digest, 'bytes': len(data), 'counts': counts,
            'reviewed_notes_sha256': metadata['reviewed_notes_sha256']}


def read_package_bytes(data: bytes, expected_sha256: str):
    if (not re.fullmatch(r'[a-f0-9]{64}', expected_sha256 or '')
            or not 0 < len(data) <= MAX_BYTES or sha256(data) != expected_sha256):
        raise VaultError('private_package_digest_mismatch')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if (not entries or len(entries) > MAX_FILES
                    or sum(entry.file_size for entry in entries) > MAX_BYTES
                    or len({entry.filename.casefold() for entry in entries}) != len(entries)):
                raise VaultError('invalid_private_package_layout')
            for entry in entries:
                if (entry.filename != entry.orig_filename or not _valid_member(entry.filename)
                        or entry.flag_bits & 1 or entry.is_dir()
                        or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)):
                    raise VaultError('unsafe_private_package_member')
            members = {entry.filename: archive.read(entry) for entry in entries}
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise VaultError('invalid_private_package_archive') from error
    try:
        metadata = json.loads(members[METADATA])
        if (set(metadata) != {'schema_version', 'kind', 'reviewed_notes_sha256', 'counts', 'files'}
                or metadata['schema_version'] != 1 or metadata['kind'] != 'PSYCHOLOGYATLAS_PRIVATE_VAULT'
                or metadata['reviewed_notes_sha256'] != catalogue.REVIEWED_NOTES_SHA256
                or metadata['files'] != {name: sha256(body) for name, body in members.items()
                                         if name != METADATA}):
            raise VaultError('private_package_manifest_mismatch')
        payload = members[REVIEWED]
        files, counts = catalogue.render_reviewed_payload(payload)
        actual = {name.removeprefix('generated/'): body for name, body in members.items()
                  if name.startswith('generated/') and name != 'generated/' + STATE}
        state = json.loads(members['generated/' + STATE])
        if (actual != files or metadata['counts'] != counts or members['README.md'] != README
                or state != {'schema_version': 1, 'files': {name: sha256(body)
                                                           for name, body in files.items()}}):
            raise VaultError('private_package_unreviewed_output')
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeError) as error:
        raise VaultError('invalid_private_package_metadata') from error
    return files, payload, metadata


def read_package(archive: Path, expected_sha256: str):
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > MAX_BYTES:
        raise VaultError('private_regular_package_required')
    return read_package_bytes(archive.read_bytes(), expected_sha256)


def apply_package(archive: Path, expected_sha256: str, vault: Path) -> dict:
    """Update only generated/. Existing root metadata remains a dated receipt."""
    files, payload, metadata = read_package(archive, expected_sha256)
    result = write_vault(vault, files, published_content=True, reviewed_payload=payload)
    actual = vault.resolve(strict=True) / 'generated'
    state = json.loads((actual / STATE).read_bytes())
    if any(sha256((actual / name).read_bytes()) != digest for name, digest in state['files'].items()):
        raise VaultError('private_vault_update_readback_failed')
    return {**result, 'package_sha256': expected_sha256,
            'reviewed_notes_sha256': metadata['reviewed_notes_sha256'],
            'unmanaged_paths_written': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create', 'check', 'apply'])
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--sha256')
    parser.add_argument('--vault', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'create':
            if args.manifest is None:
                raise VaultError('private_reviewed_manifest_required')
            result = create_package(args.manifest, args.archive)
        elif args.action == 'check':
            _, _, metadata = read_package(args.archive, args.sha256)
            result = {'sha256': args.sha256, 'counts': metadata['counts']}
        else:
            if args.vault is None:
                raise VaultError('private_vault_target_required')
            result = apply_package(args.archive, args.sha256, args.vault)
    except (OSError, ValueError, TypeError) as error:
        message = str(error) if isinstance(error, VaultError) else type(error).__name__
        print('PRIVATE_VAULT_STOP ' + message)
        return 1
    print('PRIVATE_VAULT_OK ' + json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
