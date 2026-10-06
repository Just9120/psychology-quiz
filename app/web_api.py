"""Same-origin owner API; no Telegram credentials or client-supplied actor IDs."""
import asyncio
import json
import logging
from html import escape
from app.request_body import RequestBodyTooLarge, read_request_body
from app.database import OPERATIONAL_ERRORS, begin_write
from app import glossary_service, learning_reset, progress_service, literature_service, repetition, learning_goals, achievements, homework
from app.mastery import overview as mastery_overview
from urllib.parse import unquote

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.payload_validation import is_sqlite_integer
from app.quiz_service import QuizSetupError, answer_quiz, prepare_quiz, quiz_setup_options, quiz_state, start_confirmed_quiz
from app.owner_google_oauth import OwnerGoogleOAuth, TTL as OAUTH_TTL
from app.web_auth import AuthError, SESSION_TTL, WebAuth
from app.logging_config import configure_noisy_http_client_loggers

GET_ACTIONS = {"auth/google/available", "auth/me", "quiz/state", "quiz/options", "homework/catalog", "progress/overview", "progress/mastery", "progress/review", "progress/goals", "progress/achievements", "glossary/state", "glossary/options", "literature/catalog"}
POST_ACTIONS = {"auth/google/begin", "auth/google/unlink", "auth/register", "auth/verify", "auth/recover", "auth/reset", "auth/login", "auth/logout",
                "identity/new", "link/start", "link/complete", "profile/name", "owner/stats", "owner/content", "quiz/setup", "quiz/answer", "homework/start", "literature/progress",
                "progress/history", "progress/attempt", "progress/errors", "progress/train",
                "progress/reset-preview", "progress/reset-confirm", "progress/review-start", "progress/review-glossary-start", "progress/goal-set", "glossary/setup", "glossary/answer", "glossary/next", "glossary/restart"}
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
    if action == "auth/google/available":
        with auth.transaction() as conn:
            linked = conn.execute("""SELECT 1 FROM web_google_identities g JOIN web_accounts a ON a.id=g.account_id
                WHERE a.email=? AND a.enabled=1""", (auth.settings.owner_email,)).fetchone()
        return {"ok": True, "available": auth.settings.google is not None and linked is not None}, None
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
        if action == "auth/google/unlink":
            OwnerGoogleOAuth(auth).unlink(conn, account)
            return {"ok": True}, None
        if action == "auth/me":
            return auth.account_state(conn, account, token), None
        if action == "auth/logout":
            conn.execute("DELETE FROM web_sessions WHERE digest=?", (account["session_digest"],))
            return {"ok": True}, ""
        if action == "profile/name":
            return {"ok": True, "display_name": auth.set_display_name(conn, account, payload.get("display_name"))}, None
        if action == "owner/content":
            if account["email"] != auth.settings.owner_email:
                raise AuthError("forbidden", 403)
            from app.owner_content import dashboard
            return dashboard(conn), None
        if action == "owner/stats":
            if account["email"] != auth.settings.owner_email:
                raise AuthError("forbidden", 403)
            from app.owner_stats import get_owner_period_stats
            try:
                return get_owner_period_stats(conn, payload.get("period")), None
            except ValueError:
                raise AuthError("invalid_period", 400) from None
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
                    return mastery_overview(conn, actor), None
                if action == "progress/review":
                    return repetition.queue(conn, actor), None
                if action == "progress/goals":
                    return learning_goals.overview(conn, actor), None
                if action == "progress/achievements":
                    return achievements.refresh(conn, actor), None
                if action == "progress/goal-set":
                    try:
                        return learning_goals.set_target(conn, actor, payload), None
                    except learning_goals.GoalError as error:
                        raise AuthError(error.code, 400) from None
                if action == "progress/history":
                    return progress_service.history(conn, actor, payload.get("before"), payload.get("scope")), None
                if action == "progress/attempt":
                    return progress_service.attempt(conn, actor, payload.get("session_id"), payload.get("after")), None
                if action == "progress/errors":
                    return progress_service.errors(conn, actor, payload.get("before")), None
                if action == "progress/review-start":
                    return progress_service.review_today(conn, actor, payload), None
                if action == "progress/review-glossary-start":
                    return progress_service.review_glossary_today(conn, actor, payload), None
                if action == "progress/reset-preview":
                    return learning_reset.preview(conn, actor, payload), None
                if action == "progress/reset-confirm":
                    return learning_reset.confirm(conn, actor, payload), None
                return progress_service.train_errors(conn, actor, payload), None
            except progress_service.ProgressError as exc:
                raise AuthError(exc.code, exc.status) from None
        if action == "quiz/options":
            return {"ok": True, "setup_options": quiz_setup_options(conn)}, None
        if action == "homework/catalog":
            return homework.catalog_for_actor(conn, actor), None
        if action == "homework/start":
            try:
                return homework.start_homework(conn, actor_user_id=actor,
                    assignment_id=payload.get("assignment_id"), payload=payload), None
            except homework.HomeworkError as exc:
                code = str(exc)
                raise AuthError(code, 400 if code == "invalid_homework" else 404 if code == "homework_unavailable" else 409) from None
        if action == "quiz/state":
            return quiz_state(conn, actor_user_id=actor), None
        if action == "quiz/setup":
            try:
                prepared = prepare_quiz(conn, payload, actor_user_id=actor)
            except QuizSetupError as exc:
                raise AuthError(str(exc), 400 if str(exc) == "invalid_setup" else 409) from None
            try:
                state = start_confirmed_quiz(conn, actor_user_id=actor, prepared=prepared, payload=payload)
            except QuizSetupError as exc:
                raise AuthError(str(exc), 400 if str(exc) == "invalid_setup" else 409) from None
            return {"ok": True, "runner_state": state}, None
        if action == "quiz/answer":
            sid, qid, choice = payload.get("session_id"), payload.get("question_id"), payload.get("selected_option_index")
            if not (is_sqlite_integer(sid, minimum=1) and is_sqlite_integer(qid, minimum=1)
                    and (is_sqlite_integer(choice) or type(choice) is int and choice == -1)):
                raise AuthError("invalid_payload")
            result = answer_quiz(conn, actor_user_id=actor, session_id=sid, question_id=qid, selected_option_index=choice)
            if result["submission_status"] == "forbidden":
                raise AuthError("forbidden", 403)
            result["homework_outcome"] = homework.outcome_for_session(conn, actor_user_id=actor, session_id=sid)
            return result, None
        raise AuthError("not_found", 404)


