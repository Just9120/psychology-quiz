from __future__ import annotations

import base64
import json
import urllib.parse

from app.miniapp_glossary import list_glossary_topics_payload


MAX_MINIAPP_URL_LENGTH = 1800
MINIAPP_FRONTEND_VERSION = "ui-polish-v2"


def _safe_miniapp_glossary_context() -> dict:
    return list_glossary_topics_payload()


def build_miniapp_setup_context(categories, question_snapshot: dict | None = None, runner_state: dict | None = None) -> dict:
    context = {
        "type": "miniapp_setup_context",
        "version": 1,
        "frontend_version": MINIAPP_FRONTEND_VERSION,
        "categories": [{"id": int(row["id"]), "name": str(row["name"])} for row in categories],
        "mode": "setup",
        "glossary": _safe_miniapp_glossary_context(),
    }
    if question_snapshot is not None:
        context["current_question_snapshot"] = question_snapshot
    if runner_state is not None:
        context["runner_state"] = runner_state
    return context


def _build_compact_runner_progress_state(runner_state: dict | None) -> dict | None:
    if not isinstance(runner_state, dict):
        return None
    compact: dict = {
        "state": runner_state.get("state"),
        "status": runner_state.get("status"),
        "server_derived": bool(runner_state.get("server_derived")),
        "compact_progress_only": True,
    }
    if isinstance(runner_state.get("session"), dict):
        compact["session"] = {
            "session_id": runner_state["session"].get("session_id"),
            "session_status": runner_state["session"].get("session_status"),
        }
    if isinstance(runner_state.get("progress"), dict):
        compact["progress"] = {
            "current_question_number": runner_state["progress"].get("current_question_number"),
            "total_questions": runner_state["progress"].get("total_questions"),
            "answered_count": runner_state["progress"].get("answered_count"),
            "remaining_count": runner_state["progress"].get("remaining_count"),
            "session_status": runner_state["progress"].get("session_status"),
            "server_derived": bool(runner_state["progress"].get("server_derived")),
        }
    return compact


def _build_compact_runner_question_payload(runner_state: dict | None) -> dict | None:
    if not isinstance(runner_state, dict) or runner_state.get("state") != "in_progress":
        return None
    current_question = runner_state.get("current_question")
    session = runner_state.get("session")
    progress = runner_state.get("progress")
    if not isinstance(current_question, dict) or not isinstance(session, dict):
        return None
    options = []
    for option in current_question.get("options", []):
        if not isinstance(option, dict):
            continue
        option_index = option.get("option_index")
        option_text = option.get("option_text")
        if isinstance(option_index, int) and isinstance(option_text, str):
            options.append([option_index, option_text])
    payload = {
        "m": "runner",
        "s": session.get("session_id"),
        "q": current_question.get("question_id"),
        "qt": current_question.get("question_text"),
        "o": options,
        "sd": True,
    }
    if isinstance(progress, dict):
        payload["n"] = progress.get("current_question_number")
        payload["t"] = progress.get("total_questions")
        payload["a"] = progress.get("answered_count")
        payload["r"] = progress.get("remaining_count")
    return payload


def _build_miniapp_context(
    categories,
    runner_state: dict | None,
    *,
    mode: str,
    compact: bool = False,
    abandons_active_session: bool = False,
    api_base_url: str | None = None,
) -> dict:
    selected_state = _build_compact_runner_progress_state(runner_state) if compact else runner_state
    include_categories = mode == "setup" and not compact
    context = {
        "type": "miniapp_setup_context",
        "version": 1,
        "frontend_version": MINIAPP_FRONTEND_VERSION,
        "mode": mode,
        "categories": [{"id": int(row["id"]), "name": str(row["name"])} for row in categories] if include_categories else [],
    }
    if mode == "setup" and compact:
        context["setup_hydration_required"] = True
    elif mode == "setup":
        context["glossary"] = _safe_miniapp_glossary_context()
    if selected_state is not None:
        context["runner_state"] = selected_state
    if api_base_url:
        context["api_base_url"] = api_base_url
    if mode == "setup" and abandons_active_session:
        context["force_setup"] = True
        context["abandons_active_session"] = True
    return context


