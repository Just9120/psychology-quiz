"""Boot the actual Compose PG profile on an isolated CI-only project."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

import pytest

from app.postgres_config import PG_IMAGE, PG_SERVICE


def test_private_compose_service_initializes_with_mounted_secret_and_checksums(tmp_path):
    if not os.environ.get('CI') or shutil.which('docker') is None:
        pytest.skip('Requires the disposable Linux Docker CI runner')
    project = 'psychology-test-' + uuid.uuid4().hex
    assert project.startswith('psychology-test-')
    (tmp_path / 'docker-compose.yml').write_text(Path('docker-compose.yml').read_text(), encoding='utf-8')
    (tmp_path / '.env').write_text('BOT_TOKEN=synthetic\n', encoding='utf-8')
    state = tmp_path / '.postgres'
    state.mkdir(mode=0o700)
    (state / 'data').mkdir()
    password = state / 'admin.password'
    password.write_text('synthetic-compose-only\n', encoding='utf-8')
    password.chmod(0o400)
    base = ['docker','compose','--project-directory',str(tmp_path),'-f',str(tmp_path/'docker-compose.yml'),'-p',project]
    def command(args, **kwargs):
        result = subprocess.run(args, cwd=tmp_path, capture_output=True, timeout=120, **kwargs)
        assert result.returncode == 0, 'Isolated Compose test command failed: ' + result.stderr.decode(errors='replace')[-2000:]
        return result.stdout
    # Only this temporary file is mounted; the real VPS uses the same uid/mode.
    def secret_owner(uid):
        command(['docker','run','--rm','--network','none','--mount',f'type=bind,source={password},target=/owned-secret',
                 '--entrypoint','chown',PG_IMAGE,str(uid),'/owned-secret'])
    started = False
    try:
        assert command(['docker','run','--rm','--network','none','--entrypoint','id',PG_IMAGE,'-u','postgres']).strip() == b'999'
        secret_owner(999)
        default = json.loads(command(base + ['config','--format','json']))
        assert PG_SERVICE not in default['services']
        started = True  # Cleanup even if up starts only partially.
        command(base + ['--profile','postgres','up','-d','--no-deps',PG_SERVICE])
        container = command(base + ['--profile','postgres','ps','--all','--quiet',PG_SERVICE]).decode().strip()
        assert container and '\n' not in container
        for attempt in range(30):
            item = json.loads(command(['docker','inspect',container]))[0]
            assert item['Config']['Labels']['com.docker.compose.project'] == project
            if item['State'].get('Health',{}).get('Status') == 'healthy': break
            time.sleep(1)
        else: pytest.fail('Private PostgreSQL Compose service never became healthy')
        assert not item['HostConfig'].get('PortBindings')
        assert set(item['NetworkSettings']['Networks']) == {project + '_default'}
        data = [m for m in item['Mounts'] if m['Destination'] == '/var/lib/postgresql']
        assert len(data) == 1 and Path(data[0]['Source']) == state / 'data'
        wrapper = 'export PGPASSWORD="$(cat /run/secrets/postgres_admin_password)"; exec psql -X -qAt -U postgres -d postgres -v ON_ERROR_STOP=1'
        result = command(base + ['--profile','postgres','exec','-T',PG_SERVICE,'sh','-eu','-c',wrapper],
                         input=b'SHOW data_checksums; SHOW server_version; SHOW password_encryption;')
        assert result.decode().splitlines()[0] == 'on'
        assert result.decode().splitlines()[1].split()[0] == '18.6'
        assert result.decode().splitlines()[2] == 'scram-sha-256'
    finally:
        if started:
            command(base + ['--profile','postgres','down'])
        secret_owner(os.getuid())
        # PG owns only this disposable bind directory, not arbitrary host paths.
        command(['docker','run','--rm','--network','none','--mount',f'type=bind,source={state / "data"},target=/owned-data',
                 '--entrypoint','chown',PG_IMAGE,'-R',str(os.getuid()),'/owned-data'])
