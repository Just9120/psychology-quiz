from __future__ import annotations

import json
import logging
import os
import time
import asyncio
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import Response
from app.web_config import WebSettings

from app.logging_config import configure_noisy_http_client_loggers, install_telegram_url_redaction
from app.miniapp_api import (
    _extract_init_data,
    _extract_transport_payload,
    _read_request_id,
    build_answer_response,
    build_glossary_answer_response,
    build_glossary_next_response,
    build_glossary_restart_response,
    build_glossary_start_response,
    build_glossary_topics_response,
    build_literature_items_response,
    build_literature_progress_response,
    build_literature_state_response,
    build_literature_topics_response,
    build_setup_options_response,
    build_setup_response,
    build_state_response,
)

logger = logging.getLogger("uvicorn.error")

_ENDPOINTS = {"/miniapp/state", "/miniapp/setup-options", "/miniapp/setup", "/miniapp/answer", "/miniapp/glossary/topics", "/miniapp/glossary/start", "/miniapp/glossary/answer", "/miniapp/glossary/next", "/miniapp/glossary/restart", "/miniapp/literature/topics", "/miniapp/literature/items", "/miniapp/literature/state", "/miniapp/literature/progress"}


def _to_response(status: int, headers: dict[str, str], body: bytes) -> Response:
    return Response(content=body, status_code=status, headers=headers)