def install_web_api(app, auth: WebAuth) -> None:
    configure_noisy_http_client_loggers()
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, WebAccessLogFilter) for item in access.filters):
        access.addFilter(WebAccessLogFilter())

    google = OwnerGoogleOAuth(auth)

    def google_failure(status):
        # Fixed copy and configured same-origin link: never render provider
        # errors, query parameters, credentials or exception messages.
        home = escape(auth.settings.origin + "/", quote=True)
        return HTMLResponse(
            '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Вход через Google — PsychologyAtlas</title></head><body><main>'
            '<h1>Не удалось войти через Google</h1>'
            '<p>Вернитесь в приложение и попробуйте ещё раз. '
            'Вы также можете войти с помощью пароля.</p>'
            f'<p><a href="{home}">Вернуться в приложение</a></p>'
            '</main></body></html>', status_code=status)

    @app.get("/web/auth/google/callback")
    async def google_callback(request: Request):
        try:
            params = request.query_params
            if len(request.url.query) > 8192 or any(len(params.getlist(key)) != 1 for key in params):
                raise AuthError("invalid_oauth_state", 401)
            cookie = await asyncio.to_thread(google.complete, params.get("state"),
                request.cookies.get(google.cookie_name), params.get("code"))
            response = RedirectResponse(auth.settings.origin + "/", status_code=303)
            if cookie:
                response.set_cookie(auth.settings.cookie_name, cookie, max_age=SESSION_TTL,
                    secure=auth.settings.secure_cookie, httponly=True, samesite="strict", path="/")
        except AuthError as exc:
            response = google_failure(exc.status)
        except OPERATIONAL_ERRORS:
            response = google_failure(503)
        except Exception as exc:
            logger.error("web_oauth_failure type=%s", type(exc).__name__)
            response = google_failure(500)
        response.delete_cookie(google.cookie_name, path="/", secure=auth.settings.secure_cookie, httponly=True, samesite="lax")
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"})
        return response

    @app.api_route("/web/{action:path}", methods=["GET", "POST", "OPTIONS", "PUT", "DELETE", "PATCH"])
    async def web_endpoint(action: str, request: Request):
        cookie = None
        oauth_cookie = None
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
                try:
                    body = await read_request_body(request.stream())
                except RequestBodyTooLarge:
                    raise AuthError("body_too_large", 413) from None
                try:
                    payload = json.loads(body)
                except (ValueError, UnicodeError, RecursionError):
                    raise AuthError("invalid_json") from None
                if not isinstance(payload, dict):
                    raise AuthError("invalid_payload")
            if action == "auth/google/begin":
                result, oauth_cookie = await asyncio.to_thread(google.begin, payload.get("purpose"),
                    request.cookies.get(auth.settings.cookie_name), request.headers.get("x-csrf-token"))
            else:
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
        if oauth_cookie is not None:
            response.set_cookie(google.cookie_name, oauth_cookie, max_age=OAUTH_TTL,
                secure=auth.settings.secure_cookie, httponly=True, samesite="lax", path="/")
        if cookie is not None:
            response.set_cookie(auth.settings.cookie_name, cookie, max_age=SESSION_TTL if cookie else 0,
                                secure=auth.settings.secure_cookie, httponly=True, samesite="strict", path="/")
        response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff",
                                 "Referrer-Policy": "no-referrer", "Vary": "Cookie, Origin"})
        logger.info("web_api action=%s status=%s", action if action in GET_ACTIONS | POST_ACTIONS else "unknown", response.status_code)
        return response
