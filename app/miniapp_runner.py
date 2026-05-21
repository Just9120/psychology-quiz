from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.db import (
    get_current_unanswered_question,
    get_question_options,
    get_quiz_session,
    is_question_in_session,
    save_quiz_answer,
)

SubmissionStatus = Literal[
    "accepted",
    "duplicate",
    "stale_question",
    "invalid_option",
    "session_not_found",
    "forbidden",
    "invalid_question",
]


@dataclass(frozen=True)
class MiniAppAnswerSubmissionResult:
    status: SubmissionStatus
    session_id: int
    expected_question_id: int | None = None
    selected_option_index: int | None = None
    is_correct: bool | None = None
    resolved_question_id: int | None = None


# Baseline contract for upcoming Mini App in-app runner slices.
# TODO(next slices): extend return payload with authoritative next-question/completed state.
def submit_miniapp_answer_event(
    conn,
    *,
    session_id: int,
    actor_user_id: int,
    question_id: int,
    selected_option_index: int,
) -> MiniAppAnswerSubmissionResult:
    session = get_quiz_session(conn, session_id)
    if session is None or str(session["status"]) != "in_progress":
        return MiniAppAnswerSubmissionResult(status="session_not_found", session_id=session_id)

    if int(session["user_id"]) != actor_user_id:
        return MiniAppAnswerSubmissionResult(status="forbidden", session_id=session_id)

    if not is_question_in_session(conn, session_id, question_id):
        return MiniAppAnswerSubmissionResult(status="invalid_question", session_id=session_id)

    current = get_current_unanswered_question(conn, session_id)
    if current is None:
        return MiniAppAnswerSubmissionResult(status="stale_question", session_id=session_id)

    expected_question_id = int(current["question_id"])
    if expected_question_id != question_id:
        return MiniAppAnswerSubmissionResult(
            status="stale_question",
            session_id=session_id,
            expected_question_id=expected_question_id,
        )

    allowed_options = {int(opt["option_index"]) for opt in get_question_options(conn, question_id)}
    if selected_option_index not in allowed_options:
        return MiniAppAnswerSubmissionResult(
            status="invalid_option",
            session_id=session_id,
            expected_question_id=expected_question_id,
            selected_option_index=selected_option_index,
        )

    answer = save_quiz_answer(conn, session_id, question_id, selected_option_index)
    return MiniAppAnswerSubmissionResult(
        status="duplicate" if int(answer["already_answered"]) == 1 else "accepted",
        session_id=session_id,
        expected_question_id=expected_question_id,
        selected_option_index=selected_option_index,
        is_correct=bool(int(answer["is_correct"])),
        resolved_question_id=question_id,
    )