def _with_completed_setup_url_if_fit(
    base_url: str,
    context: dict,
    categories,
    *,
    api_base_url: str | None = None,
) -> dict:
    if context.get("mode") != "completed":
        return context

    setup_context = _build_miniapp_context(categories, None, mode="setup", compact=bool(api_base_url), api_base_url=api_base_url)
    setup_url = build_miniapp_url(base_url, setup_context)
    context_with_setup = dict(context)
    context_with_setup["setup_url"] = setup_url
    if len(build_miniapp_url(base_url, context_with_setup)) <= MAX_MINIAPP_URL_LENGTH:
        return context_with_setup
    return context


def build_miniapp_url_with_fallback(
    base_url: str,
    categories,
    runner_state: dict | None,
    *,
    abandons_active_session: bool = False,
    api_base_url: str | None = None,
) -> tuple[str | None, bool]:
    has_runner = isinstance(runner_state, dict) and runner_state.get("state") in {"in_progress", "completed"}
    preferred_mode = "setup"
    if has_runner:
        preferred_mode = "completed" if runner_state.get("state") == "completed" else "runner"

    if preferred_mode == "runner":
        compact_question_context = {
            "type": "miniapp_setup_context",
            "version": 1,
            "frontend_version": MINIAPP_FRONTEND_VERSION,
            "mode": "runner",
            "categories": [],
            "runner_q": _build_compact_runner_question_payload(runner_state),
        }
        if api_base_url:
            compact_question_context["api_base_url"] = api_base_url
        compact_question_url = build_miniapp_url(base_url, compact_question_context)
        if len(compact_question_url) <= MAX_MINIAPP_URL_LENGTH:
            return compact_question_url, False

        compact_context = _build_miniapp_context(
            categories,
            runner_state,
            mode=preferred_mode,
            compact=True,
            api_base_url=api_base_url,
        )
        compact_url = build_miniapp_url(base_url, compact_context)
        if len(compact_url) <= MAX_MINIAPP_URL_LENGTH:
            return compact_url, True
        return None, False

    setup_requires_api_hydration = preferred_mode == "setup" and bool(api_base_url)
    primary_context = _build_miniapp_context(
        categories,
        runner_state,
        mode=preferred_mode,
        compact=setup_requires_api_hydration,
        abandons_active_session=abandons_active_session,
        api_base_url=api_base_url,
    )
    primary_context = _with_completed_setup_url_if_fit(
        base_url,
        primary_context,
        categories,
        api_base_url=api_base_url,
    )
    primary_url = build_miniapp_url(base_url, primary_context)
    if len(primary_url) <= MAX_MINIAPP_URL_LENGTH:
        return primary_url, False

    compact_context = _build_miniapp_context(
        categories,
        runner_state,
        mode=preferred_mode,
        compact=True,
        abandons_active_session=abandons_active_session,
        api_base_url=api_base_url,
    )
    compact_context = _with_completed_setup_url_if_fit(
        base_url,
        compact_context,
        categories,
        api_base_url=api_base_url,
    )
    compact_url = build_miniapp_url(base_url, compact_context)
    if len(compact_url) <= MAX_MINIAPP_URL_LENGTH:
        return compact_url, True

    return None, False


def build_miniapp_setup_entrypoint_url(
    base_url: str,
    categories,
    *,
    abandons_active_session: bool = False,
    api_base_url: str | None = None,
) -> tuple[str | None, bool]:
    setup_state = {"state": "setup", "status": "entrypoint", "server_derived": True}
    return build_miniapp_url_with_fallback(
        base_url,
        categories,
        setup_state,
        abandons_active_session=abandons_active_session,
        api_base_url=api_base_url,
    )


def encode_miniapp_setup_context(context: dict) -> str:
    context_json = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    context_bytes = context_json.encode("utf-8")
    encoded = base64.urlsafe_b64encode(context_bytes).decode("ascii")
    return encoded.rstrip("=")


def build_miniapp_url(base_url: str, context: dict) -> str:
    encoded_context = encode_miniapp_setup_context(context)
    parsed = urllib.parse.urlsplit(base_url)
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query_params.append(("context", encoded_context))
    new_query = urllib.parse.urlencode(query_params)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))
