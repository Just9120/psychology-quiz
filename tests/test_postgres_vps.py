"""Cutover failure/resume behavior with isolated filesystem/system boundaries."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.postgres_config import private_target, validate_delivery_target
from scripts import postgres_vps as vps
from scripts.postgres_backup import backup_and_rehearse

SHA = 'a' * 40


@pytest.mark.parametrize('input_kind', ['none', 'empty', 'bytes', 'file'])
def test_subprocess_keeps_operator_input_and_accepts_explicit_payload(tmp_path, input_kind):
    """Docker-like stdin readers must not swallow the caller's remaining commands."""
    caller_input = b'prepare\ncutover\nstatus\n'
    payload = b'synthetic SQL or archive\x00\xff\n'
    source = tmp_path / 'input.bin'
    source.write_bytes(payload)
    driver = '''
import json
from pathlib import Path
import sys
from scripts import postgres_vps as vps

vps.PROJECT = Path.cwd()
kind, source = sys.argv[1:]
command = [sys.executable, '-c', 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())']
if kind == 'file':
    with open(source, 'rb') as stream:
        output = vps.run(command, input_file=stream)
elif kind == 'bytes':
    output = vps.run(command, data=Path(source).read_bytes())
elif kind == 'empty':
    output = vps.run(command, data=b'')
else:
    output = vps.run(command)
print(json.dumps({'child': output.hex(), 'caller': sys.stdin.buffer.read().hex()}))
'''
    result = subprocess.run(
        [sys.executable, '-c', driver, input_kind, str(source)],
        cwd=Path(__file__).resolve().parents[1], input=caller_input,
        capture_output=True, timeout=20, check=True,
    )
    assert json.loads(result.stdout) == {
        'child': (b'' if input_kind in {'none', 'empty'} else payload).hex(),
        'caller': caller_input.hex(),
    }


@pytest.mark.parametrize('source', [b'A=one\nDATABASE_URL=\nB=two\n', b'A=one\r\nexport DATABASE_URL=""\r\nB=two', b'A=one'])
def test_config_edit_preserves_other_values_and_adds_one_target(source):
    result = vps.replace_database_url(source, private_target('synthetic'))
    assert result.count(b'DATABASE_URL=') == 1
    assert b'A=one' in result
    if b'B=two' in source: assert result.endswith(b'B=two\n') or result.endswith(b'B=two')
    assert private_target('synthetic').encode() in result


@pytest.mark.parametrize('source', [b'DATABASE_URL=x\n', b'DATABASE_URL=\nDATABASE_URL=\n', b'DATABASE_URL="multiline\nvalue"\n'])
def test_config_edit_refuses_nonempty_or_ambiguous_values(source):
    with pytest.raises(vps.OperationError): vps.replace_database_url(source, private_target('synthetic'))


@pytest.mark.parametrize('target', ['postgresql://a:b@external/db', private_target('x')+'?options=-csearch_path=foreign', private_target('x').replace('5432','1234')])
def test_delivery_target_is_private_and_exact(target):
    with pytest.raises(ValueError): validate_delivery_target(target)
    validate_delivery_target(private_target('synthetic'))


