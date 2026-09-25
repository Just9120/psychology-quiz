from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from app.database import OperationalError, OPERATIONAL_ERRORS
import time
import urllib.parse
from datetime import datetime, timezone
from contextlib import closing
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import dataclass
from functools import wraps
from app.literature_service import (
    load_progress as _load_literature_progress_by_user, load_item_states as _load_literature_item_states_by_user,
    validate_progress as _validate_literature_progress_payload, save_progress as _upsert_literature_progress,
)
from app import glossary_service, progress_service, repetition, learning_goals, achievements
from app.mastery import overview as mastery_overview
from app.miniapp_glossary import run as run_glossary
from typing import Any
from app.payload_validation import is_sqlite_integer, valid_quiz_setup

from app.db import create_or_load_user, get_connection
from app.quiz_service import (
    QuizSetupError, prepare_quiz, start_prepared_quiz, quiz_setup_options, quiz_state, answer_quiz,
)
from app.literature import (
    list_literature_topic_payloads,
    load_literature_items,
)
from app.miniapp_glossary import (
    answer_glossary_session,
    list_glossary_topics_payload,
    next_glossary_session,
    restart_glossary_session,
    start_glossary_session,
)

logger = logging.getLogger(__name__)

LEARNING_READ_ACTIONS = {"overview", "review", "mastery", "goals", "achievements"}
LEARNING_WRITE_ACTIONS = {"goal-set", "review-start", "review-glossary-start"}


def build_learning_response(db_path: str, bot_token: str, action: str,
                            owner_email: str | None, init_data: str, body: bytes = b"",
                            *, max_age_seconds: int = 3600):
    """New learning routes remain owner-only until student launch is authorized.

    Telegram initData proves the external identity; the existing confirmed web
    link proves that it is the enabled owner. No unknown Telegram user is created.
    """
    if action not in LEARNING_READ_ACTIONS | LEARNING_WRITE_ACTIONS:
        return _json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
    verified = _verified_user_or_error(bot_token, init_data, max_age_seconds)
    if not isinstance(verified, VerifiedInitData):
        return verified
    payload = _parse_json_payload(body) if action in LEARNING_WRITE_ACTIONS else {}
    if payload is None:
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
    try:
        with closing(get_connection(db_path)) as conn, conn:
            if not owner_email:
                return _json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "student_access_disabled"})
            row = conn.execute("""SELECT u.id FROM users u JOIN web_accounts a ON a.user_id=u.id
                WHERE u.telegram_user_id=? AND a.email=? AND a.enabled=1""",
                (verified.telegram_user_id, owner_email)).fetchone()
            if row is None:
                return _json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "student_access_disabled"})
            actor = int(row[0])
            if action == "overview":
                result = progress_service.overview(conn, actor)
            elif action == "review":
                result = repetition.queue(conn, actor)
            elif action == "mastery":
                result = mastery_overview(conn, actor)
            elif action == "goals":
                result = learning_goals.overview(conn, actor)
            elif action == "achievements":
                result = achievements.refresh(conn, actor)
            elif action == "goal-set":
                result = learning_goals.set_target(conn, actor, payload)
            elif action == "review-start":
                result = progress_service.review_today(conn, actor, payload)
            else:
                result = progress_service.review_glossary_today(conn, actor, payload)
        return _json(HTTPStatus.OK, result)
    except (progress_service.ProgressError, glossary_service.GlossaryError) as error:
        return _json(HTTPStatus(error.status), {"ok": False, "error": error.code})
    except learning_goals.GoalError as error:
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": error.code})
    except OPERATIONAL_ERRORS as error:
        if _is_sqlite_locked_error(error):
            return _database_busy_response()
        raise


def _log_locked_db(endpoint: str, started_at: float) -> None:
    logger.warning(
        "miniapp_db_locked endpoint=%s duration_ms=%s",
        endpoint,
        int((time.time() - started_at) * 1000),
    )


def _read_request_id(headers) -> str:
    return _sanitize_request_id(headers.get("X-Miniapp-Request-Id", ""))


