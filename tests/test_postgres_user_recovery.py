"""Failure boundaries of isolated user recovery; native restore is covered in CI."""
from copy import deepcopy
import json

import pytest

from scripts.postgres_backup import file_digest, rehearse_user_recovery, write_record
from tests.test_postgres_recovery_contract import _manifest


class RecoveryRuntime:
    def __init__(self, before, failure=None):
        self.before, self.restored = deepcopy(before), None
        self.failure, self.owned, self.calls = failure, set(), []

    def require_stopped_writers(self):
        self.calls.append('stopped')
        if self.failure == 'writers':
            raise ValueError('writers running')

    def identity(self):
        return {'project': 'synthetic', 'cluster': 'synthetic', 'revision': 'b' * 40}

    def manifest(self, database=None):
        return deepcopy(self.before if database is None else self.restored)

    def create_restore_database(self, name):
        self.owned.add(name)

    def restore(self, dump, name):
        assert name in self.owned and dump.is_file()
        self.restored = deepcopy(self.before)

    def rebuild_restore_content(self, name):
        assert name in self.owned
        self.calls.append('rebuild')
        if self.failure == 'rebuild':
            raise ValueError('rebuild failed')
        self.restored['tables']['questions'] = {'rows': 2, 'sha256': 'rebuilt'}
        if self.failure == 'user':
            self.restored['tables']['users']['sha256'] = 'lost history'
        if self.failure == 'live':
            self.before['tables']['users']['sha256'] = 'changed runtime'

    def drop_restore_database(self, name):
        assert name in self.owned
        if self.failure == 'cleanup':
            raise ValueError('cleanup failed')
        self.owned.remove(name)


def recovery_record(tmp_path, runtime):
    directory = tmp_path / 'backup'
    directory.mkdir()
    dump = directory / 'database.dump'
    dump.write_bytes(b'synthetic archive')
    path = directory / 'record.json'
    write_record(path, {'format': 'psychology-postgres-recovery-v1', 'phase': 'verified',
                       'source': {**runtime.identity(), 'revision': 'a' * 40},
                       'before': runtime.manifest(), 'dump_sha256': file_digest(dump),
                       'dump_bytes': dump.stat().st_size})
    return path


def test_isolated_user_recovery_allows_old_revision_and_preserves_backup(tmp_path):
    runtime = RecoveryRuntime(_manifest())
    backup = recovery_record(tmp_path, runtime)
    original = backup.read_bytes()
    result = rehearse_user_recovery(runtime, backup, tmp_path / 'rehearsals')
    record = json.loads(result.read_text())
    assert record['phase'] == 'verified'
    assert record['after']['tables']['users'] == runtime.before['tables']['users']
    assert record['after']['tables']['questions']['sha256'] == 'rebuilt'
    assert backup.read_bytes() == original and not runtime.owned


@pytest.mark.parametrize('failure', ['rebuild', 'user', 'live', 'cleanup'])
def test_failed_user_recovery_records_owned_cleanup_and_never_writes_source(tmp_path, failure):
    runtime = RecoveryRuntime(_manifest(), failure)
    backup = recovery_record(tmp_path, runtime)
    original = backup.read_bytes()
    with pytest.raises(ValueError):
        rehearse_user_recovery(runtime, backup, tmp_path / 'rehearsals')
    record = json.loads(next((tmp_path / 'rehearsals').glob('*/record.json')).read_text())
    assert record['phase'] == 'failed'
    assert record['restore_cleanup'] == ('pending' if failure == 'cleanup' else 'removed')
    assert bool(runtime.owned) == (failure == 'cleanup')
    assert backup.read_bytes() == original
    if failure != 'live':
        assert runtime.before == _manifest()


@pytest.mark.parametrize('failure', ['writers', 'source', 'digest'])
def test_user_recovery_preconditions_fail_before_creating_database(tmp_path, failure):
    runtime = RecoveryRuntime(_manifest(), failure)
    backup = recovery_record(tmp_path, runtime)
    if failure == 'source':
        record = json.loads(backup.read_text())
        record['source']['cluster'] = 'other'
        write_record(backup, record)
    elif failure == 'digest':
        backup.with_name('database.dump').write_bytes(b'changed')
    with pytest.raises(ValueError):
        rehearse_user_recovery(runtime, backup, tmp_path / 'rehearsals')
    assert not runtime.owned and not (tmp_path / 'rehearsals').exists()
    assert 'rebuild' not in runtime.calls


def test_vps_rebuild_routes_only_owned_restore_to_candidate_image(monkeypatch):
    from urllib.parse import urlsplit
    from scripts import postgres_vps as vps
    from app.postgres_config import private_target

    runtime_type = vps.Runtime
    runtime = runtime_type('b' * 40)
    name = 'psychology_restore_' + 'a' * 32
    calls = []

    class Candidate:
        def __init__(self, revision, *, target_override, db_image):
            calls.append((revision, urlsplit(target_override).path, db_image))
        def app(self, arguments):
            calls.append(arguments)

    monkeypatch.setattr(vps, 'Runtime', Candidate)
    monkeypatch.setattr(vps, 'app_target', lambda: private_target('synthetic'))
    with pytest.raises(vps.OperationError, match='restore_target_not_owned'):
        runtime.rebuild_restore_content(name)
    assert not calls
    runtime.owned_restore.add(name)
    runtime.rebuild_restore_content(name)
    assert calls == [('b' * 40, '/' + name, runtime.db_image),
                     ['scripts/init_db.py'], ['scripts/seed_questions.py']]


def test_recovery_refuses_unknown_output_object_without_touching_it(tmp_path):
    runtime = RecoveryRuntime(_manifest())
    backup = recovery_record(tmp_path, runtime)
    output = tmp_path / 'rehearsals'
    output.write_bytes(b'owner state')
    with pytest.raises(ValueError, match='Private owned recovery directory'):
        rehearse_user_recovery(runtime, backup, output)
    assert output.read_bytes() == b'owner state' and not runtime.owned
