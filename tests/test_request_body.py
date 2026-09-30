import asyncio
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.miniapp_fastapi import create_app
from app.request_body import MAX_REQUEST_BODY_BYTES, RequestBodyTooLarge, read_request_body


def test_stream_limit_rejects_without_consuming_remainder():
    consumed = []

    async def stream():
        consumed.append(1)
        yield b"x" * MAX_REQUEST_BODY_BYTES
        consumed.append(2)
        yield b"y"
        consumed.append(3)
        raise AssertionError("oversize body remainder must not be consumed")

    with pytest.raises(RequestBodyTooLarge):
        asyncio.run(read_request_body(stream()))
    assert consumed == [1, 2]


@pytest.mark.parametrize("path", ["/miniapp/setup", "/miniapp/answer", "/miniapp/glossary/start",
                                  "/miniapp/literature/progress", "/miniapp/homework/start",
                                  "/miniapp/learning/goal-set"])
def test_oversize_miniapp_request_never_dispatches(path, caplog):
    app = create_app(db_path=":memory:", bot_token="synthetic", allowed_origin="https://mini.example")
    private = "private-input-marker"
    with patch("app.miniapp_fastapi._run_builder_in_thread") as dispatch, TestClient(app) as client:
        response = client.post(path, content=private + "x" * MAX_REQUEST_BODY_BYTES,
                               headers={"Origin": "https://mini.example", "Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json() == {"ok": False, "error": "body_too_large"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "https://mini.example"
    dispatch.assert_not_called()
    assert private not in caplog.text


def test_exact_wire_limit_remains_accepted_for_header_and_simple_body_transport():
    app = create_app(db_path=":memory:", bot_token="synthetic")
    async def builder(*args, **kwargs):
        assert len(args[4]) <= MAX_REQUEST_BODY_BYTES
        return 200, {"Content-Type": "application/json"}, b'{"ok":true}'
    payloads = [('{"padding":"' + "x" * (MAX_REQUEST_BODY_BYTES - 14) + '"}', {"Authorization": "tma proof"}),
                ('{"init_data":"proof","payload":{}}' + " " * (MAX_REQUEST_BODY_BYTES - 34), {})]
    with patch("app.miniapp_fastapi._run_builder_in_thread", side_effect=builder), TestClient(app) as client:
        for payload, headers in payloads:
            assert len(payload.encode()) == MAX_REQUEST_BODY_BYTES
            response = client.post("/miniapp/setup", content=payload, headers=headers)
            assert response.status_code == 200


@pytest.mark.parametrize("headers,expected", [
    ([("Content-Length", "16385")], 413),
    ([("Content-Length", "-1")], 400),
    ([("Content-Length", "invalid")], 400),
    ([("Content-Length", "1"), ("Content-Length", "2")], 400),
    ([("Transfer-Encoding", "chunked")], 400),
])
def test_legacy_transport_rejects_body_framing_before_waiting_or_dispatching(headers, expected):
    import http.client
    import threading
    from app.miniapp_api import start_miniapp_api_server

    server = start_miniapp_api_server("127.0.0.1", 0, db_path=":memory:", bot_token="synthetic")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
    try:
        with patch("app.miniapp_api.build_setup_response") as dispatch:
            connection.putrequest("POST", "/miniapp/setup")
            for name, value in headers:
                connection.putheader(name, value)
            connection.endheaders()  # No body: reading an unvalidated length would hang.
            response = connection.getresponse()
            assert response.status == expected
            assert response.headers["connection"] == "close"
            assert response.headers["cache-control"] == "no-store"
            assert json.loads(response.read())["ok"] is False
            dispatch.assert_not_called()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