def _sanitize_request_id(raw: str) -> str:
    # Only a bounded correlation token, never arbitrary header/body contents.
    return raw if isinstance(raw, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", raw) else ""


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
    try:
        pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise InitDataValidationError("invalid_hash") from exc
    data = {k: v for k, v in pairs}
    recv_hash = data.pop("hash", "")
    if not recv_hash:
        raise InitDataValidationError("missing_hash")
    auth_date_raw = data.get("auth_date")
    if auth_date_raw is None or not auth_date_raw.isdigit():
        raise InitDataValidationError("invalid_auth_date")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise InitDataValidationError("invalid_auth_date") from exc
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

    if not isinstance(user, dict):
        raise InitDataValidationError("invalid_user_json")
    telegram_user_id = user.get("id")
    if not is_sqlite_integer(telegram_user_id, minimum=1):
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
    return status.value, {"Content-Type": "application/json; charset=utf-8", "Content-Length": str(len(body))}, body


def _database_busy_response() -> tuple[int, dict[str, str], bytes]:
    status, headers, body = _json(HTTPStatus.SERVICE_UNAVAILABLE, {"ok": False, "error": "database_busy_retry"})
    headers["Retry-After"] = "1"
    return status, headers, body


def _is_sqlite_locked_error(exc: Exception) -> bool:
    if isinstance(exc, OperationalError):
        return exc.sqlstate in {"55P03", "40P01", "40001"}
    message = str(exc).lower()
    return (
        "database is locked" in message
        or "database table is locked" in message
        or "database schema is locked" in message
        or "table is locked" in message
        or "schema is locked" in message
    )


def _extract_init_data(headers) -> str:
    auth = headers.get("Authorization", "")
    if auth.startswith("tma "):
        return auth[4:].strip()
    return headers.get("X-Telegram-Init-Data", "").strip()


def _extract_transport_payload(headers, body: bytes) -> tuple[str, bytes, str, str]:
    header_init_data = _extract_init_data(headers)
    if header_init_data:
        return header_init_data, body, _read_request_id(headers), "header_auth"
    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        return "", body, _read_request_id(headers), "simple_body"
    if not isinstance(parsed, dict):
        return "", body, _read_request_id(headers), "simple_body"
    init_data = parsed.get("init_data")
    request_id = _sanitize_request_id(str(parsed.get("request_id", "")))
    payload = parsed.get("payload")
    if isinstance(init_data, str) and isinstance(payload, dict):
        payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return init_data, payload_bytes, request_id or _read_request_id(headers), "simple_body"
    return "", body, request_id or _read_request_id(headers), "simple_body"





def _verified_user_or_error(bot_token: str, init_data: str, max_age_seconds: int) -> VerifiedInitData | tuple[int, dict[str, str], bytes]:
    try:
        return verify_telegram_init_data(init_data, bot_token, max_age_seconds=max_age_seconds)
    except InitDataValidationError as exc:
        return _json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": str(exc)})

def build_glossary_topics_response(bot_token: str, init_data: str, *, max_age_seconds: int = 3600):
    verified = _verified_user_or_error(bot_token, init_data, max_age_seconds)
    if not isinstance(verified, VerifiedInitData):
        return verified
    return _json(HTTPStatus.OK, {"ok": True, "modes": [{"mode": "topics", "title": "Тесты по темам"}, {"mode": "glossary", "title": "Глоссарий"}], "glossary": list_glossary_topics_payload()})

def _parse_json_payload(body: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None

def _normalize_glossary_question_count(value: Any) -> int | str | None:
    if value is None or value == "all":
        return value
    if type(value) is int and value in {5, 10}:
        return value
    if value == "5":
        return 5
    if value == "10":
        return 10
    raise ValueError("invalid_glossary_setup")


def _glossary_errors(builder):
    @wraps(builder)
    def wrapped(*args, **kwargs):
        try:
            return builder(*args, **kwargs)
        except glossary_service.GlossaryError as error:
            return _json(HTTPStatus(error.status), {"ok": False, "error": error.code})
        except OPERATIONAL_ERRORS:
            return _database_busy_response()
    return wrapped


@_glossary_errors
def build_glossary_start_response(db_path: str, bot_token: str, init_data: str, body: bytes, *, max_age_seconds: int = 3600):
    verified = _verified_user_or_error(bot_token, init_data, max_age_seconds)
    if not isinstance(verified, VerifiedInitData):
        return verified
    payload = _parse_json_payload(body)
    if payload is None:
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
    topic_id = payload.get("topic_id")
    try:
        count = _normalize_glossary_question_count(payload.get("question_count"))
    except ValueError:
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_glossary_setup"})
    if not isinstance(topic_id, str):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_glossary_setup"})
    state = start_glossary_session(verified.telegram_user_id, topic_id, count, db_path=db_path,
        expected_session_id=payload.get("expected_session_id"), replace_active=payload.get("replace_active"))
    if state is None:
        return _json(HTTPStatus.CONFLICT, {"ok": False, "error": "glossary_unavailable"})
    return _json(HTTPStatus.OK, {"ok": True, "glossary_state": state})

@_glossary_errors
def build_glossary_answer_response(db_path: str, bot_token: str, init_data: str, body: bytes, *, max_age_seconds: int = 3600):
    verified = _verified_user_or_error(bot_token, init_data, max_age_seconds)
    if not isinstance(verified, VerifiedInitData):
        return verified
    payload = _parse_json_payload(body)
    if payload is None:
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
    session_id = payload.get("session_id")
    selected = payload.get("selected_option_index")
    if not isinstance(session_id, str) or not is_sqlite_integer(selected):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_glossary_answer"})
    step_id = payload.get("step_id")
    if not is_sqlite_integer(step_id, minimum=1):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "glossary_step_required"})
    state = answer_glossary_session(verified.telegram_user_id, session_id, selected, step_id, db_path=db_path)
    if state is None:
        return _json(HTTPStatus.CONFLICT, {"ok": False, "error": "invalid_glossary_answer"})
    return _json(HTTPStatus.OK, {"ok": True, "glossary_state": state})

