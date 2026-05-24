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
from app.db import (
    abandon_in_progress_sessions_for_user,
    get_active_categories,
    select_random_approved_question_ids_across_active_categories,
    select_random_approved_question_ids_by_categories,
    select_random_approved_question_ids_by_category,
    set_selected_categories_for_session,
    start_quiz_session,
    store_session_questions,
)
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
            feedback = {
                "selected_option_index": submission.selected_option_index,
                "is_correct": bool(submission.is_correct),
                "correct_option_index": _find_correct_option_index(conn, req[1]),
                "explanation": _get_question_explanation(conn, req[1]),
            }
            feedback["selected_option_text"] = _get_option_text(conn, req[1], submission.selected_option_index)
            feedback["correct_option_text"] = _get_option_text(conn, req[1], feedback["correct_option_index"])
            return _json(HTTPStatus.OK, {"ok": True, "submission_status": submission.status, "feedback": feedback, "runner_state": state})
        response_payload: dict[str, Any] = {"ok": True, "submission_status": submission.status}
        if submission.status in {"duplicate", "stale_question", "invalid_option", "session_not_found", "invalid_question"}:
            response_payload["runner_state"] = build_miniapp_runner_state(conn, actor_user_id=int(user_row["id"]))
        return _json(HTTPStatus.OK, response_payload)


def _find_correct_option_index(conn, question_id: int) -> int | None:
    row = conn.execute(
        "SELECT option_index FROM question_options WHERE question_id = ? AND is_correct = 1 LIMIT 1",
        (question_id,),
    ).fetchone()
    return int(row["option_index"]) if row is not None else None


def _get_question_explanation(conn, question_id: int) -> str | None:
    row = conn.execute("SELECT explanation FROM questions WHERE id = ? LIMIT 1", (question_id,)).fetchone()
    if row is None:
        return None
    value = row["explanation"]
    return str(value) if isinstance(value, str) else None


def _get_option_text(conn, question_id: int, option_index: int | None) -> str | None:
    if not isinstance(option_index, int):
        return None
    row = conn.execute(
        "SELECT option_text FROM question_options WHERE question_id = ? AND option_index = ? LIMIT 1",
        (question_id, option_index),
    ).fetchone()
    if row is None:
        return None
    value = row["option_text"]
    return str(value) if isinstance(value, str) else None


def build_setup_response(db_path: str, bot_token: str, init_data: str, body: bytes, *, max_age_seconds: int = 3600):
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

    quiz_mode = payload.get("quiz_mode")
    question_count = payload.get("question_count")
    difficulty = payload.get("difficulty")
    category_ids = payload.get("category_ids")
    if (
        quiz_mode not in {"single", "selected_mix", "all"}
        or question_count not in {5, 10, 15, None}
        or difficulty not in {"any", "easy", "medium", "hard"}
        or not isinstance(category_ids, list)
        or any(not isinstance(item, int) for item in category_ids)
    ):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_setup"})

    with get_connection(db_path) as conn:
        user_row = create_or_load_user(conn, verified.telegram_user_id, verified.username, verified.first_name, verified.last_name)
        active_categories = get_active_categories(conn)
        active_ids = {int(row["id"]) for row in active_categories}
        if not active_ids:
            return _json(HTTPStatus.CONFLICT, {"ok": False, "error": "no_categories"})
        difficulty_filter = None if difficulty == "any" else difficulty
        if quiz_mode == "single":
            if len(category_ids) != 1 or int(category_ids[0]) not in active_ids:
                return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_setup"})
            session_category_id = int(category_ids[0])
            selected_ids = None
            question_ids = select_random_approved_question_ids_by_category(conn, session_category_id, question_count, difficulty_filter)
        elif quiz_mode == "selected_mix":
            if not category_ids or any(int(cid) not in active_ids for cid in category_ids):
                return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_setup"})
            session_category_id = None
            selected_ids = [int(cid) for cid in category_ids]
            question_ids = select_random_approved_question_ids_by_categories(conn, selected_ids, question_count, difficulty_filter)
        else:
            session_category_id = None
            selected_ids = None
            question_ids = select_random_approved_question_ids_across_active_categories(conn, question_count, difficulty_filter)
        if not question_ids:
            return _json(HTTPStatus.CONFLICT, {"ok": False, "error": "no_questions"})
        abandon_in_progress_sessions_for_user(conn, int(user_row["id"]))
        session_id = start_quiz_session(conn, int(user_row["id"]), session_category_id, difficulty_mode=difficulty_filter)
        if selected_ids:
            set_selected_categories_for_session(conn, session_id, selected_ids)
        store_session_questions(conn, session_id, question_ids)
        state = build_miniapp_runner_state(conn, actor_user_id=int(user_row["id"]), session_id=session_id)
    return _json(HTTPStatus.OK, {"ok": True, "runner_state": state})


def build_setup_options_response(
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
        create_or_load_user(conn, verified.telegram_user_id, verified.username, verified.first_name, verified.last_name)
        categories = [{"id": int(row["id"]), "name": str(row["name"])} for row in get_active_categories(conn)]
    return _json(
        HTTPStatus.OK,
        {
            "ok": True,
            "setup_options": {
                "categories": categories,
                "question_count_choices": [5, 10, 15, "all"],
                "difficulty_choices": ["any", "easy", "medium", "hard"],
            },
        },
    )


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
        if self.path.split("?")[0] not in {"/miniapp/state", "/miniapp/setup-options", "/miniapp/answer", "/miniapp/setup"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._set_common_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Telegram-Init-Data")
        self.end_headers()

    def do_GET(self):
        endpoint = self.path.split("?")[0]
        if endpoint not in {"/miniapp/state", "/miniapp/setup-options"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if endpoint == "/miniapp/state":
            status, headers, body = build_state_response(
                self.db_path,
                self.bot_token,
                _extract_init_data(self.headers),
                max_age_seconds=self.initdata_ttl_seconds,
            )
        else:
            status, headers, body = build_setup_options_response(
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
        endpoint = self.path.split("?")[0]
        if endpoint not in {"/miniapp/answer", "/miniapp/setup"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if endpoint == "/miniapp/answer":
            status, headers, data = build_answer_response(
                self.db_path,
                self.bot_token,
                _extract_init_data(self.headers),
                body,
                max_age_seconds=self.initdata_ttl_seconds,
            )
        else:
            status, headers, data = build_setup_response(
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
