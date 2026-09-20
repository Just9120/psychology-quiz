from io import BytesIO
import json
import urllib.error

import pytest

from scripts import deployment_http_smoke


@pytest.mark.parametrize('enabled,status', [('false',404),('true',401)])
def test_http_smoke_requires_correct_web_auth_gate(monkeypatch, enabled, status):
    monkeypatch.setenv('APP_REVISION','synthetic-sha')
    monkeypatch.setenv('PWA_ENABLED',enabled)
    calls = []
    def response(url, timeout):
        calls.append(url)
        if url.endswith('/healthz'):
            return BytesIO(json.dumps({'ok':True,'revision':'synthetic-sha'}).encode())
        if url.endswith('/readyz'):
            return BytesIO(json.dumps({'ok':True,'revision':'synthetic-sha','database_backend':'sqlite','database_version':'3.test'}).encode())
        code = status if '/web/' in url else 401
        raise urllib.error.HTTPError(url,code,'',{},BytesIO(b'{"error":"unauthorized"}'))
    monkeypatch.setattr(deployment_http_smoke.urllib.request,'urlopen',response)
    deployment_http_smoke.main(require_pwa=enabled == 'true')
    assert calls[-1].endswith('/web/auth/me')


def test_static_delivery_cannot_accept_disabled_web_runtime(monkeypatch):
    monkeypatch.setenv('PWA_ENABLED', 'false')
    monkeypatch.setattr(deployment_http_smoke.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('No network before config gate'))
    with pytest.raises(RuntimeError, match='Enabled PWA required'):
        deployment_http_smoke.main(require_pwa=True)


def test_http_smoke_rejects_accidentally_open_web_gate(monkeypatch):
    monkeypatch.setenv('APP_REVISION','synthetic-sha')
    monkeypatch.setenv('PWA_ENABLED','false')
    def response(url, timeout):
        if url.endswith('/miniapp/state'):
            raise urllib.error.HTTPError(url,401,'',{},BytesIO(b'{"error":"unauthorized"}'))
        return BytesIO(json.dumps({'ok':True,'revision':'synthetic-sha','database_backend':'sqlite','database_version':'3.test'}).encode())
    monkeypatch.setattr(deployment_http_smoke.urllib.request,'urlopen',response)
    with pytest.raises(RuntimeError,match='Unauthenticated PWA'):
        deployment_http_smoke.main()


@pytest.mark.parametrize('field,value', [('revision','old'),('database_backend','postgresql'),('ok',False),('database_version','')])
def test_readiness_failure_cannot_pass_health_only(monkeypatch, field, value):
    monkeypatch.setenv('APP_REVISION','synthetic-sha')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setattr(deployment_http_smoke.time, 'sleep', lambda _: None)
    def response(url, timeout):
        payload = {'ok':True,'revision':'synthetic-sha','database_backend':'sqlite','database_version':'3.test'}
        if url.endswith('/readyz'): payload[field] = value
        return BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(deployment_http_smoke.urllib.request,'urlopen',response)
    with pytest.raises(RuntimeError, match='readiness'):
        deployment_http_smoke.main()