@_glossary_errors
def build_glossary_next_response(db_path: str, bot_token: str, init_data: str, body: bytes, *, max_age_seconds: int = 3600):
    verified = _verified_user_or_error(bot_token, init_data, max_age_seconds)
    if not isinstance(verified, VerifiedInitData):
        return verified
    payload = _parse_json_payload(body)
    if payload is None:
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
    session_id = payload.get("session_id")
    if not isinstance(session_id, str):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_glossary_session"})
    step_id = payload.get("step_id")
    if not is_sqlite_integer(step_id, minimum=1):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "glossary_step_required"})
    state = next_glossary_session(verified.telegram_user_id, session_id, step_id, db_path=db_path)
    if state is None:
        return _json(HTTPStatus.CONFLICT, {"ok": False, "error": "invalid_glossary_session"})
    return _json(HTTPStatus.OK, {"ok": True, "glossary_state": state})

@_glossary_errors
def build_glossary_restart_response(db_path: str, bot_token: str, init_data: str, body: bytes, *, max_age_seconds: int = 3600):
    verified = _verified_user_or_error(bot_token, init_data, max_age_seconds)
    if not isinstance(verified, VerifiedInitData):
        return verified
    payload = _parse_json_payload(body)
    if payload is None:
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
    session_id = payload.get("session_id")
    if not isinstance(session_id, str):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_glossary_session"})
    state = restart_glossary_session(verified.telegram_user_id, session_id, db_path=db_path)
    if state is None:
        return _json(HTTPStatus.CONFLICT, {"ok": False, "error": "invalid_glossary_session"})
    return _json(HTTPStatus.OK, {"ok": True, "glossary_state": state})




def build_literature_topics_response(
    db_path: str,
    bot_token: str,
    init_data: str,
    *,
    max_age_seconds: int = 3600,
) -> tuple[int, dict[str, str], bytes]:
    started_at = time.time()
    try:
        verified = verify_telegram_init_data(init_data, bot_token, max_age_seconds=max_age_seconds)
    except InitDataValidationError as exc:
        return _json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": str(exc)})
    try:
        with closing(get_connection(db_path)) as conn:
            with conn:
                user_row = create_or_load_user(conn, verified.telegram_user_id, verified.username, verified.first_name, verified.last_name)
                user_states = _load_literature_progress_by_user(conn, int(user_row["id"]))
    except OPERATIONAL_ERRORS as exc:
        if _is_sqlite_locked_error(exc):
            _log_locked_db("/miniapp/literature/topics", started_at)
            return _database_busy_response()
        raise
    return _json(HTTPStatus.OK, {"ok": True, "literature_topics": list_literature_topic_payloads(user_states)})


