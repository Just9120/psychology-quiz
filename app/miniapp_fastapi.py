from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response

from app.miniapp_api import (
    _extract_init_data,
    _extract_transport_payload,
    _read_request_id,
    build_answer_response,
    build_setup_options_response,
    build_setup_response,
    build_state_response,
    verify_telegram_init_data,
)

logger = logging.getLogger(__name__)

_ENDPOINTS = {"/miniapp/state", "/miniapp/setup-options", "/miniapp/setup", "/miniapp/answer"}


def _to_response(status: int, headers: dict[str, str], body: bytes) -> Response:
    return Response(content=body, status_code=status, headers=headers)


def _log_request(
    *,
    endpoint: str,
    method: str,
    status: int,
    started_at: float,
    bot_token: str,
    init_data: str,
    max_age_seconds: int,
    request_id: str,
    transport: str,
    body: bytes,
) -> None:
    safe_user_id = "-"
    error_code = "-"
    try:
        payload = json.loads(body.decode("utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("error"), str):
            error_code = payload["error"]
    except Exception:
        pass
    try:
        verified = verify_telegram_init_data(init_data, bot_token, max_age_seconds=max_age_seconds)
        safe_user_id = str(verified.telegram_user_id)
    except Exception:
        pass

    logger.info(
        "miniapp_api endpoint=%s request_id=%s transport=%s method=%s status=%s duration_ms=%s telegram_user_id=%s error_code=%s",
        endpoint,
        request_id or "-",
        transport,
        method,
        status,
        int((time.time() - started_at) * 1000),
        safe_user_id,
        error_code,
    )



def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var for FastAPI runtime: {name}")
    return value


def create_app_from_env() -> FastAPI:
    return create_app(
        db_path=_required_env("DB_PATH"),
        bot_token=_required_env("BOT_TOKEN"),
        initdata_ttl_seconds=int(os.getenv("MINIAPP_API_INITDATA_TTL_SECONDS", "3600")),
        allowed_origin=os.getenv("MINIAPP_API_ALLOWED_ORIGIN", "").strip() or None,
    )

def create_app(*, db_path: str, bot_token: str, initdata_ttl_seconds: int = 3600, allowed_origin: str | None = None) -> FastAPI:
    app = FastAPI(redirect_slashes=False)

    def _set_common_headers(response: Response, request: Request) -> None:
        response.headers["Cache-Control"] = "no-store"
        request_origin = request.headers.get("Origin", "")
        if allowed_origin and request_origin == allowed_origin:
            response.headers["Access-Control-Allow-Origin"] = allowed_origin
            response.headers["Vary"] = "Origin"


    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True, "service": "miniapp_api"}

    @app.api_route("/miniapp/{rest:path}", methods=["OPTIONS"])
    async def options_handler(rest: str, request: Request) -> Response:
        started_at = time.time()
        endpoint = f"/miniapp/{rest}"
        request_id = _read_request_id(request.headers)
        origin = request.headers.get("Origin", "")
        allowed = bool(allowed_origin and origin == allowed_origin)
        if endpoint not in _ENDPOINTS:
            response = Response(status_code=404)
        else:
            response = Response(status_code=204, content=b"")
            _set_common_headers(response, request)
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-Telegram-Init-Data, X-Miniapp-Request-Id"
            response.headers["Access-Control-Max-Age"] = "600"
            response.headers["Content-Length"] = "0"

        logger.info(
            "miniapp_options endpoint=%s request_id=%s method=OPTIONS status=%s duration_ms=%s origin_allowed=%s req_method=%s req_headers=%s",
            endpoint,
            request_id or "-",
            response.status_code,
            int((time.time() - started_at) * 1000),
            "yes" if allowed else "no",
            request.headers.get("Access-Control-Request-Method", ""),
            request.headers.get("Access-Control-Request-Headers", ""),
        )
        return response

    @app.get("/miniapp/state")
    async def get_state(request: Request) -> Response:
        started_at = time.time()
        endpoint = "/miniapp/state"
        request_id = _read_request_id(request.headers)
        transport = "header_auth"
        init_data = _extract_init_data(request.headers)
        status, headers, body = build_state_response(db_path, bot_token, init_data, max_age_seconds=initdata_ttl_seconds)
        response = _to_response(status, headers, body)
        _set_common_headers(response, request)
        _log_request(endpoint=endpoint, method="GET", status=status, started_at=started_at, bot_token=bot_token, init_data=init_data, max_age_seconds=initdata_ttl_seconds, request_id=request_id, transport=transport, body=body)
        return response

    @app.get("/miniapp/setup-options")
    async def get_setup_options(request: Request) -> Response:
        started_at = time.time()
        endpoint = "/miniapp/setup-options"
        request_id = _read_request_id(request.headers)
        transport = "header_auth"
        init_data = _extract_init_data(request.headers)
        status, headers, body = build_setup_options_response(db_path, bot_token, init_data, max_age_seconds=initdata_ttl_seconds)
        response = _to_response(status, headers, body)
        _set_common_headers(response, request)
        _log_request(endpoint=endpoint, method="GET", status=status, started_at=started_at, bot_token=bot_token, init_data=init_data, max_age_seconds=initdata_ttl_seconds, request_id=request_id, transport=transport, body=body)
        return response

    @app.post("/miniapp/setup")
    async def post_setup(request: Request) -> Response:
        started_at = time.time()
        endpoint = "/miniapp/setup"
        request_id = _read_request_id(request.headers)
        raw_body = await request.body()
        init_data, payload_body, body_request_id, transport = _extract_transport_payload(request.headers, raw_body)
        request_id = body_request_id or request_id
        status, headers, body = build_setup_response(db_path, bot_token, init_data, payload_body, max_age_seconds=initdata_ttl_seconds)
        response = _to_response(status, headers, body)
        _set_common_headers(response, request)
        _log_request(endpoint=endpoint, method="POST", status=status, started_at=started_at, bot_token=bot_token, init_data=init_data, max_age_seconds=initdata_ttl_seconds, request_id=request_id, transport=transport, body=body)
        return response

    @app.post("/miniapp/answer")
    async def post_answer(request: Request) -> Response:
        started_at = time.time()
        endpoint = "/miniapp/answer"
        request_id = _read_request_id(request.headers)
        raw_body = await request.body()
        init_data, payload_body, body_request_id, transport = _extract_transport_payload(request.headers, raw_body)
        request_id = body_request_id or request_id
        status, headers, body = build_answer_response(db_path, bot_token, init_data, payload_body, max_age_seconds=initdata_ttl_seconds)
        response = _to_response(status, headers, body)
        _set_common_headers(response, request)
        _log_request(endpoint=endpoint, method="POST", status=status, started_at=started_at, bot_token=bot_token, init_data=init_data, max_age_seconds=initdata_ttl_seconds, request_id=request_id, transport=transport, body=body)
        return response

    return app
