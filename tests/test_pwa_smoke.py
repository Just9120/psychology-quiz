import io
import json
from urllib.error import URLError
from urllib.parse import urlsplit

import pytest

from scripts import pwa_smoke
from tests.test_pwa_release import make_artifact, FIRST


@pytest.mark.parametrize("failure", [None, "asset", "revision", "dirty", "mime", "cache", "csp", "disabled", "wrong-api", "redirect"])
def test_smoke_checks_every_public_byte_headers_and_actual_auth_route(tmp_path, monkeypatch, failure):
    artifact = make_artifact(tmp_path / "artifact")
    calls = []

    class Response(io.BytesIO):
        def __init__(self, body, status=200, headers=None):
            super().__init__(body)
            self.status = status
            self.headers = headers or {"Content-Type": "application/javascript", "Cache-Control": "no-store",
                                       "Content-Security-Policy": "frame-ancestors 'none'"}

    class Opener:
        def open(self, request, timeout):
            assert request.get_header("User-agent") == "PsychologyAtlas-Deployment-Check/1.0"
            path = urlsplit(request.full_url).path
            calls.append(path)
            if path == "/web/auth/me":
                body = b'{"ok":false,"error":"unauthorized"}'
                if failure == "wrong-api": body = b'{"ok":true}'
                return Response(body, 404 if failure == "disabled" else 401)
            body = (artifact / path[1:]).read_bytes()
            if path == "/build.json" and failure in {"revision", "dirty"}:
                data = json.loads(body)
                data["revision" if failure == "revision" else "dirty"] = "wrong" if failure == "revision" else True
                body = json.dumps(data).encode()
            if path == "/sw.js" and failure == "asset": body += b"modified"
            response = Response(body, 302 if failure == "redirect" else 200)
            if failure == "mime": response.headers["Content-Type"] = "text/html"
            if failure == "cache": response.headers.pop("Cache-Control")
            if failure == "csp": response.headers.pop("Content-Security-Policy")
            return response

    monkeypatch.setattr(pwa_smoke, "build_opener", lambda *args: Opener())
    if failure:
        with pytest.raises(ValueError):
            pwa_smoke.smoke("https://pwa.example.test", artifact, FIRST)
    else:
        pwa_smoke.smoke("https://pwa.example.test", artifact, FIRST)
        expected = set(json.loads((artifact / "build.json").read_text())["files"])
        assert set(calls) == {"/build.json", "/web/auth/me"} | {"/" + name for name in expected}
        assert len(calls) == len(expected) + 2


@pytest.mark.parametrize("origin", ["http://pwa.example.test", "https://user:secret@example.test", "https://example.test/?token=private"])
def test_smoke_rejects_unsafe_origin_without_network(tmp_path, monkeypatch, origin):
    artifact = make_artifact(tmp_path / "artifact")
    monkeypatch.setattr(pwa_smoke, "build_opener", lambda *args: pytest.fail("Unexpected network"))
    with pytest.raises(ValueError, match="HTTPS origin"):
        pwa_smoke.smoke(origin, artifact, FIRST)


@pytest.mark.parametrize("recover", [True, False])
def test_smoke_retries_only_bounded_transport_failures(tmp_path, monkeypatch, recover):
    artifact = make_artifact(tmp_path / "artifact")
    calls = []
    delays = []

    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Type": "application/javascript", "Cache-Control": "no-store",
                   "Content-Security-Policy": "frame-ancestors 'none'"}

    class Opener:
        def open(self, request, timeout):
            path = urlsplit(request.full_url).path
            calls.append(path)
            if path == "/build.json" and (not recover or calls.count(path) == 1):
                raise URLError(ConnectionResetError(104, "Connection reset by peer"))
            if path == "/web/auth/me":
                response = Response(b'{"ok":false,"error":"unauthorized"}')
                response.status = 401
                return response
            return Response((artifact / path[1:]).read_bytes())

    monkeypatch.setattr(pwa_smoke, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(pwa_smoke.time, "sleep", delays.append)
    if recover:
        pwa_smoke.smoke("https://pwa.example.test", artifact, FIRST)
        assert calls.count("/build.json") == 2
        assert delays == [1]
    else:
        with pytest.raises(URLError):
            pwa_smoke.smoke("https://pwa.example.test", artifact, FIRST)
        assert calls == ["/build.json"] * 3
        assert delays == [1, 2]


def test_smoke_does_not_retry_certificate_error(tmp_path, monkeypatch):
    artifact = make_artifact(tmp_path / "artifact")
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            raise URLError("certificate verify failed")

    monkeypatch.setattr(pwa_smoke, "build_opener", lambda *args: Opener())
    with pytest.raises(URLError):
        pwa_smoke.smoke("https://pwa.example.test", artifact, FIRST)
    assert calls == ["https://pwa.example.test/build.json"]
