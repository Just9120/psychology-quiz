"""Boot the actual Compose PG profile on an isolated CI-only project."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

import pytest

from app.postgres_config import PG_IMAGE, PG_PREVIOUS_IMAGE, PG_SERVICE


def test_private_compose_service_initializes_with_mounted_secret_and_checksums(tmp_path):
    if not os.environ.get('CI') or shutil.which('docker') is None:
        pytest.skip('Requires the disposable Linux Docker CI runner')
    project = 'psychology-test-' + uuid.uuid4().hex
    assert project.startswith('psychology-test-')
    candidate_compose = Path('docker-compose.yml').read_text(encoding='utf-8')
    assert candidate_compose.count(PG_IMAGE) == 1
    (tmp_path / 'docker-compose.yml').write_text(
        candidate_compose.replace(PG_IMAGE, PG_PREVIOUS_IMAGE), encoding='utf-8')
    (tmp_path / '.env').write_text('BOT_TOKEN=synthetic\n', encoding='utf-8')
    state = tmp_path / '.postgres'
    state.mkdir(mode=0o700)
    data_root = state / 'data'
    data_root.mkdir(mode=0o700)
    password = state / 'admin.password'
    password.write_text('synthetic-compose-only\n', encoding='utf-8')
    password.chmod(0o400)
    base = ['docker','compose','--project-directory',str(tmp_path),'-f',str(tmp_path/'docker-compose.yml'),'-p',project]
    def command(args, **kwargs):
        result = subprocess.run(args, cwd=tmp_path, capture_output=True, timeout=120, **kwargs)
        assert result.returncode == 0, 'Isolated Compose test command failed: ' + result.stderr.decode(errors='replace')[-2000:]
        return result.stdout
    # Only this temporary file is mounted; the real VPS uses the same uid/mode.
    def path_owner(path, uid):
        command(['docker','run','--rm','--network','none','--mount',f'type=bind,source={path},target=/owned-path',
                 '--entrypoint','chown',PG_IMAGE,str(uid),'/owned-path'])
    started = False
    try:
        assert command(['docker','run','--rm','--network','none','--entrypoint','id',PG_IMAGE,'-u','postgres']).strip() == b'999'
        path_owner(password, 999)
        # Match the VPS allocation: private mount root owned by root, then the
        # actual operator helper makes it traversable by PostgreSQL uid 999.
        path_owner(data_root, '0:0')
        initial = data_root.stat()
        assert (initial.st_uid, initial.st_gid, initial.st_mode & 0o777) == (0, 0, 0o700)
        helper = ('from pathlib import Path; import sys; from scripts import postgres_vps as vps; '
                  'vps.STATE=Path(sys.argv[1]); vps.prepare_data_directory({"phase":"allocated"})')
        result = subprocess.run(['sudo','-n',sys.executable,'-c',helper,str(state)],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=20)
        assert result.returncode == 0, result.stderr.decode(errors='replace')
        prepared = data_root.stat()
        assert (prepared.st_uid, prepared.st_gid, prepared.st_mode & 0o777) == (999, 999, 0o700)
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
        assert item['Config']['Image'] == PG_PREVIOUS_IMAGE
        assert set(item['NetworkSettings']['Networks']) == {project + '_default'}
        data = [m for m in item['Mounts'] if m['Destination'] == '/var/lib/postgresql']
        assert len(data) == 1 and Path(data[0]['Source']) == state / 'data'
        wrapper = 'export PGPASSWORD="$(cat /run/secrets/postgres_admin_password)"; exec psql -X -qAt -U postgres -d postgres -v ON_ERROR_STOP=1'
        result = command(base + ['--profile','postgres','exec','-T',PG_SERVICE,'sh','-eu','-c',wrapper],
                         input=b'SHOW data_checksums; SHOW server_version; SHOW password_encryption;')
        assert result.decode().splitlines()[0] == 'on'
        assert result.decode().splitlines()[1].split()[0] == '18.6'
        assert result.decode().splitlines()[2] == 'scram-sha-256'
        command(base + ['--profile','postgres','exec','-T',PG_SERVICE,
                        'sh','-eu','-c',wrapper],
                input=b'CREATE ROLE psychology_app LOGIN;\n'
                      b'CREATE DATABASE psychology_atlas OWNER psychology_app;\n')
        before = command(base + ['--profile','postgres','exec','-T',PG_SERVICE,
                                  'sh','-eu','-c',wrapper],
                         input=(b'CREATE TABLE public.image_upgrade_probe (id integer PRIMARY KEY, value text NOT NULL); '
                                b"INSERT INTO public.image_upgrade_probe VALUES (1, 'preserved'); "
                                b'SELECT system_identifier FROM pg_control_system();'))
        cluster = before.decode().strip()
        assert cluster.isdigit()
        (tmp_path / 'docker-compose.yml').write_text(candidate_compose, encoding='utf-8')
        command(base + ['--profile','postgres','up','-d','--no-deps','--force-recreate',PG_SERVICE])
        container = command(base + ['--profile','postgres','ps','--all','--quiet',PG_SERVICE]).decode().strip()
        assert container and '\n' not in container
        for attempt in range(30):
            item = json.loads(command(['docker','inspect',container]))[0]
            if item['State'].get('Health',{}).get('Status') == 'healthy': break
            time.sleep(1)
        else: pytest.fail('Existing PostgreSQL cluster did not start on the candidate image')
        assert item['Config']['Image'] == PG_IMAGE
        preserved = command(base + ['--profile','postgres','exec','-T',PG_SERVICE,
                                    'sh','-eu','-c',wrapper],
                            input=(b'SELECT system_identifier FROM pg_control_system(); '
                                   b'SELECT id, value FROM public.image_upgrade_probe; '
                                   b'SHOW server_version;'))
        persisted = preserved.decode().splitlines()
        assert persisted[:2] == [cluster, '1|preserved']
        assert len(persisted) == 3 and persisted[2].split()[0] == '18.6'
        db_wrapper = wrapper.replace('-d postgres', '-d psychology_atlas')
        command(base + ['--profile','postgres','exec','-T',PG_SERVICE,
                        'sh','-eu','-c',db_wrapper],
                input=Path('sql/private-search-bootstrap.sql').read_bytes())
        vector = command(base + ['--profile','postgres','exec','-T',PG_SERVICE,
                                  'sh','-eu','-c',db_wrapper],
                         input=(b"SELECT e.extversion||'|'||n.nspname||'|'||pg_get_userbyid(n.nspowner) "
                                b"FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace "
                                b"WHERE e.extname='vector';"))
        assert vector.decode().strip() == '0.8.6|private_search|psychology_app'
    finally:
        if started:
            command(base + ['--profile','postgres','down'])
        path_owner(password, os.getuid())
        # PG owns only this disposable bind directory, not arbitrary host paths.
        command(['docker','run','--rm','--network','none','--mount',f'type=bind,source={state / "data"},target=/owned-data',
                 '--entrypoint','chown',PG_IMAGE,'-R',str(os.getuid()),'/owned-data'])
