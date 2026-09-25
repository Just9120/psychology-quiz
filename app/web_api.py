"""Same-origin owner API; no Telegram credentials or client-supplied actor IDs."""
import asyncio
import json
import logging
from app.database import OPERATIONAL_ERRORS, begin_write
from app import glossary_service, learning_reset, progress_service, literature_service
from app.mastery import quiz_states
from urllib.parse import unquote

from fastapi import Request
from fastapi.responses import JSONResponse

from app.payload_validation import is_sqlite_integer
from app.quiz_service import QuizSetupError, answer_quiz, prepare_quiz, quiz_setup_options, quiz_state, start_prepared_quiz
from app.web_auth import AuthError, SESSION_TTL, WebAuth
from app.logging_config import configure_noisy_http_client_loggers

GET_ACTIONS = {"auth/me", "quiz/state", "quiz/options", "progress/overview", "progress/mastery", "glossary/state", "glossary/options", "literature/catalog"}
POST_ACTIONS = {"auth/register", "auth/verify", "auth/recover", "auth/reset", "auth/login", "auth/logout",
                "identity/new", "link/start", "link/complete", "quiz/setup", "quiz/answer", "literature/progress",
                "progress/history", "progress/attempt", "progress/errors", "progress/train",
                "progress/reset-preview", "progress/reset-confirm", "glossary/setup", "glossary/answer", "glossary/next", "glossary/restart"}
logger = logging.getLogger(__name__)


class WebAccessLogFilter(logging.Filter):
    def filter(self, record):
        # Structured logs below replace raw Uvicorn URLs/client identifiers.
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            path = record.args[2]
            if isinstance(path, str) and unquote(path).startswith("/web"):
                return False
        return True


def _dispatch(auth: WebAuth, action: str, payload: dict, token: str | None, csrf: str | None):
    if action in {"auth/register", "auth/recover"}:
        auth.request_mail(payload.get("email"), "register" if action == "auth/register" else "recover")
        return {"ok": True}, None
    if action in {"auth/verify", "auth/reset"}:
        auth.set_password(payload.get("token"), payload.get("password"), "register" if action == "auth/verify" else "recover")
        return {"ok": True}, None
    if action == "auth/login":
        session = auth.login(payload.get("email"), payload.get("password"))
        return {"ok": True}, session
    with auth.transaction() as conn:
        account = auth.authenticate(conn, token, csrf=csrf, mutation=action in POST_ACTIONS)
        if action == "auth/me":
            return auth.account_state(conn, account, token), None
        if action == "auth/logout":
            conn.execute("DELETE FROM web_sessions WHERE digest=?", (account["session_digest"],))
            return {"ok": True}, ""
        if action == "identity/new":
            auth.fresh_identity(conn, account)
            return {"ok": True}, None
        if action == "link/start":
            return {"ok": True, "code": auth.start_link(conn, account)}, None
        if action == "link/complete":
            auth.complete_link(conn, account)
            return {"ok": True}, None
        actor = account["user_id"]
        if actor is None:
            raise AuthError("identity_required", 409)
        if action == "literature/catalog":
            return literature_service.catalog(conn, actor), None
        if action == "literature/progress":
            validated = literature_service.validate_progress(payload)
            if isinstance(validated, str):
                raise AuthError(validated, 400)
            state = literature_service.save_progress(conn, actor, *validated)
            return {"ok": True, "literature_progress": state}, None
        if action.startswith('glossary/'):
            try:
                if action == 'glossary/options':
                    return {'ok': True, **glossary_service.topics()}, None
                if action == 'glossary/state':
                    result = glossary_service.state(conn, actor)
                elif action == 'glossary/setup':
                    result = glossary_service.start(conn, actor, payload.get('topic_id'), payload.get('question_count'),
                        expected_session_id=payload.get('expected_session_id'), replace_active=payload.get('replace_active'))
                elif action == 'glossary/answer':
                    result = glossary_service.answer(conn, actor, payload.get('session_id'), payload.get('selected_option_index'), payload.get('step_id'))
                elif action == 'glossary/next':
                    result = glossary_service.advance(conn, actor, payload.get('session_id'), payload.get('step_id'))
                else:
                    result = glossary_service.restart(conn, actor, payload.get('session_id'))
                return {'ok': True, 'glossary_state': result}, None
            except glossary_service.GlossaryError as exc:
                raise AuthError(exc.code, exc.status) from None
        if action.startswith("progress/"):
            begin_write(conn, f"actor:{actor}")
            try:
                if action == "progress/overview":
                    return progress_service.overview(conn, actor), None
                if action == "progress/mastery":
                    return quiz_states(conn, actor), None
                if action == "progress/history":
                    return progress_service.history(conn, actor, payload.get("before"), payload.get("scope")), None
                if action == "progress/attempt":
                    return progress_service.attempt(conn, actor, payload.get("session_id"), payload.get("after")), None
                if action == "progress/errors":
                    return progress_service.errors(conn, actor, payload.get("before")), None
                if action == "progress/reset-preview":
                    return learning_reset.preview(conn, actor, payload), None
                if action == "progress/reset-confirm":
                    return learning_reset.confirm(conn, actor, payload), None
                return progress_service.train_errors(conn, actor, payload), None
            except progress_service.ProgressError as exc:
                raise AuthError(exc.code, exc.status) from None
        if action == "quiz/options":
            return {"ok": True, "setup_options": quiz_setup_options(conn)}, None
        if action == "quiz/state":
            return quiz_state(conn, actor_user_id=actor), None
        if action == "quiz/setup":
            try:
                prepared = prepare_quiz(conn, payload)
            except QuizSetupError as exc:
                raise AuthError(str(exc), 400 if str(exc) == "invalid_setup" else 409) from None
            return {"ok": True, "runner_state": start_prepared_quiz(conn, actor_user_id=actor, prepared=prepared)}, None
        if action == "quiz/answer":
            sid, qid, choice = payload.get("session_id"), payload.get("question_id"), payload.get("selected_option_index")
            if not (is_sqlite_integer(sid, minimum=1) and is_sqlite_integer(qid, minimum=1) and is_sqlite_integer(choice)):
                raise AuthError("invalid_payload")
            result = answer_quiz(conn, actor_user_id=actor, session_id=sid, question_id=qid, selected_option_index=choice)
            if result["submission_status"] == "forbidden":
                raise AuthError("forbidden", 403)
            return result, None
        raise AuthError("not_found", 404)


