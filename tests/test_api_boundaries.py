from contextlib import closing
import json
import logging
from pathlib import Path
import shutil
import sqlite3
import subprocess
from types import SimpleNamespace
import asyncio
import http.client
import threading

from fastapi.testclient import TestClient
import pytest

from app.handler_latency import HandlerLatency
from app.db import store_session_questions
from app.main import update_ingress_logger
from app.classic_quiz_handlers import _safe_classic_text_log_fields
from app.miniapp_api import MiniAppApiHandler, _sanitize_request_id, build_setup_response, verify_telegram_init_data, InitDataValidationError, start_miniapp_api_server
from app.miniapp_fastapi import create_app
from tests.test_miniapp_api import _make_init_data

TOKEN = "123:synthetic-secret-token"
USER_ID = 8642097531924


@pytest.fixture
def api(tmp_path):
    path = tmp_path / "quiz.sqlite3"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(Path("sql/schema.sql").read_text(encoding="utf-8"))
        conn.execute("INSERT INTO categories (slug, name) VALUES ('c', 'Category')")
        conn.execute("INSERT INTO questions (external_id, category_id, question_text) VALUES ('q', 1, 'Question')")
        conn.execute("INSERT INTO question_options (question_id, option_index, option_text, is_correct) VALUES (1, 0, 'A', 1), (1, 1, 'B', 0)")
        conn.execute("INSERT INTO users (telegram_user_id, first_name) VALUES (?, 'Original name')", (USER_ID,))
        conn.execute("INSERT INTO quiz_sessions (user_id, category_id) VALUES (1, 1)")
        store_session_questions(conn, 1, [1])
    signed = _make_init_data(TOKEN, {"id": USER_ID, "first_name": "Changed name"})
    client = TestClient(create_app(db_path=str(path), bot_token=TOKEN, allowed_origin="https://miniapp.example.com"))
    return path, client, signed


def dump(path):
    with closing(sqlite3.connect(path)) as conn:
        return list(conn.iterdump())


@pytest.mark.parametrize("field,value", [
    ("quiz_mode", []), ("quiz_mode", {}), ("quiz_mode", True), ("quiz_mode", "invalid"),
    ("difficulty", []), ("difficulty", {}), ("difficulty", False),
    ("question_count", []), ("question_count", {}), ("question_count", True), ("question_count", 5.0),
    ("category_ids", [True]), ("category_ids", [1.0]), ("category_ids", [2**64]),
    ("category_ids", [-1]), ("category_ids", [0]), ("category_ids", [999]), ("category_ids", []),
])
def test_invalid_setup_is_4xx_without_any_database_mutation(api, field, value):
    path, client, signed = api
    before = dump(path)
    payload = {"quiz_mode": "single", "question_count": 5, "difficulty": "any", "category_ids": [1], field: value}
    response = client.post("/miniapp/setup", headers={"Authorization": f"tma {signed}"}, json=payload)
    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_setup"}
    assert dump(path) == before
    # The legacy adapter calls this same builder; verify its structured response too.
    assert build_setup_response(str(path), TOKEN, signed, json.dumps(payload).encode())[0] == 400
    assert dump(path) == before


@pytest.mark.parametrize("mode", ["all", "selected_mix"])
def test_unavailable_category_rejected_in_every_mode(api, mode):
    path, client, signed = api
    before = dump(path)
    payload = {"quiz_mode": mode, "question_count": None, "difficulty": "any", "category_ids": [999]}
    assert client.post("/miniapp/setup", headers={"Authorization": f"tma {signed}"}, json=payload).status_code == 400
    assert dump(path) == before


@pytest.mark.parametrize("endpoint,payload", [
    ("/miniapp/glossary/start", {"topic_id": "general", "question_count": []}),
    ("/miniapp/glossary/start", {"topic_id": "general", "question_count": {}}),
    ("/miniapp/setup", {"mode": "glossary", "topic_id": "general", "question_count": {}}),
    ("/miniapp/answer", {"mode": "glossary", "session_id": "test", "action": []}),
    ("/miniapp/answer", {"mode": "glossary", "session_id": "test", "action": {}}),
    ("/miniapp/glossary/answer", {"session_id": "test", "selected_option_index": True}),
    ("/miniapp/answer", {"session_id": True, "question_id": 1, "selected_option_index": 0}),
    ("/miniapp/answer", {"session_id": 2**64, "question_id": 1, "selected_option_index": 0}),
    ("/miniapp/answer", {"session_id": 1, "question_id": -1, "selected_option_index": 0}),
    ("/miniapp/answer", {"session_id": 1, "question_id": 1, "selected_option_index": False}),
])
def test_invalid_payload_shapes_never_reach_state_changes(api, endpoint, payload):
    path, client, signed = api
    before = dump(path)
    response = client.post(endpoint, headers={"Authorization": f"tma {signed}"}, json=payload)
    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert dump(path) == before


@pytest.mark.parametrize("user", [[], None, True, {"id": True}, {"id": 2**64}])
def test_signed_but_malformed_user_is_controlled_auth_error(user):
    with pytest.raises(InitDataValidationError):
        verify_telegram_init_data(_make_init_data(TOKEN, user), TOKEN)


def test_logs_exclude_identifiers_auth_and_untrusted_correlation_data(api, caplog):
    _, client, signed = api
    caplog.set_level(logging.INFO)
    response = client.get("/miniapp/state", headers={"Authorization": f"tma {signed}", "X-Miniapp-Request-Id": signed})
    assert response.status_code == 200
    client.options("/miniapp/setup", headers={"Access-Control-Request-Headers": signed})
    tracker = HandlerLatency(handler="synthetic", telegram_user_id=USER_ID)
    tracker.start()
    tracker.summary()
    asyncio.run(update_ingress_logger(SimpleNamespace(update_id=123, effective_user=SimpleNamespace(id=USER_ID)), None))
    text = caplog.text + _safe_classic_text_log_fields(telegram_user_id=USER_ID)
    for sensitive in (str(USER_ID), signed, TOKEN, "telegram_user_id="):
        assert sensitive not in text
    assert "duration_ms=" in text
    assert "handler=synthetic" in text
    assert _sanitize_request_id("rq_abcd.retry-1") == "rq_abcd.retry-1"
    assert _sanitize_request_id("rq_ok\nforged=true") == ""
    # BaseHTTPRequestHandler otherwise writes raw URL/query to stderr.
    MiniAppApiHandler.log_message(None, "%s", f"GET /?initData={signed}")


@pytest.mark.parametrize("script", ["frontend_api_destination.cjs", "frontend_glossary_retries.cjs"])
def test_frontend_behavior_regressions(script):
    node = shutil.which("node")
    assert node, "Node.js is required for the dependency-free frontend security regression"
    subprocess.run([node, str(Path("tests") / script)], check=True, capture_output=True, text=True)


def test_legacy_http_logs_exclude_user_and_raw_query(api, caplog, capsys):
    path, _, signed = api
    caplog.set_level(logging.INFO)
    server = start_miniapp_api_server("127.0.0.1", 0, db_path=str(path), bot_token=TOKEN)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", "/miniapp/state?initData=synthetic-secret-query", headers={"Authorization": f"tma {signed}"})
        response = connection.getresponse()
        assert response.status == 200
        response.read()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    logged = caplog.text + capsys.readouterr().err
    for sensitive in (str(USER_ID), signed, TOKEN, "synthetic-secret-query", "telegram_user_id="):
        assert sensitive not in logged
    assert "miniapp_api endpoint=/miniapp/state" in logged
