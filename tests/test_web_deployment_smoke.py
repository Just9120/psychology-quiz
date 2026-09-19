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
        code = status if '/web/' in url else 401
        raise urllib.error.HTTPError(url,code,'',{},BytesIO(b'{"error":"unauthorized"}'))
    monkeypatch.setattr(deployment_http_smoke.urllib.request,'urlopen',response)
    deployment_http_smoke.main()
    assert calls[-1].endswith('/web/auth/me')


def test_http_smoke_rejects_accidentally_open_web_gate(monkeypatch):
    monkeypatch.setenv('APP_REVISION','synthetic-sha')
    monkeypatch.setenv('PWA_ENABLED','false')
    def response(url, timeout):
        if url.endswith('/miniapp/state'):
            raise urllib.error.HTTPError(url,401,'',{},BytesIO(b'{"error":"unauthorized"}'))
        return BytesIO(json.dumps({'ok':True,'revision':'synthetic-sha'}).encode())
    monkeypatch.setattr(deployment_http_smoke.urllib.request,'urlopen',response)
    with pytest.raises(RuntimeError,match='Unauthenticated PWA'):
        deployment_http_smoke.main()