def build_literature_items_response(
    db_path: str,
    bot_token: str,
    init_data: str,
    topic_id: str | None = None,
    *,
    max_age_seconds: int = 3600,
) -> tuple[int, dict[str, str], bytes]:
    started_at = time.time()
    try:
        verified = verify_telegram_init_data(init_data, bot_token, max_age_seconds=max_age_seconds)
    except InitDataValidationError as exc:
        return _json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": str(exc)})
    normalized_topic_id = topic_id.strip() if isinstance(topic_id, str) and topic_id.strip() else None
    try:
        items = load_literature_items(normalized_topic_id)
    except FileNotFoundError:
        items = []
    try:
        with closing(get_connection(db_path)) as conn:
            with conn:
                user_row = create_or_load_user(conn, verified.telegram_user_id, verified.username, verified.first_name, verified.last_name)
                user_states = _load_literature_item_states_by_user(conn, int(user_row["id"]))
    except OPERATIONAL_ERRORS as exc:
        if _is_sqlite_locked_error(exc):
            _log_locked_db("/miniapp/literature/items", started_at)
            return _database_busy_response()
        raise
    enriched_items = []
    for item in items:
        enriched = dict(item)
        item_id = enriched.get("id")
        if isinstance(item_id, str) and item_id in user_states:
            enriched["user_state"] = user_states[item_id]
        enriched_items.append(enriched)
    return _json(HTTPStatus.OK, {"ok": True, "literature_items": enriched_items})


def build_literature_state_response(
    db_path: str,
    bot_token: str,
    init_data: str,
    *,
    max_age_seconds: int = 3600,
) -> tuple[int, dict[str, str], bytes]:
    started_at = time.time()
    try:
        verified = verify_telegram_init_data(init_data, bot_token, max_age_seconds=max_age_seconds)
    except InitDataValidationError as exc:
        return _json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": str(exc)})
    try:
        with closing(get_connection(db_path)) as conn:
            with conn:
                user_row = create_or_load_user(conn, verified.telegram_user_id, verified.username, verified.first_name, verified.last_name)
                states = list(_load_literature_progress_by_user(conn, int(user_row["id"])).values())
    except OPERATIONAL_ERRORS as exc:
        if _is_sqlite_locked_error(exc):
            _log_locked_db("/miniapp/literature/state", started_at)
            return _database_busy_response()
        raise
    return _json(HTTPStatus.OK, {"ok": True, "literature_state": states})


def build_literature_progress_response(
    db_path: str,
    bot_token: str,
    init_data: str,
    body: bytes,
    *,
    max_age_seconds: int = 3600,
) -> tuple[int, dict[str, str], bytes]:
    started_at = time.time()
    try:
        verified = verify_telegram_init_data(init_data, bot_token, max_age_seconds=max_age_seconds)
    except InitDataValidationError as exc:
        return _json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": str(exc)})
    payload = _parse_json_payload(body)
    if payload is None:
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
    validated = _validate_literature_progress_payload(payload)
    if isinstance(validated, str):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": validated})
    literature_id, reading_status, progress_percent = validated
    try:
        with closing(get_connection(db_path)) as conn:
            with conn:
                user_row = create_or_load_user(conn, verified.telegram_user_id, verified.username, verified.first_name, verified.last_name)
                progress = _upsert_literature_progress(conn, int(user_row["id"]), literature_id, reading_status, progress_percent)
    except OPERATIONAL_ERRORS as exc:
        if _is_sqlite_locked_error(exc):
            _log_locked_db("/miniapp/literature/progress", started_at)
            return _database_busy_response()
        raise
    return _json(HTTPStatus.OK, {"ok": True, "literature_progress": progress})

def _is_glossary_setup_payload(payload: dict[str, Any]) -> bool:
    return payload.get("mode") == "glossary" or payload.get("quiz_mode") == "glossary"


@_glossary_errors
def _build_existing_endpoint_glossary_setup_response(db_path: str, verified: VerifiedInitData, payload: dict[str, Any]):
    topic_id = payload.get("topic_id")
    try:
        count = _normalize_glossary_question_count(payload.get("question_count"))
    except ValueError:
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_glossary_setup"})
    if not isinstance(topic_id, str):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_glossary_setup"})
    state = start_glossary_session(verified.telegram_user_id, topic_id, count, db_path=db_path,
        expected_session_id=payload.get("expected_session_id"), replace_active=payload.get("replace_active"))
    if state is None:
        return _json(HTTPStatus.CONFLICT, {"ok": False, "error": "glossary_unavailable"})
    return _json(HTTPStatus.OK, {"ok": True, "mode": "glossary", "glossary_state": state})