def _duration_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _log_request(
    *,
    endpoint: str,
    method: str,
    status: int,
    started_at: float,
    request_id: str,
    transport: str,
    body: bytes,
    slow_request_ms: int,
) -> None:
    error_code = "-"
    try:
        payload = json.loads(body.decode("utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("error"), str):
            error_code = payload["error"]
    except Exception:
        pass

    duration_ms = _duration_ms(started_at)
    logger.info(
        "miniapp_api endpoint=%s request_id=%s transport=%s method=%s status=%s duration_ms=%s error_code=%s",
        endpoint,
        request_id or "-",
        transport,
        method,
        status,
        duration_ms,
        error_code,
    )
    if duration_ms > slow_request_ms:
        logger.warning(
            "miniapp_api_slow endpoint=%s duration_ms=%s status=%s request_id=%s",
            endpoint,
            duration_ms,
            status,
            request_id or "-",
        )


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var for FastAPI runtime: {name}")
    return value


async def _run_builder_in_thread(builder: Any, *args: Any, **kwargs: Any) -> tuple[int, dict[str, str], bytes]:
    return await asyncio.to_thread(builder, *args, **kwargs)


def create_app_from_env() -> FastAPI:
    install_telegram_url_redaction()
    configure_noisy_http_client_loggers()
    return create_app(
        db_path=_required_env("DB_PATH"),
        bot_token=_required_env("BOT_TOKEN"),
        initdata_ttl_seconds=int(os.getenv("MINIAPP_API_INITDATA_TTL_SECONDS", "3600")),
        slow_request_ms=int(os.getenv("MINIAPP_API_SLOW_REQUEST_MS", "500")),
        allowed_origin=os.getenv("MINIAPP_API_ALLOWED_ORIGIN", "").strip() or None,
        revision=os.getenv("APP_REVISION", "UNSET"),
        web_settings=WebSettings.from_env(),
    )


def create_app(
    *,
    db_path: str,
    bot_token: str,
    initdata_ttl_seconds: int = 3600,
    slow_request_ms: int = 500,
    allowed_origin: str | None = None,
    revision: str = "UNSET",
    web_settings: WebSettings | None = None,
    web_mailer=None,
    web_clock=time.time,
) -> FastAPI:
    app = FastAPI(redirect_slashes=False)

    def _set_common_headers(response: Response, request: Request) -> None:
        response.headers["Cache-Control"] = "no-store"
        request_origin = request.headers.get("Origin", "")
        if allowed_origin and request_origin == allowed_origin:
            response.headers["Access-Control-Allow-Origin"] = allowed_origin
            response.headers["Vary"] = "Origin"

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True, "service": "miniapp_api", "revision": revision}

    async def _options_response(endpoint: str, request: Request) -> Response:
        started_at = time.perf_counter()
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

        duration_ms = _duration_ms(started_at)
        logger.info(
            "miniapp_api endpoint=%s request_id=%s transport=preflight method=OPTIONS status=%s duration_ms=%s error_code=-",
            endpoint,
            request_id or "-",
            response.status_code,
            duration_ms,
        )
        if duration_ms > slow_request_ms:
            logger.warning(
                "miniapp_api_slow endpoint=%s duration_ms=%s status=%s request_id=%s",
                endpoint,
                duration_ms,
                response.status_code,
                request_id or "-",
            )

        logger.info(
            "miniapp_options endpoint=%s request_id=%s method=OPTIONS status=%s duration_ms=%s origin_allowed=%s",
            endpoint,
            request_id or "-",
            response.status_code,
            duration_ms,
            "yes" if allowed else "no",
        )
        return response

    @app.options("/miniapp/state")
    async def options_state(request: Request) -> Response:
        return await _options_response("/miniapp/state", request)

    @app.options("/miniapp/setup-options")
    async def options_setup_options(request: Request) -> Response:
        return await _options_response("/miniapp/setup-options", request)

    @app.options("/miniapp/setup")
    async def options_setup(request: Request) -> Response:
        return await _options_response("/miniapp/setup", request)

    @app.options("/miniapp/answer")
    async def options_answer(request: Request) -> Response:
        return await _options_response("/miniapp/answer", request)


    @app.options("/miniapp/glossary/topics")
    async def options_glossary_topics(request: Request) -> Response:
        return await _options_response("/miniapp/glossary/topics", request)

    @app.options("/miniapp/glossary/start")
    async def options_glossary_start(request: Request) -> Response:
        return await _options_response("/miniapp/glossary/start", request)

    @app.options("/miniapp/glossary/answer")
    async def options_glossary_answer(request: Request) -> Response:
        return await _options_response("/miniapp/glossary/answer", request)

    @app.options("/miniapp/glossary/next")
    async def options_glossary_next(request: Request) -> Response:
        return await _options_response("/miniapp/glossary/next", request)

    @app.options("/miniapp/glossary/restart")
    async def options_glossary_restart(request: Request) -> Response:
        return await _options_response("/miniapp/glossary/restart", request)

    @app.options("/miniapp/literature/topics")
    async def options_literature_topics(request: Request) -> Response:
        return await _options_response("/miniapp/literature/topics", request)

    @app.options("/miniapp/literature/items")
    async def options_literature_items(request: Request) -> Response:
        return await _options_response("/miniapp/literature/items", request)

    @app.options("/miniapp/literature/state")
    async def options_literature_state(request: Request) -> Response:
        return await _options_response("/miniapp/literature/state", request)

    @app.options("/miniapp/literature/progress")
    async def options_literature_progress(request: Request) -> Response:
        return await _options_response("/miniapp/literature/progress", request)

    async def _get_builder_response(endpoint: str, request: Request, builder: Any, *builder_args: Any) -> Response:
        started_at = time.perf_counter()
        request_id = _read_request_id(request.headers)
        transport = "header_auth"
        init_data = _extract_init_data(request.headers)
        status, headers, body = await _run_builder_in_thread(
            builder,
            *builder_args,
            init_data,
            max_age_seconds=initdata_ttl_seconds,
        )
        response = _to_response(status, headers, body)
        _set_common_headers(response, request)
        _log_request(endpoint=endpoint, method="GET", status=status, started_at=started_at, request_id=request_id, transport=transport, body=body, slow_request_ms=slow_request_ms)
        return response

    async def _post_builder_response(endpoint: str, request: Request, builder: Any, *builder_args: Any) -> Response:
        started_at = time.perf_counter()
        request_id = _read_request_id(request.headers)
        raw_body = await request.body()
        init_data, payload_body, body_request_id, transport = _extract_transport_payload(request.headers, raw_body)
        request_id = body_request_id or request_id
        status, headers, body = await _run_builder_in_thread(
            builder,
            *builder_args,
            init_data,
            payload_body,
            max_age_seconds=initdata_ttl_seconds,
        )
        response = _to_response(status, headers, body)
        _set_common_headers(response, request)
        _log_request(endpoint=endpoint, method="POST", status=status, started_at=started_at, request_id=request_id, transport=transport, body=body, slow_request_ms=slow_request_ms)
        return response

    @app.get("/miniapp/state")
    async def get_state(request: Request) -> Response:
        return await _get_builder_response("/miniapp/state", request, build_state_response, db_path, bot_token)

    @app.get("/miniapp/setup-options")
    async def get_setup_options(request: Request) -> Response:
        return await _get_builder_response("/miniapp/setup-options", request, build_setup_options_response, db_path, bot_token)

    @app.post("/miniapp/setup")
    async def post_setup(request: Request) -> Response:
        return await _post_builder_response("/miniapp/setup", request, build_setup_response, db_path, bot_token)

    @app.post("/miniapp/answer")
    async def post_answer(request: Request) -> Response:
        return await _post_builder_response("/miniapp/answer", request, build_answer_response, db_path, bot_token)

    @app.get("/miniapp/glossary/topics")
    async def get_glossary_topics(request: Request) -> Response:
        return await _get_builder_response("/miniapp/glossary/topics", request, build_glossary_topics_response, bot_token)

    @app.get("/miniapp/literature/topics")
    async def get_literature_topics(request: Request) -> Response:
        return await _get_builder_response("/miniapp/literature/topics", request, build_literature_topics_response, db_path, bot_token)

    @app.get("/miniapp/literature/items")
    async def get_literature_items(request: Request) -> Response:
        started_at = time.perf_counter()
        request_id = _read_request_id(request.headers)
        transport = "header_auth"
        init_data = _extract_init_data(request.headers)
        topic_id = request.query_params.get("topic_id")
        status, headers, body = await _run_builder_in_thread(
            build_literature_items_response,
            db_path,
            bot_token,
            init_data,
            topic_id,
            max_age_seconds=initdata_ttl_seconds,
        )
        response = _to_response(status, headers, body)
        _set_common_headers(response, request)
        _log_request(endpoint="/miniapp/literature/items", method="GET", status=status, started_at=started_at, request_id=request_id, transport=transport, body=body, slow_request_ms=slow_request_ms)
        return response

    @app.get("/miniapp/literature/state")
    async def get_literature_state(request: Request) -> Response:
        return await _get_builder_response("/miniapp/literature/state", request, build_literature_state_response, db_path, bot_token)

    @app.post("/miniapp/literature/progress")
    async def post_literature_progress(request: Request) -> Response:
        return await _post_builder_response("/miniapp/literature/progress", request, build_literature_progress_response, db_path, bot_token)

    async def _post_glossary(request: Request, endpoint: str, builder: Any) -> Response:
        return await _post_builder_response(endpoint, request, builder, bot_token)

    @app.post("/miniapp/glossary/start")
    async def post_glossary_start(request: Request) -> Response:
        return await _post_glossary(request, "/miniapp/glossary/start", build_glossary_start_response)

    @app.post("/miniapp/glossary/answer")
    async def post_glossary_answer(request: Request) -> Response:
        return await _post_glossary(request, "/miniapp/glossary/answer", build_glossary_answer_response)

    @app.post("/miniapp/glossary/next")
    async def post_glossary_next(request: Request) -> Response:
        return await _post_glossary(request, "/miniapp/glossary/next", build_glossary_next_response)

    @app.post("/miniapp/glossary/restart")
    async def post_glossary_restart(request: Request) -> Response:
        return await _post_glossary(request, "/miniapp/glossary/restart", build_glossary_restart_response)

    if web_settings is not None:
        from app.web_auth import WebAuth
        from app.web_api import install_web_api
        from app.web_mail import SmtpMailer
        auth = WebAuth(db_path, web_settings, web_mailer if web_mailer is not None else SmtpMailer(web_settings), clock=web_clock)
        install_web_api(app, auth)
        app.state.web_auth = auth
    return app