@pytest.fixture
def cutover_host(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    state = project / '.postgres'
    state.mkdir(parents=True)
    (project / '.env').write_bytes(b'BOT_TOKEN=synthetic\nDATABASE_URL=\n')
    record = {'format':vps.FORMAT,'project':str(project),'revision':SHA,'phase':'prepared','cluster':'test'}
    vps.write_record(state / 'state.json', record)
    host = SimpleNamespace(project=project, state=state, calls=[], fail=None, running=True, writes=False)
    monkeypatch.setattr(vps, 'PROJECT', project)
    monkeypatch.setattr(vps, 'STATE', state)
    monkeypatch.setattr(vps, 'app_target', lambda: private_target('synthetic'))
    monkeypatch.setattr(vps, 'private_file', lambda path: path.read_bytes())
    monkeypatch.setattr(vps, 'preflight', lambda runtime: {})
    monkeypatch.setattr(vps.os, 'chown', lambda *args: None, raising=False)

    def fail_at(action):
        host.calls.append(action)
        if host.fail == action:
            host.fail = None
            raise vps.OperationError('injected_' + action)

    class FakeRuntime:
        def __init__(self, revision, **kwargs): self.revision = revision
        def require_stopped_writers(self): assert not host.running
        def require_running_revision(self): assert host.running
        def container(self, service): return {'Image':'sha256:test'}
        def app(self, arguments, **kwargs):
            if arguments[:2] == ['scripts/deployment_db.py','backup']:
                fail_at('sqlite_backup')
                directory = project / 'data/backups/release-test'
                directory.mkdir(parents=True, exist_ok=True)
                (directory / 'quiz.sqlite3').write_bytes(b'snapshot')
                return b'/data/backups/release-test/quiz.sqlite3\n'
            if arguments[:2] == ['scripts/postgres_storage.py','import']:
                assert not host.writes
                fail_at('import')
                return b''
            fail_at('business_check')
            return b''

    def compose(arguments, **kwargs):
        if arguments[0] == 'stop': host.running = False
        if arguments[0] == 'up':
            # Simulate one writer accepting data before a partial start fails.
            host.running, host.writes = True, True
            fail_at('start')
        return b''

    def native_backup(runtime):
        fail_at('native_backup')
        return state / 'backups/release-test/record.json'

    monkeypatch.setattr(vps, 'Runtime', FakeRuntime)
    monkeypatch.setattr(vps, 'configured_runtime', lambda revision: (FakeRuntime(revision), json.loads((state / 'state.json').read_text())))
    monkeypatch.setattr(vps, 'compose', compose)
    monkeypatch.setattr(vps, 'backup', native_backup)
    monkeypatch.setattr(vps, 'verify_backup', lambda *args: fail_at('preservation'))
    monkeypatch.setattr(vps, 'post_checks', lambda *args: fail_at('post_checks'))
    return host


@pytest.mark.parametrize('failure', ['sqlite_backup','import','native_backup','preservation','start','post_checks'])
def test_interrupted_cutover_resumes_without_sqlite_rollback_or_reimport_after_writes(cutover_host, failure):
    host = cutover_host
    original = (host.project / '.env').read_bytes()
    host.fail = failure
    with pytest.raises(vps.OperationError): vps.cutover(SHA)
    assert not host.running
    failed = json.loads((host.state / 'state.json').read_text())
    if failure in {'start','post_checks'}:
        assert failed['phase'] == 'postgres_writers_starting'
        assert private_target('synthetic').encode() in (host.project / '.env').read_bytes()
    else:
        assert (host.project / '.env').read_bytes() == original
    prior_imports = host.calls.count('import')
    result = vps.cutover(SHA)
    assert result['phase'] == 'complete'
    assert host.running and host.writes
    if failure in {'start','post_checks'}: assert host.calls.count('import') == prior_imports
    assert (host.state / 'sqlite.env').read_bytes() == original
    # Re-running a completed cutover verifies it without stopping or importing.
    previous = list(host.calls)
    assert vps.cutover(SHA)['phase'] == 'complete'
    assert host.calls == previous + ['post_checks']


def test_environment_change_during_cutover_is_preserved(cutover_host):
    host = cutover_host
    host.fail = 'native_backup'
    with pytest.raises(vps.OperationError): vps.cutover(SHA)
    changed = b'BOT_TOKEN=changed-by-owner\nDATABASE_URL=\n'
    (host.project / '.env').write_bytes(changed)
    with pytest.raises(vps.OperationError, match='config_changed'): vps.cutover(SHA)
    assert (host.project / '.env').read_bytes() == changed
    assert not host.running and not host.writes


def test_backup_refuses_running_writer_before_dump(tmp_path):
    class Running:
        def require_stopped_writers(self): raise vps.OperationError('writers_running')
    with pytest.raises(vps.OperationError): backup_and_rehearse(Running(), tmp_path / 'backups')
    assert not (tmp_path / 'backups').exists()


def test_wrong_candidate_image_is_refused_before_running_app(monkeypatch):
    calls = []
    def compose(arguments, **kwargs):
        calls.append(arguments)
        return b'candidate-image\n'
    monkeypatch.setattr(vps, 'compose', compose)
    monkeypatch.setattr(vps, 'run', lambda *args, **kwargs: json.dumps([{'Config':{'Labels':{'org.opencontainers.image.revision':'b'*40}}}]).encode())
    with pytest.raises(vps.OperationError, match='candidate_application_image_revision'):
        vps.Runtime(SHA).app(['scripts/postgres_storage.py','init'])
    assert calls == [['config','--images',vps.SERVICES[0]]]


def test_source_mapping_rejects_foreign_persistent_mount():
    class Foreign:
        def container(self, service):
            return {'Mounts':[{'Destination':'/data','Type':'bind','Source':'/other-project/data'}]}
    with pytest.raises(vps.OperationError, match='persistent_storage'):
        vps.source_path(Foreign())
