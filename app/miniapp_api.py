from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import dataclass
from typing import Any

from app.db import create_or_load_user, finalize_quiz_session, get_connection
from app.miniapp_runner import build_miniapp_runner_state, submit_miniapp_answer_event

logger = logging.getLogger(__name__)


class InitDataValidationError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedInitData:
    telegram_user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    auth_date: int


def verify_telegram_init_data(init_data: str, bot_token: str, *, max_age_seconds: int = 3600) -> VerifiedInitData:
    if not init_data:
        raise InitDataValidationError("missing_init_data")
    pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    data = {k: v for k, v in pairs}
    recv_hash = data.pop("hash", "")
    if not recv_hash:
        raise InitDataValidationError("missing_hash")
    auth_date_raw = data.get("auth_date")
    if auth_date_raw is None or not auth_date_raw.isdigit():
        raise InitDataValidationError("invalid_auth_date")
    auth_date = int(auth_date_raw)
    now = int(time.time())
    if auth_date > now + 60 or now - auth_date > max_age_seconds:
        raise InitDataValidationError("expired_init_data")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, recv_hash):
        raise InitDataValidationError("invalid_hash")

    raw_user = data.get("user")
    if not raw_user:
        raise InitDataValidationError("missing_user")
    try:
        user = json.loads(raw_user)
    except json.JSONDecodeError as exc:
        raise InitDataValidationError("invalid_user_json") from exc

    telegram_user_id = user.get("id")
    if not isinstance(telegram_user_id, int) or telegram_user_id <= 0:
        raise InitDataValidationError("invalid_user_id")

    return VerifiedInitData(
        telegram_user_id=telegram_user_id,
        username=user.get("username") if isinstance(user.get("username"), str) else None,
        first_name=user.get("first_name") if isinstance(user.get("first_name"), str) else None,
        last_name=user.get("last_name") if isinstance(user.get("last_name"), str) else None,
        auth_date=auth_date,
    )


def _json(status: HTTPStatus, payload: dict[str, Any]) -> tuple[int, dict[str, str], bytes]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return status.value, {"Content-Type": "application/json; charset=utf-8"}, body


def _extract_init_data(headers) -> str:
    auth = headers.get("Authorization", "")
    if auth.startswith("tma "):
        return auth[4:].strip()
    return headers.get("X-Telegram-Init-Data", "").strip()


def build_state_response(
    db_path: str,
    bot_token: str,
    init_data: str,
    *,
    max_age_seconds: int = 3600,
) -> tuple[int, dict[str, str], bytes]:
    try:
        verified = verify_telegram_init_data(init_data, bot_token, max_age_seconds=max_age_seconds)
    except InitDataValidationError as exc:
        return _json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": str(exc)})

    with get_connection(db_path) as conn:
        user_row = create_or_load_user(
            conn,
            verified.telegram_user_id,
            verified.username,
            verified.first_name,
            verified.last_name,
        )
        state = build_miniapp_runner_state(conn, actor_user_id=int(user_row["id"]))
    return _json(HTTPStatus.OK, {"ok": True, "runner_state": state})


def build_answer_response(
    db_path: str,
    bot_token: str,
    init_data: str,
    body: bytes,
    *,
    max_age_seconds: int = 3600,
) -> tuple[int, dict[str, str], bytes]:
    try:
        verified = verify_telegram_init_data(init_data, bot_token, max_age_seconds=max_age_seconds)
    except InitDataValidationError as exc:
        return _json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": str(exc)})
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
    if not isinstance(payload, dict):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_payload"})
    req = (payload.get("session_id"), payload.get("question_id"), payload.get("selected_option_index"))
    if not all(type(v) is int for v in req):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_payload"})

    with get_connection(db_path) as conn:
        user_row = create_or_load_user(conn, verified.telegram_user_id, verified.username, verified.first_name, verified.last_name)
        submission = submit_miniapp_answer_event(
            conn,
            session_id=req[0],
            actor_user_id=int(user_row["id"]),
            question_id=req[1],
            selected_option_index=req[2],
        )
        if submission.status == "accepted":
            state = build_miniapp_runner_state(conn, actor_user_id=int(user_row["id"]), session_id=req[0])
            if state.get("state") == "in_progress" and state.get("status") == "no_current_question":
                finalized = finalize_quiz_session(conn, req[0])
                if finalized is not None:
                    state = build_miniapp_runner_state(conn, actor_user_id=int(user_row["id"]), session_id=req[0])
            return _json(HTTPStatus.OK, {"ok": True, "submission_status": submission.status, "runner_state": state})
        response_payload: dict[str, Any] = {"ok": True, "submission_status": submission.status}
        if submission.status in {"duplicate", "stale_question", "invalid_option", "session_not_found", "invalid_question"}:
            response_payload["runner_state"] = build_miniapp_runner_state(conn, actor_user_id=int(user_row["id"]))
        return _json(HTTPStatus.OK, response_payload)


class MiniAppApiHandler(BaseHTTPRequestHandler):
    db_path = ""
    bot_token = ""
    initdata_ttl_seconds = 3600
    allowed_origin: str | None = None

    def _set_common_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        request_origin = self.headers.get("Origin", "")
        if self.allowed_origin and request_origin == self.allowed_origin:
            self.send_header("Access-Control-Allow-Origin", self.allowed_origin)
            self.send_header("Vary", "Origin")

    def do_OPTIONS(self):
        if self.path.split("?")[0] not in {"/miniapp/state", "/miniapp/answer"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._set_common_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Telegram-Init-Data")
        self.end_headers()

    def do_GET(self):
        if self.path.split("?")[0] != "/miniapp/state":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        status, headers, body = build_state_response(
            self.db_path,
            self.bot_token,
            _extract_init_data(self.headers),
            max_age_seconds=self.initdata_ttl_seconds,
        )
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self._set_common_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.split("?")[0] != "/miniapp/answer":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        status, headers, data = build_answer_response(
            self.db_path,
            self.bot_token,
            _extract_init_data(self.headers),
            body,
            max_age_seconds=self.initdata_ttl_seconds,
        )
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self._set_common_headers()
        self.end_headers()
        self.wfile.write(data)


def start_miniapp_api_server(
    host: str,
    port: int,
    *,
    db_path: str,
    bot_token: str,
    initdata_ttl_seconds: int = 3600,
    allowed_origin: str | None = None,
) -> ThreadingHTTPServer:
    MiniAppApiHandler.db_path = db_path
    MiniAppApiHandler.bot_token = bot_token
    MiniAppApiHandler.initdata_ttl_seconds = initdata_ttl_seconds
    MiniAppApiHandler.allowed_origin = allowed_origin
    server = ThreadingHTTPServer((host, port), MiniAppApiHandler)
    return server
