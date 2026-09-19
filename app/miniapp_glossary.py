from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
import random
import secrets
from threading import RLock
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
    questions: dict[int, Any] = field(default_factory=dict)
    answers: dict[int, tuple[int, dict]] = field(default_factory=dict)
    advances: dict[int, dict] = field(default_factory=dict)
    restarted_state: dict | None = None
    lock: Any = field(default_factory=RLock, repr=False)


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
    step_id = session.current_index + 1
    question = session.questions.get(step_id)
    if question is None:
        question = build_glossary_quiz_question(session.entries, session.entries[session.current_index])
    if question is None:
        return None
    session.questions[step_id] = question
    return {
        "session_id": session.session_id,
        "step_id": step_id,
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
    question = _safe_question(session)
    if question is None:
        return None
    _SESSIONS[session_id] = session
    return {"state": "in_progress", "current_question": question}


def get_session(session_id: str, telegram_user_id: int) -> MiniAppGlossarySession | None:
    if not isinstance(session_id, str):
        return None
    session = _SESSIONS.get(session_id)
    if session is None or session.owner_telegram_user_id != telegram_user_id:
        return None
    return session


def answer_glossary_session(telegram_user_id: int, session_id: str, selected_option_index: int, step_id: int) -> dict[str, Any] | None:
    session = get_session(session_id, telegram_user_id)
    if session is None or type(step_id) is not int or type(selected_option_index) is not int:
        return None
    with session.lock:
        if step_id in session.answers:
            selected, feedback = session.answers[step_id]
            return deepcopy(feedback) if selected == selected_option_index else None
        if session.current_index >= len(session.entries) or step_id != session.current_index + 1:
            return None
        question = session.questions.get(step_id)
        if question is None or selected_option_index not in range(len(question.options)):
            return None
        correct = question.correct_option_index
        is_correct = selected_option_index == correct
        session.score += int(is_correct)
        session.answered_current = True
        state = {
            "state": "feedback",
            "feedback": {
                "step_id": step_id,
                "is_correct": is_correct,
                "selected_option_index": selected_option_index,
                "selected_option_text": question.options[selected_option_index],
                "correct_option_index": correct,
                "correct_option_text": question.options[correct],
                "explanation": question.entry.definition,
                "answered_count": step_id,
                "total_questions": len(session.entries),
                "has_next": step_id < len(session.entries),
            },
        }
        session.answers[step_id] = (selected_option_index, state)
        return deepcopy(state)


def next_glossary_session(telegram_user_id: int, session_id: str, step_id: int) -> dict[str, Any] | None:
    session = get_session(session_id, telegram_user_id)
    if session is None or type(step_id) is not int:
        return None
    with session.lock:
        if step_id in session.advances:
            return deepcopy(session.advances[step_id])
        if step_id != session.current_index + 1 or step_id > len(session.entries):
            return None
        if not session.answered_current:
            # Reading the current step must not reshuffle it or consume a future next.
            return {"state": "in_progress", "current_question": _safe_question(session)}
        session.current_index += 1
        session.answered_current = False
        if session.current_index >= len(session.entries):
            state = {"state": "completed", "result": {"score": session.score, "total_questions": len(session.entries)}}
        else:
            state = {"state": "in_progress", "current_question": _safe_question(session)}
        session.advances[step_id] = state
        return deepcopy(state)


def restart_glossary_session(telegram_user_id: int, session_id: str) -> dict[str, Any] | None:
    session = get_session(session_id, telegram_user_id)
    if session is None:
        return None
    with session.lock:
        if session.restarted_state is None:
            session.restarted_state = start_glossary_session(telegram_user_id, session.topic_id, len(session.entries))
        return deepcopy(session.restarted_state)
