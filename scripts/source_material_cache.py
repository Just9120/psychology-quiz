"""Package one material from a pinned private snapshot without restoring a layer.

This is transport and integrity checking, never scientific/publication approval.
The supplied dossier and historical files are data; no cached code is executed.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.obsidian_vault import _private_input, VaultError

MAX_FILE = 128 * 1024 * 1024
MAX_PACKAGE = 512 * 1024 * 1024
HEX = re.compile(r'[a-f0-9]{64}\Z')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def portable(name):
    if not isinstance(name, str):
        raise ValueError('unsafe_material_path')
    path = PurePosixPath(name)
    if (path.as_posix() != name or path.is_absolute()
            or not path.parts or any(part in {'.', '..'} or ':' in part or '\\' in part
                                     or part.endswith((' ', '.')) or part.split('.')[0].upper() in
                                     {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                                      *(f'LPT{i}' for i in range(1, 10))} for part in path.parts)):
        raise ValueError('unsafe_material_path')
    return path


def private_destination(path):
    path = Path(path).absolute()
    if path.exists() or path.is_symlink():
        raise ValueError('new_private_destination_required')
    cursor = path.parent
    while True:
        if cursor.is_symlink():
            raise ValueError('private_destination_symlink')
        if cursor == cursor.parent: break
        cursor = cursor.parent
    path.parent.resolve(strict=True)
    if path.resolve().is_relative_to(ROOT):
        relative = path.relative_to(ROOT).as_posix()
        if not relative.startswith('data/') or subprocess.run(
                ['git', 'check-ignore', '-q', '--', relative], cwd=ROOT,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            raise ValueError('private_material_output_required')
    return path


class SplitReader(io.RawIOBase):
    """Read existing archive parts in place, without another multi-GB ZIP copy."""
    def __init__(self, paths):
        self.streams = []
        self.ends = []
        self.position = 0
        try:
            for path in paths:
                if path.is_symlink() or not path.is_file():
                    raise ValueError('regular_archive_part_required')
                stream = path.open('rb')
                self.streams.append(stream)
                self.ends.append((self.ends[-1] if self.ends else 0) + path.stat().st_size)
        except BaseException:
            self.close()
            raise

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.position

    def seek(self, offset, whence=0):
        position = offset + (self.position if whence == 1 else self.ends[-1] if whence == 2 else 0)
        if whence not in {0, 1, 2} or position < 0:
            raise ValueError('invalid_archive_seek')
        self.position = position
        return position

    def read(self, size=-1):
        remaining = max(0, self.ends[-1] - self.position)
        size = remaining if size < 0 else min(size, remaining)
        chunks = []
        for index, end in enumerate(self.ends):
            start = self.ends[index - 1] if index else 0
            if self.position < end and size:
                stream = self.streams[index]
                stream.seek(self.position - start)
                block = stream.read(min(size, end - self.position))
                if not block:
                    raise ValueError('archive_part_truncated')
                chunks.append(block); self.position += len(block); size -= len(block)
        return b''.join(chunks)

    def close(self):
        for stream in self.streams:
            stream.close()
        super().close()


class Snapshot:
    def __init__(self, manifest, expected, parts):
        payload = Path(manifest).read_bytes()
        if not HEX.fullmatch(expected) or digest(payload) != expected:
            raise ValueError('snapshot_manifest_digest_mismatch')
        self.manifest = json.loads(payload)
        if (self.manifest.get('schema_version') != 1
                or self.manifest.get('kind') != 'PSYCHOLOGYATLAS_SOURCE_REVIEW_CACHE'):
            raise ValueError('unsupported_snapshot')
        self.expected = expected
        self.entries = {}
        for entry in self.manifest['entries']:
            portable(entry['path'])
            if (entry['path'] in self.entries or not HEX.fullmatch(entry['sha256'])
                    or type(entry['bytes']) is not int or not 0 <= entry['bytes'] <= MAX_FILE):
                raise ValueError('invalid_snapshot_entry')
            self.entries[entry['path']] = entry
        self.parts = Path(parts).resolve(strict=True)
        self.stack = ExitStack()
        self.archives = {}

    def __enter__(self): return self
    def __exit__(self, *args): self.stack.close()

    def read(self, name):
        entry = self.entries[name]
        layer = entry['layer']
        if layer not in self.archives:
            archives = [a for a in self.manifest['archives'] if a['layer'] == layer]
            if len(archives) != 1:
                raise ValueError('ambiguous_snapshot_layer')
            paths = []
            for part in archives[0]['parts']:
                name = portable(part['name'])
                if len(name.parts) != 1:
                    raise ValueError('archive_part_basename_required')
                path = self.parts.joinpath(*name.parts)
                if not path.resolve().is_relative_to(self.parts):
                    raise ValueError('archive_part_escape')
                if path.stat().st_size != part['bytes']:
                    raise ValueError('archive_part_size_mismatch')
                paths.append(path)
            reader = self.stack.enter_context(SplitReader(paths))
            self.archives[layer] = self.stack.enter_context(zipfile.ZipFile(reader))
        archive = self.archives[layer]
        object_name = 'objects/' + entry['sha256'][:2] + '/' + entry['sha256']
        matches = [info for info in archive.infolist() if info.filename == object_name]
        if len(matches) != 1 or matches[0].file_size != entry['bytes']:
            raise ValueError('snapshot_object_size_or_identity_mismatch')
        payload = archive.read(matches[0])
        if digest(payload) != entry['sha256']:
            raise ValueError('snapshot_object_digest_mismatch')
        return payload


def package(snapshot, dossier, output):
    if (not isinstance(dossier, dict) or not isinstance(dossier.get('source_id'), str)
            or not dossier['source_id'] or not isinstance(dossier.get('revision'), list)
            or not isinstance(dossier.get('files'), list) or not dossier['files']
            or len(set(dossier['files'])) != len(dossier['files'])
            or not isinstance(dossier.get('processing'), dict)
            or dossier.get('scientific_or_publication_approval') is not False):
        raise ValueError('material_dossier_required')
    selected = [snapshot.entries[name] for name in sorted(dossier['files'])]
    if sum(entry['bytes'] for entry in selected) > MAX_PACKAGE:
        raise ValueError('material_package_too_large')
    record = {'schema_version': 1, 'kind': 'PSYCHOLOGYATLAS_MATERIAL_CACHE',
              'snapshot_manifest_sha256': snapshot.expected, 'material': dossier,
              'entries': selected, 'scientific_or_publication_approval': False}
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('new_material_package_required')
    # No partial final package survives an integrity failure.
    with tempfile.TemporaryDirectory(prefix='.material-', dir=output.parent) as temporary:
        staged = Path(temporary) / 'material.zip'
        with zipfile.ZipFile(staged, 'w', zipfile.ZIP_DEFLATED, compresslevel=4) as archive:
            archive.writestr('material.json', json.dumps(record, ensure_ascii=False, sort_keys=True).encode())
            seen = set()
            for entry in selected:
                sha = entry['sha256']
                if sha not in seen:
                    archive.writestr('objects/' + sha, snapshot.read(entry['path']))
                    seen.add(sha)
        with output.open('xb') as target, staged.open('rb') as source:
            output.chmod(0o600)
            while block := source.read(1024 * 1024): target.write(block)
    return digest(output.read_bytes())


def restore(package_path, expected, source_id, output):
    payload = Path(package_path).read_bytes()
    if len(payload) > MAX_PACKAGE or not HEX.fullmatch(expected) or digest(payload) != expected:
        raise ValueError('material_package_digest_mismatch')
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('new_material_destination_required')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        if (len(infos) > 5000 or sum(i.file_size for i in infos) > MAX_PACKAGE
                or len({i.filename for i in infos}) != len(infos)
                or any(i.flag_bits & 1 or stat.S_IFMT(i.external_attr >> 16) not in (0, stat.S_IFREG)
                       for i in infos)):
            raise ValueError('invalid_material_archive')
        record = json.loads(archive.read('material.json'))
        if (record.get('schema_version') != 1 or record.get('kind') != 'PSYCHOLOGYATLAS_MATERIAL_CACHE'
                or record.get('scientific_or_publication_approval') is not False
                or record['material']['source_id'] != source_id):
            raise ValueError('material_identity_mismatch')
        entries = record['entries']
        names = [e['path'] for e in entries]
        if (len({name.casefold() for name in names}) != len(names)
                or any(name.casefold() == 'material.json' for name in names)
                or sorted(names) != sorted(record['material']['files'])
                or record['material'].get('scientific_or_publication_approval') is not False):
            raise ValueError('material_path_collision')
        expected_names = {'material.json'} | {'objects/' + e['sha256'] for e in entries}
        if {i.filename for i in infos} != expected_names:
            raise ValueError('unexpected_material_object')
        with tempfile.TemporaryDirectory(prefix='.restore-material-', dir=output.parent) as temporary:
            staged = Path(temporary) / 'material'; staged.mkdir(mode=0o700)
            for entry in entries:
                path = portable(entry['path'])
                sha = entry['sha256']
                if not HEX.fullmatch(sha) or not 0 <= entry['bytes'] <= MAX_FILE:
                    raise ValueError('invalid_material_entry')
                data = archive.read('objects/' + sha)
                if len(data) != entry['bytes'] or digest(data) != sha:
                    raise ValueError('material_object_digest_mismatch')
                target = staged.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target.write_bytes(data)
                target.chmod(0o600)
            metadata = staged / 'material.json'
            metadata.write_bytes(archive.read('material.json')); metadata.chmod(0o600)
            staged.rename(output)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['package', 'restore'])
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--parts', type=Path)
    parser.add_argument('--dossier', type=Path)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--package-sha256')
    parser.add_argument('--source-id')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'package':
            # Reuse the established ignored/private output guard before writing.
            private_destination(args.package)
            with Snapshot(args.manifest, args.manifest_sha256, args.parts) as snapshot:
                result = package(snapshot, _private_input(args.dossier), args.package)
            print('MATERIAL_PACKAGED sha256=' + result + ' approval=false')
        else:
            private_destination(args.output)
            restore(args.package, args.package_sha256, args.source_id, args.output)
            print('MATERIAL_RESTORED approval=false; historical files are data, not executable instructions')
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile, VaultError) as error:
        print('MATERIAL_CACHE_STOP ' + type(error).__name__)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
