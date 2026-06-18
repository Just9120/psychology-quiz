from __future__ import annotations

from dataclasses import dataclass
import random
import secrets
from typing import Any

from app.glossary import GLOSSARY_TOPICS, build_glossary_quiz_question, load_glossary_entries


@dataclass
class MiniAppGlossarySession:
    session_id: str
    owner_telegram_user_id: int
    topic_id: str
    topic_title: str
    entries: list
    current_index: int = 0
    score: int = 0
    answered_current: bool = False


_SESSIONS: dict[str, MiniAppGlossarySession] = {}


def list_glossary_topics_payload() -> dict[str, Any]:
    topics = []
    for topic_id, title in GLOSSARY_TOPICS:
        entries = load_glossary_entries(topic_id) or []
        topics.append({"topic_id": topic_id, "title": title, "available_count": len(entries)})
    return {"topics": topics, "question_count_choices": [5, 10, "all"]}


def _safe_question(session: MiniAppGlossarySession) -> dict[str, Any] | None:
    if session.current_index >= len(session.entries):
        return None
    question = build_glossary_quiz_question(session.entries, session.entries[session.current_index])
    if question is None:
        return None
    # Store the generated option order on the session entry slot without exposing entry ids.
    setattr(session, "current_options", list(question.options))
    setattr(session, "current_correct_index", int(question.correct_option_index))
    setattr(session, "current_definition", question.entry.definition)
    return {
        "session_id": session.session_id,
        "topic_id": session.topic_id,
        "topic_title": session.topic_title,
        "order_index": session.current_index + 1,
        "total_questions": len(session.entries),
        "term": question.entry.term,
        "options": [{"option_index": index, "option_text": text} for index, text in enumerate(question.options)],
    }


def start_glossary_session(telegram_user_id: int, topic_id: str, count: int | str | None) -> dict[str, Any] | None:
    topic_map = dict(GLOSSARY_TOPICS)
    if topic_id not in topic_map:
        return None
    entries = load_glossary_entries(topic_id)
    if not entries or len(entries) < 4:
        return None
    limit = len(entries) if count in (None, "all") else int(count) if isinstance(count, int) else 0
    if limit not in {5, 10, len(entries)}:
        return None
    selected = random.sample(entries, min(limit, len(entries)))
    session_id = secrets.token_urlsafe(16)
    session = MiniAppGlossarySession(session_id, telegram_user_id, topic_id, topic_map[topic_id], selected)
    _SESSIONS[session_id] = session
    return {"state": "in_progress", "current_question": _safe_question(session)}


def get_session(session_id: str, telegram_user_id: int) -> MiniAppGlossarySession | None:
    session = _SESSIONS.get(session_id)
    if session is None or session.owner_telegram_user_id != telegram_user_id:
        return None
    return session


def answer_glossary_session(telegram_user_id: int, session_id: str, selected_option_index: int) -> dict[str, Any] | None:
    session = get_session(session_id, telegram_user_id)
    if session is None or session.current_index >= len(session.entries) or session.answered_current:
        return None
    options = getattr(session, "current_options", None)
    correct = getattr(session, "current_correct_index", None)
    definition = getattr(session, "current_definition", "")
    if not isinstance(options, list) or not isinstance(correct, int) or selected_option_index not in range(len(options)):
        return None
    is_correct = selected_option_index == correct
    if is_correct:
        session.score += 1
    session.answered_current = True
    return {
        "state": "feedback",
        "feedback": {
            "is_correct": is_correct,
            "selected_option_index": selected_option_index,
            "selected_option_text": options[selected_option_index],
            "correct_option_index": correct,
            "correct_option_text": options[correct],
            "explanation": definition,
            "answered_count": session.current_index + 1,
            "total_questions": len(session.entries),
            "has_next": session.current_index + 1 < len(session.entries),
        },
    }


def next_glossary_session(telegram_user_id: int, session_id: str) -> dict[str, Any] | None:
    session = get_session(session_id, telegram_user_id)
    if session is None:
        return None
    if session.answered_current:
        session.current_index += 1
        session.answered_current = False
    if session.current_index >= len(session.entries):
        return {"state": "completed", "result": {"score": session.score, "total_questions": len(session.entries)}}
    return {"state": "in_progress", "current_question": _safe_question(session)}


def restart_glossary_session(telegram_user_id: int, session_id: str) -> dict[str, Any] | None:
    session = get_session(session_id, telegram_user_id)
    if session is None:
        return None
    return start_glossary_session(telegram_user_id, session.topic_id, len(session.entries))
