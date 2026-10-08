import pytest
from fastapi.testclient import TestClient
from app.miniapp_fastapi import create_app
from app.miniapp_origins import parse_allowed_origins
from app.miniapp_api import MiniAppApiHandler
from scripts.miniapp_domain_config import OLD, NEW, apply, restore, migrated_url
from types import SimpleNamespace


@pytest.mark.parametrize('origin,allowed', [(OLD, True), (NEW, True),
    ('https://miniapp.psy.cloud-nodes.net.evil.example', False), ('null', False),
    ('https://untrusted.example', False), ('', False)])
def test_transition_allows_exact_origins_without_authorizing_requests(tmp_path, origin, allowed):
    client = TestClient(create_app(db_path=str(tmp_path / 'db.sqlite3'), bot_token='123:test',
                                  allowed_origin=OLD + ',' + NEW))
    response = client.options('/miniapp/state', headers={'Origin': origin})
    assert response.status_code == 204
    assert response.headers.get('Access-Control-Allow-Origin') == (origin if allowed else None)
    response = client.get('/miniapp/state', headers={'Origin': origin})
    assert response.status_code == 401
    assert response.headers.get('Access-Control-Allow-Origin') == (origin if allowed else None)
    headers = {}
    handler = SimpleNamespace(headers={'Origin': origin}, allowed_origin=OLD + ',' + NEW,
                              send_header=lambda key, value: headers.__setitem__(key, value))
    MiniAppApiHandler._set_common_headers(handler)
    assert headers.get('Access-Control-Allow-Origin') == (origin if allowed else None)


@pytest.mark.parametrize('value', ['*', NEW+'/', NEW+'/path', 'https://user:secret@example.com',
    NEW+',', NEW+'?query', 'https://example.com:invalid', 'null'])
def test_invalid_origin_configuration_fails_closed(value):
    with pytest.raises(ValueError):
        parse_allowed_origins(value)


def test_config_cutover_preserves_other_settings_and_supports_checked_restore(tmp_path):
    path, backup = tmp_path / '.env', tmp_path / 'backup'
    original = ('# owner configuration\r\nSECRET=keep-private\r\nMINI_APP_URL='+OLD+
                '\r\nPWA_ENABLED=true\r\nMINIAPP_API_ALLOWED_ORIGIN='+OLD+'\r\n').encode()
    path.write_bytes(original)
    apply(path, backup)
    updated = path.read_bytes()
    assert b'SECRET=keep-private\r\n' in updated
    assert b'PWA_ENABLED=true\r\n' in updated
    assert ('MINI_APP_URL='+NEW+'\n').encode() in updated
    assert ('MINIAPP_API_ALLOWED_ORIGIN='+OLD+','+NEW+'\n').encode() in updated
    assert backup.read_bytes() == original
    restore(path, backup)
    assert path.read_bytes() == original


def test_config_restore_does_not_overwrite_later_owner_change(tmp_path):
    path, backup = tmp_path / '.env', tmp_path / 'backup'
    path.write_text('MINI_APP_URL='+OLD+'\nMINIAPP_API_ALLOWED_ORIGIN='+OLD+'\n')
    apply(path, backup)
    path.write_bytes(path.read_bytes() + b'OWNER_CHANGE=preserve\n')
    with pytest.raises(ValueError, match='changed after cutover'):
        restore(path, backup)
    assert b'OWNER_CHANGE=preserve' in path.read_bytes()


@pytest.mark.parametrize('config', [
    'MINI_APP_URL=https://different.example\nMINIAPP_API_ALLOWED_ORIGIN='+OLD+'\n',
    'MINI_APP_URL='+OLD+'\nMINIAPP_API_ALLOWED_ORIGIN=*\n',
    'MINI_APP_URL='+OLD+'\nMINI_APP_URL='+NEW+'\nMINIAPP_API_ALLOWED_ORIGIN='+OLD+'\n'])
def test_unknown_or_duplicate_runtime_config_is_preserved(tmp_path, config):
    path = tmp_path / '.env'; path.write_text(config)
    with pytest.raises(ValueError):
        apply(path, tmp_path / 'backup')
    assert path.read_text() == config

def test_cutover_shell_syntax_on_linux_delivery_platform():
    import subprocess
    import sys
    if sys.platform != 'linux':
        pytest.skip('Linux Bash delivery check runs in required CI')
    result = subprocess.run(['bash', '-n', 'scripts/miniapp_domain_cutover.sh'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_host_config_helper_needs_only_python_standard_library():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-I', '-S', 'scripts/miniapp_domain_config.py', '--help'],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_quoted_runtime_values_and_comments_are_supported(tmp_path):
    path, backup = tmp_path / '.env', tmp_path / 'backup'
    path.write_text('export MINI_APP_URL="'+OLD+'" # owner choice\nMINIAPP_API_ALLOWED_ORIGIN=\''+OLD+'\'\n')
    apply(path, backup)
    assert ('MINI_APP_URL='+NEW+'\n') in path.read_text()


@pytest.mark.parametrize('suffix', ['/', '/?api=https%3A%2F%2Fquiz-api.librechat.online&v=2',
                                  '?debug=1&context=sample%2Bvalue%26x',
                                  '/?context=first&context=second&blank='])
def test_cutover_keeps_existing_entrypoint_path_and_query(tmp_path, suffix):
    path, backup = tmp_path / '.env', tmp_path / 'backup'
    original = ('MINI_APP_URL="'+OLD+suffix+'"\nOTHER=unchanged\n'
                'MINIAPP_API_ALLOWED_ORIGIN='+OLD+'\n').encode()
    path.write_bytes(original)
    apply(path, backup)
    assert ('MINI_APP_URL='+NEW+suffix+'\n').encode() in path.read_bytes()
    assert b'OTHER=unchanged\n' in path.read_bytes()
    assert migrated_url(NEW+suffix) == NEW+suffix
    restore(path, backup)
    assert path.read_bytes() == original


@pytest.mark.parametrize('url', [OLD+'/other?api=example', OLD+'.evil.example/?v=1',
                               OLD+'/#fragment', OLD+':443/?v=1',
                               'http://miniapp.librechat.online/?v=1',
                               'https://user:password@miniapp.librechat.online/?v=1',
                               OLD+'/\t?v=1'])
def test_entrypoint_migration_still_rejects_unknown_or_unsafe_urls(tmp_path, url):
    path = tmp_path / '.env'
    original = ('MINI_APP_URL="'+url+'"\nMINIAPP_API_ALLOWED_ORIGIN='+OLD+'\n').encode()
    path.write_bytes(original)
    backup = tmp_path / 'backup'
    with pytest.raises(ValueError):
        apply(path, backup)
    assert path.read_bytes() == original
    assert not backup.exists()