@_glossary_errors
def _build_existing_endpoint_glossary_answer_response(db_path: str, verified: VerifiedInitData, payload: dict[str, Any]):
    action = payload.get("action")
    if action == "state":
        state = run_glossary(db_path, verified.telegram_user_id, glossary_service.state)
        return _json(HTTPStatus.OK, {"ok": True, "mode": "glossary", "glossary_state": state})
    session_id = payload.get("session_id")
    if not isinstance(action, str) or action not in {"answer", "next", "restart"}:
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_glossary_action"})
    if not isinstance(session_id, str):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_glossary_session"})
    step_id = payload.get("step_id")
    if action in {"answer", "next"} and not is_sqlite_integer(step_id, minimum=1):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "glossary_step_required"})
    if action == "answer":
        selected = payload.get("selected_option_index")
        if not is_sqlite_integer(selected):
            return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_glossary_answer"})
        state = answer_glossary_session(verified.telegram_user_id, session_id, selected, step_id, db_path=db_path)
        error = "invalid_glossary_answer"
    elif action == "next":
        state = next_glossary_session(verified.telegram_user_id, session_id, step_id, db_path=db_path)
        error = "invalid_glossary_session"
    else:
        state = restart_glossary_session(verified.telegram_user_id, session_id, db_path=db_path)
        error = "invalid_glossary_session"
    if state is None:
        return _json(HTTPStatus.CONFLICT, {"ok": False, "error": error})
    return _json(HTTPStatus.OK, {"ok": True, "mode": "glossary", "glossary_state": state})

def build_state_response(
    db_path: str,
    bot_token: str,
    init_data: str,
    *,
    max_age_seconds: int = 3600,
) -> tuple[int, dict[str, str], bytes]:
    started_at = time.time()
    try:
        verified = verify_telegram_init_data(init_data, bot_token, max_age_seconds=max_age_seconds)
    except InitDataValidationError as exc:
        return _json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": str(exc)})

    try:
        with closing(get_connection(db_path)) as conn:
            with conn:
                user_row = create_or_load_user(
                    conn,
                    verified.telegram_user_id,
                    verified.username,
                    verified.first_name,
                    verified.last_name,
                )
                payload = quiz_state(conn, actor_user_id=int(user_row["id"]))
    except OPERATIONAL_ERRORS as exc:
        if _is_sqlite_locked_error(exc):
            _log_locked_db("/miniapp/state", started_at)
            return _database_busy_response()
        raise
    return _json(HTTPStatus.OK, payload)




def build_answer_response(
    db_path: str,
    bot_token: str,
    init_data: str,
    body: bytes,
    *,
    max_age_seconds: int = 3600,
) -> tuple[int, dict[str, str], bytes]:
    started_at = time.time()
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
    if payload.get("mode") == "glossary":
        return _build_existing_endpoint_glossary_answer_response(db_path, verified, payload)
    req = (payload.get("session_id"), payload.get("question_id"), payload.get("selected_option_index"))
    if not (is_sqlite_integer(req[0], minimum=1) and is_sqlite_integer(req[1], minimum=1)
            and is_sqlite_integer(req[2])):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_payload"})

    try:
        with closing(get_connection(db_path)) as conn:
            with conn:
                user_row = create_or_load_user(conn, verified.telegram_user_id, verified.username, verified.first_name, verified.last_name)
                result = answer_quiz(conn, actor_user_id=int(user_row["id"]), session_id=req[0],
                                     question_id=req[1], selected_option_index=req[2])
                return _json(HTTPStatus.OK, result)
    except OPERATIONAL_ERRORS as exc:
        if _is_sqlite_locked_error(exc):
            _log_locked_db("/miniapp/answer", started_at)
            return _database_busy_response()
        raise