def install_web_api(app, auth: WebAuth) -> None:
    configure_noisy_http_client_loggers()
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, WebAccessLogFilter) for item in access.filters):
        access.addFilter(WebAccessLogFilter())

    @app.api_route("/web/{action:path}", methods=["GET", "POST", "OPTIONS", "PUT", "DELETE", "PATCH"])
    async def web_endpoint(action: str, request: Request):
        cookie = None
        try:
            if action not in GET_ACTIONS | POST_ACTIONS:
                raise AuthError("not_found", 404)
            method = "GET" if action in GET_ACTIONS else "POST"
            if request.method != method:
                raise AuthError("method_not_allowed", 405)
            origin = request.headers.get("origin")
            if (method == "POST" and origin != auth.settings.origin) or (origin and origin != auth.settings.origin):
                raise AuthError("origin_forbidden", 403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                raise AuthError("origin_forbidden", 403)
            if request.url.query:
                raise AuthError("query_not_allowed")
            payload = {}
            if method == "POST":
                if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                    raise AuthError("json_required", 415)
                body = bytearray()
                async for part in request.stream():
                    body.extend(part)
                    if len(body) > 16384:
                        raise AuthError("body_too_large", 413)
                try:
                    payload = json.loads(body)
                except (ValueError, UnicodeError, RecursionError):
                    raise AuthError("invalid_json") from None
                if not isinstance(payload, dict):
                    raise AuthError("invalid_payload")
            result, cookie = await asyncio.to_thread(_dispatch, auth, action, payload,
                request.cookies.get(auth.settings.cookie_name), request.headers.get("x-csrf-token"))
            response = JSONResponse(result)
        except AuthError as exc:
            response = JSONResponse({"ok": False, "error": exc.code}, status_code=exc.status)
        except OPERATIONAL_ERRORS:
            response = JSONResponse({"ok": False, "error": "database_unavailable"}, status_code=503)
        except Exception as exc:
            logger.error("web_api_failure type=%s", type(exc).__name__)
            response = JSONResponse({"ok": False, "error": "internal_error"}, status_code=500)
        if cookie is not None:
            response.set_cookie(auth.settings.cookie_name, cookie, max_age=SESSION_TTL if cookie else 0,
                                secure=auth.settings.secure_cookie, httponly=True, samesite="strict", path="/")
        response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff",
                                 "Referrer-Policy": "no-referrer", "Vary": "Cookie, Origin"})
        logger.info("web_api action=%s status=%s", action if action in GET_ACTIONS | POST_ACTIONS else "unknown", response.status_code)
        return response
