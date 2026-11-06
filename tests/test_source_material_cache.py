import copy
import io
import json
import subprocess
import zipfile

import pytest

from scripts import source_material_cache as cache


@pytest.fixture
def saved(tmp_path):
    files = {'owned/text.txt': b'Exact source text\r\n',
             'owned/review.json': b'{"known_hold":"retain diagnostic prohibition"}',
             'owned/original.pdf': b'%PDF-synthetic', 'owned/page.png': b'synthetic image'}
    entries = []
    archives = []
    for layer, names in [('core', ['owned/text.txt', 'owned/review.json']),
                         ('originals', ['owned/original.pdf']), ('renders', ['owned/page.png'])]:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                sha = cache.digest(files[name])
                entries.append({'path': name, 'sha256': sha, 'bytes': len(files[name]), 'layer': layer})
                archive.writestr('objects/' + sha[:2] + '/' + sha, files[name])
        payload = stream.getvalue()
        midpoint = len(payload) // 2
        parts = []
        for index, block in enumerate([payload[:midpoint], payload[midpoint:]]):
            name = f'{layer}.{index}'
            (tmp_path / name).write_bytes(block)
            parts.append({'name': name, 'bytes': len(block), 'sha256': cache.digest(block)})
        archives.append({'layer': layer, 'parts': parts})
    manifest = {'schema_version': 1, 'kind': 'PSYCHOLOGYATLAS_SOURCE_REVIEW_CACHE',
                'entries': entries, 'archives': archives}
    path = tmp_path / 'snapshot.json'
    path.write_text(json.dumps(manifest))
    dossier = {'source_id': 'synthetic-source', 'revision': ['date', 'title', 'mime'],
               'extraction_profile': 'exact-profile', 'files': list(files),
               'processing': {'review_state': 'conflict', 'reason': 'KEEP',
                              'related_source_ids': ['other-source']},
               'scientific_or_publication_approval': False}
    return path, cache.digest(path.read_bytes()), dossier, files


def test_one_material_restores_exact_bytes_holds_and_profile_without_other_layer(tmp_path, saved):
    manifest, sha, dossier, files = saved
    original = copy.deepcopy(dossier)
    with cache.Snapshot(manifest, sha, tmp_path) as snapshot:
        result = cache.package(snapshot, dossier, tmp_path / 'one.zip')
    record = cache.restore(tmp_path / 'one.zip', result, 'synthetic-source', tmp_path / 'restored')
    assert record['material'] == original == dossier
    assert record['snapshot_manifest_sha256'] == sha
    assert all((tmp_path / 'restored' / name).read_bytes() == body for name, body in files.items())
    assert record['scientific_or_publication_approval'] is False
    # A caller can request just core objects even when the other layers are absent.
    for path in tmp_path.glob('originals.*'): path.unlink()
    for path in tmp_path.glob('renders.*'): path.unlink()
    dossier['files'] = ['owned/text.txt', 'owned/review.json']
    dossier['unrestored_layers'] = ['originals', 'renders']
    with cache.Snapshot(manifest, sha, tmp_path) as snapshot:
        cache.package(snapshot, dossier, tmp_path / 'core.zip')
        assert set(snapshot.archives) == {'core'}


def test_tamper_identity_and_existing_destination_fail_without_overwrite(tmp_path, saved):
    manifest, sha, dossier, _ = saved
    with pytest.raises(ValueError, match='manifest_digest'):
        cache.Snapshot(manifest, '0' * 64, tmp_path)
    with cache.Snapshot(manifest, sha, tmp_path) as snapshot:
        package_sha = cache.package(snapshot, dossier, tmp_path / 'one.zip')
    for digest, source, error in [('0' * 64, 'synthetic-source', 'package_digest'),
                                  (package_sha, 'foreign-source', 'identity')]:
        with pytest.raises(ValueError, match=error):
            cache.restore(tmp_path / 'one.zip', digest, source, tmp_path / 'output')
        assert not (tmp_path / 'output').exists()
    output = tmp_path / 'output'; output.mkdir()
    (output / 'personal.md').write_text('Owner data')
    with pytest.raises(ValueError, match='new_material_destination'):
        cache.restore(tmp_path / 'one.zip', package_sha, 'synthetic-source', output)
    assert (output / 'personal.md').read_text() == 'Owner data'


@pytest.mark.parametrize('path', ['../escape', '/absolute', 'a/../../escape', 'a\\escape',
                                  'C:/escape', 'owned/AUX.md', 'owned/name.', 'owned/name '])
def test_portable_paths_cannot_escape_or_alias_windows_files(path):
    with pytest.raises(ValueError, match='unsafe_material_path'):
        cache.portable(path)


def test_corrupt_selected_object_never_creates_final_package(tmp_path, saved):
    manifest, sha, dossier, _ = saved
    with cache.Snapshot(manifest, sha, tmp_path) as snapshot:
        # Exact object digest remains mandatory even if ZIP CRC is internally valid.
        archive = snapshot.manifest['archives'][0]
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as output:
            for entry in snapshot.manifest['entries'][:2]:
                output.writestr('objects/' + entry['sha256'][:2] + '/' + entry['sha256'], b'x' * entry['bytes'])
        body = stream.getvalue(); midpoint = len(body) // 2
        for part, block in zip(archive['parts'], [body[:midpoint], body[midpoint:]]):
            (tmp_path / part['name']).write_bytes(block); part['bytes'] = len(block)
        with pytest.raises(ValueError, match='object_digest'):
            cache.package(snapshot, dossier, tmp_path / 'bad.zip')
    assert not (tmp_path / 'bad.zip').exists()
    assert not list(tmp_path.glob('.material-*'))


def test_approval_cannot_be_created_by_transport(tmp_path, saved):
    manifest, sha, dossier, _ = saved
    dossier['scientific_or_publication_approval'] = True
    with cache.Snapshot(manifest, sha, tmp_path) as snapshot:
        with pytest.raises(ValueError, match='dossier_required'):
            cache.package(snapshot, dossier, tmp_path / 'bad.zip')


def test_partial_read_seeks_across_part_boundary_and_closes_handles(tmp_path):
    paths = [tmp_path / 'a', tmp_path / 'b']
    paths[0].write_bytes(b'abc'); paths[1].write_bytes(b'defgh')
    with cache.SplitReader(paths) as stream:
        assert stream.read(4) == b'abcd'
        assert stream.seek(-3, 2) == 5 and stream.read() == b'fgh'
        assert stream.seek(2) == 2 and stream.read(4) == b'cdef'
    assert all(handle.closed for handle in stream.streams)


def test_private_destination_rejects_existing_and_public_repo_paths(tmp_path, monkeypatch):
    target = tmp_path / 'one'; target.write_text('existing')
    with pytest.raises(ValueError, match='new_private_destination'):
        cache.private_destination(target)
    repo = tmp_path / 'repo'
    repo.mkdir()
    subprocess.run(['git', 'init', '--quiet', str(repo)], check=True)
    (repo / '.gitignore').write_text('/data/\n', encoding='utf-8')
    (repo / 'content').mkdir()
    (repo / 'data').mkdir()
    monkeypatch.setattr(cache, 'ROOT', repo.resolve())
    with pytest.raises(ValueError, match='private_material_output'):
        cache.private_destination(cache.ROOT / 'content/new-material.zip')
    assert cache.private_destination(cache.ROOT / 'data/new-material.zip').parent == cache.ROOT / 'data'