def build_setup_response(db_path: str, bot_token: str, init_data: str, body: bytes, *, max_age_seconds: int = 3600):
    started_at = time.time()
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
    if _is_glossary_setup_payload(payload):
        return _build_existing_endpoint_glossary_setup_response(db_path, verified, payload)

    if not valid_quiz_setup(payload):
        return _json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_setup"})

    try:
        with closing(get_connection(db_path)) as conn:
            with conn:
                # Validate before profile/session writes; malformed setup is read-only.
                try:
                    existing = conn.execute("SELECT id FROM users WHERE telegram_user_id=?",
                                            (verified.telegram_user_id,)).fetchone()
                    prepared = prepare_quiz(conn, payload, actor_user_id=int(existing[0]) if existing else None)
                except QuizSetupError as exc:
                    status = HTTPStatus.BAD_REQUEST if str(exc) == "invalid_setup" else HTTPStatus.CONFLICT
                    return _json(status, {"ok": False, "error": str(exc)})
                user_row = create_or_load_user(conn, verified.telegram_user_id, verified.username, verified.first_name, verified.last_name)
                state = start_prepared_quiz(conn, actor_user_id=int(user_row["id"]), prepared=prepared)
    except OPERATIONAL_ERRORS as exc:
        if _is_sqlite_locked_error(exc):
            _log_locked_db("/miniapp/setup", started_at)
            return _database_busy_response()
        raise
    return _json(HTTPStatus.OK, {"ok": True, "runner_state": state})


def build_setup_options_response(
    db_path: str,
    bot_token: str,
    init_data: str,
    *,
    max_age_seconds: int = 3600,
) -> tuple[int, dict[str, str], bytes]:
    started_at = time.time()
    try:
        verified = verify_telegram_init_data(init_data, bot_token, max_age_seconds=max_age_seconds)
    except InitDataValidationError as exc:
        return _json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": str(exc)})

    try:
        with closing(get_connection(db_path)) as conn:
            with conn:
                create_or_load_user(conn, verified.telegram_user_id, verified.username, verified.first_name, verified.last_name)
                options = quiz_setup_options(conn)
    except OPERATIONAL_ERRORS as exc:
        if _is_sqlite_locked_error(exc):
            _log_locked_db("/miniapp/setup-options", started_at)
            return _database_busy_response()
        raise
    glossary = list_glossary_topics_payload()
    return _json(
        HTTPStatus.OK,
        {
            "ok": True,
            "setup_options": {
                **options,
                "modes": [{"mode": "topics", "title": "Тесты по темам"}, {"mode": "glossary", "title": "Глоссарий"}],
                "glossary": glossary,
            },
            "setup": {"glossary": glossary},
            "glossary": glossary,
        },
    )


class MiniAppApiHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Structured endpoint logs below exclude raw URLs, queries and credentials.
        return

    protocol_version = "HTTP/1.1"
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
        started_at = time.time()
        endpoint = self.path.split("?")[0]
        request_id = _read_request_id(self.headers)
        origin = self.headers.get("Origin", "")
        allowed = bool(self.allowed_origin and origin == self.allowed_origin)
        if endpoint not in {"/miniapp/state", "/miniapp/setup-options", "/miniapp/answer", "/miniapp/setup", "/miniapp/glossary/topics", "/miniapp/glossary/start", "/miniapp/glossary/answer", "/miniapp/glossary/next", "/miniapp/glossary/restart", "/miniapp/literature/topics", "/miniapp/literature/items", "/miniapp/literature/state", "/miniapp/literature/progress"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            logger.info("miniapp_options endpoint=%s request_id=%s method=OPTIONS status=%s duration_ms=%s origin_allowed=%s", "unknown", request_id or "-", HTTPStatus.NOT_FOUND.value, int((time.time() - started_at) * 1000), "yes" if allowed else "no")
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._set_common_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Telegram-Init-Data, X-Miniapp-Request-Id")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()
        logger.info("miniapp_options endpoint=%s request_id=%s method=OPTIONS status=%s duration_ms=%s origin_allowed=%s", endpoint, request_id or "-", HTTPStatus.NO_CONTENT.value, int((time.time() - started_at) * 1000), "yes" if allowed else "no")

    def do_GET(self):
        started_at = time.time()
        endpoint = self.path.split("?")[0]
        request_id = _read_request_id(self.headers)
        transport = "header_auth"
        init_data = _extract_init_data(self.headers)
        if endpoint not in {"/miniapp/state", "/miniapp/setup-options", "/miniapp/glossary/topics", "/miniapp/literature/topics", "/miniapp/literature/items", "/miniapp/literature/state"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            if endpoint == "/miniapp/state":
                status, headers, body = build_state_response(
                    self.db_path,
                    self.bot_token,
                    init_data,
                    max_age_seconds=self.initdata_ttl_seconds,
                )
            elif endpoint == "/miniapp/setup-options":
                status, headers, body = build_setup_options_response(
                    self.db_path,
                    self.bot_token,
                    init_data,
                    max_age_seconds=self.initdata_ttl_seconds,
                )
            elif endpoint == "/miniapp/glossary/topics":
                status, headers, body = build_glossary_topics_response(
                    self.bot_token,
                    init_data,
                    max_age_seconds=self.initdata_ttl_seconds,
                )
            elif endpoint == "/miniapp/literature/topics":
                status, headers, body = build_literature_topics_response(
                    self.db_path, self.bot_token, init_data, max_age_seconds=self.initdata_ttl_seconds
                )
            elif endpoint == "/miniapp/literature/items":
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                status, headers, body = build_literature_items_response(
                    self.db_path, self.bot_token, init_data, (params.get("topic_id") or [None])[0], max_age_seconds=self.initdata_ttl_seconds
                )
            else:
                status, headers, body = build_literature_state_response(
                    self.db_path, self.bot_token, init_data, max_age_seconds=self.initdata_ttl_seconds
                )
        except OPERATIONAL_ERRORS as exc:
            if not _is_sqlite_locked_error(exc):
                raise
            _log_locked_db(endpoint, started_at)
            status, headers, body = _database_busy_response()
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self._set_common_headers()
        self.end_headers()
        self.wfile.write(body)
        error_code = ""
        try:
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("error"), str):
                error_code = payload["error"]
        except Exception:
            pass
        logger.info(
            "miniapp_api endpoint=%s request_id=%s transport=%s method=GET status=%s duration_ms=%s error_code=%s",
            endpoint,
            request_id or "-",
            transport,
            status,
            int((time.time() - started_at) * 1000),
            error_code or "-",
        )

    def do_POST(self):
        started_at = time.time()
        endpoint = self.path.split("?")[0]
        request_id = _read_request_id(self.headers)
        transport = "header_auth"
        if endpoint not in {"/miniapp/answer", "/miniapp/setup", "/miniapp/glossary/start", "/miniapp/glossary/answer", "/miniapp/glossary/next", "/miniapp/glossary/restart", "/miniapp/literature/progress"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        init_data, payload_body, body_request_id, transport = _extract_transport_payload(self.headers, body)
        request_id = body_request_id or request_id
        try:
            if endpoint == "/miniapp/answer":
                status, headers, data = build_answer_response(
                    self.db_path,
                    self.bot_token,
                    init_data,
                    payload_body,
                    max_age_seconds=self.initdata_ttl_seconds,
                )
            elif endpoint == "/miniapp/setup":
                status, headers, data = build_setup_response(
                    self.db_path,
                    self.bot_token,
                    init_data,
                    payload_body,
                    max_age_seconds=self.initdata_ttl_seconds,
                )
            elif endpoint == "/miniapp/literature/progress":
                status, headers, data = build_literature_progress_response(
                    self.db_path, self.bot_token, init_data, payload_body, max_age_seconds=self.initdata_ttl_seconds
                )
            elif endpoint == "/miniapp/glossary/start":
                status, headers, data = build_glossary_start_response(self.db_path, self.bot_token, init_data, payload_body, max_age_seconds=self.initdata_ttl_seconds)
            elif endpoint == "/miniapp/glossary/answer":
                status, headers, data = build_glossary_answer_response(self.db_path, self.bot_token, init_data, payload_body, max_age_seconds=self.initdata_ttl_seconds)
            elif endpoint == "/miniapp/glossary/next":
                status, headers, data = build_glossary_next_response(self.db_path, self.bot_token, init_data, payload_body, max_age_seconds=self.initdata_ttl_seconds)
            else:
                status, headers, data = build_glossary_restart_response(self.db_path, self.bot_token, init_data, payload_body, max_age_seconds=self.initdata_ttl_seconds)
        except OPERATIONAL_ERRORS as exc:
            if not _is_sqlite_locked_error(exc):
                raise
            _log_locked_db(endpoint, started_at)
            status, headers, data = _database_busy_response()
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self._set_common_headers()
        self.end_headers()
        self.wfile.write(data)
        error_code = ""
        try:
            payload = json.loads(data.decode("utf-8"))
            if isinstance(payload, dict):
                if isinstance(payload.get("error"), str):
                    error_code = payload["error"]
        except Exception:
            pass
        logger.info(
            "miniapp_api endpoint=%s request_id=%s transport=%s method=POST status=%s duration_ms=%s error_code=%s",
            endpoint,
            request_id or "-",
            transport,
            status,
            int((time.time() - started_at) * 1000),
            error_code or "-",
        )


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
