"""Shared quiz state and answer transitions for verified internal actors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.db import (
    get_answered_questions_count,
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

SnapshotStatus = Literal["ok", "session_not_found", "forbidden", "session_not_in_progress", "no_current_question"]


@dataclass(frozen=True)
class AnswerSubmissionResult:
    status: SubmissionStatus
    session_id: int
    expected_question_id: int | None = None
    selected_option_index: int | None = None
    is_correct: bool | None = None
    resolved_question_id: int | None = None


@dataclass(frozen=True)
class QuestionSnapshotResult:
    status: SnapshotStatus
    session_id: int | None = None
    session_status: str | None = None
    question_id: int | None = None
    question_text: str | None = None
    order_index: int | None = None
    total_questions: int | None = None
    options: tuple[dict[str, int | str], ...] = ()


def get_current_question_snapshot(
    conn,
    *,
    actor_user_id: int,
    session_id: int | None = None,
) -> QuestionSnapshotResult:
    resolved_session_id = session_id
    if resolved_session_id is None:
        latest = conn.execute(
            """
            SELECT id
            FROM quiz_sessions
            WHERE user_id = ? AND status = 'in_progress'
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (actor_user_id,),
        ).fetchone()
        if latest is None:
            return QuestionSnapshotResult(status="session_not_found")
        resolved_session_id = int(latest["id"])

    session = get_quiz_session(conn, resolved_session_id)
    if session is None:
        return QuestionSnapshotResult(status="session_not_found", session_id=resolved_session_id)
    if int(session["user_id"]) != actor_user_id:
        return QuestionSnapshotResult(status="forbidden", session_id=resolved_session_id)
    if str(session["status"]) != "in_progress":
        return QuestionSnapshotResult(
            status="session_not_in_progress",
            session_id=resolved_session_id,
            session_status=str(session["status"]),
        )

    current = get_current_unanswered_question(conn, resolved_session_id)
    if current is None:
        return QuestionSnapshotResult(
            status="no_current_question",
            session_id=resolved_session_id,
            session_status="in_progress",
        )

    question_id = int(current["question_id"])
    options = tuple(
        {
            "option_index": int(opt["option_index"]),
            "option_text": str(opt["option_text"]),
        }
        for opt in get_question_options(conn, question_id, session_id=resolved_session_id)
    )
    return QuestionSnapshotResult(
        status="ok",
        session_id=resolved_session_id,
        session_status="in_progress",
        question_id=question_id,
        question_text=str(current["question_text"]),
        order_index=int(current["order_index"]),
        total_questions=int(current["total_questions"]),
        options=options,
    )


def submit_answer_event(
    conn,
    *,
    session_id: int,
    actor_user_id: int,
    question_id: int,
    selected_option_index: int,
) -> AnswerSubmissionResult:
    # Serialize answer writers before reading current state (including other clients).
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    session = get_quiz_session(conn, session_id)
    if session is None:
        return AnswerSubmissionResult(status="session_not_found", session_id=session_id)

    if int(session["user_id"]) != actor_user_id:
        return AnswerSubmissionResult(status="forbidden", session_id=session_id)

    if not is_question_in_session(conn, session_id, question_id):
        return AnswerSubmissionResult(status="invalid_question", session_id=session_id)

    if str(session["status"]) not in {"in_progress", "finished"}:
        return AnswerSubmissionResult(status="session_not_found", session_id=session_id)
    saved = conn.execute(
        "SELECT selected_option_index,is_correct FROM quiz_answers WHERE session_id=? AND question_id=?",
        (session_id, question_id),
    ).fetchone()
    if saved is not None:
        # Even a conflicting retry returns the original recorded outcome, never
        # the newly submitted choice paired with the old choice's correctness.
        return AnswerSubmissionResult(
            status="duplicate", session_id=session_id,
            selected_option_index=saved["selected_option_index"],
            is_correct=bool(saved["is_correct"]), resolved_question_id=question_id,
        )
    if str(session["status"]) != "in_progress":
        return AnswerSubmissionResult(status="session_not_found", session_id=session_id)
    current = get_current_unanswered_question(conn, session_id)
    if current is None:
        return AnswerSubmissionResult(status="stale_question", session_id=session_id)

    expected_question_id = int(current["question_id"])
    if expected_question_id != question_id:
        return AnswerSubmissionResult(
            status="stale_question",
            session_id=session_id,
            expected_question_id=expected_question_id,
        )

    allowed_options = {int(opt["option_index"]) for opt in get_question_options(conn, question_id, session_id=session_id)}
    if selected_option_index not in allowed_options:
        return AnswerSubmissionResult(
            status="invalid_option",
            session_id=session_id,
            expected_question_id=expected_question_id,
            selected_option_index=selected_option_index,
        )

    answer = save_quiz_answer(conn, session_id, question_id, selected_option_index)
    return AnswerSubmissionResult(
        status="duplicate" if int(answer["already_answered"]) == 1 else "accepted",
        session_id=session_id,
        expected_question_id=expected_question_id,
        selected_option_index=selected_option_index,
        is_correct=bool(int(answer["is_correct"])),
        resolved_question_id=question_id,
    )



def build_runner_state(conn, *, actor_user_id: int, session_id: int | None = None) -> dict:
    resolved_session_id = session_id
    if resolved_session_id is None:
        latest_in_progress = conn.execute(
            """
            SELECT id
            FROM quiz_sessions
            WHERE user_id = ? AND status = 'in_progress'
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            (actor_user_id,),
        ).fetchone()
        if latest_in_progress is not None:
            resolved_session_id = int(latest_in_progress["id"])
        else:
            latest_finished = conn.execute(
                """
                SELECT id
                FROM quiz_sessions
                WHERE user_id = ? AND status = 'finished'
                ORDER BY finished_at DESC, started_at DESC, id DESC
                LIMIT 1
                """,
                (actor_user_id,),
            ).fetchone()
            if latest_finished is not None:
                resolved_session_id = int(latest_finished["id"])

    snapshot = get_current_question_snapshot(
        conn,
        actor_user_id=actor_user_id,
        session_id=resolved_session_id,
    )

    if snapshot.status == "session_not_found":
        return {
            "state": "setup",
            "status": "session_not_found",
            "server_derived": True,
            "session": None,
        }

    if snapshot.status == "forbidden":
        return {
            "state": "forbidden",
            "status": "forbidden",
            "server_derived": True,
            "session": {"session_id": snapshot.session_id} if snapshot.session_id else None,
        }

    if snapshot.status == "session_not_in_progress":
        session = get_quiz_session(conn, int(snapshot.session_id)) if snapshot.session_id else None
        if session is None:
            return {
                "state": "setup",
                "status": "session_not_found",
                "server_derived": True,
                "session": None,
            }
        if str(session["status"]) == "finished":
            score = int(session["score"] or 0)
            total_questions = int(session["total_questions"] or 0)
            percent = int((score * 100) / total_questions) if total_questions > 0 else 0
            return {
                "state": "completed",
                "status": "finished",
                "server_derived": True,
                "session": {"session_id": int(session["id"]), "session_status": "finished"},
                "result": {
                    "score": score,
                    "total_questions": total_questions,
                    "percent": percent,
                    "summary": f"{score}/{total_questions} ({percent}%)",
                    "completion_state": "completed",
                },
            }
        return {
            "state": "setup",
            "status": "session_not_in_progress",
            "server_derived": True,
            "session": {"session_id": int(session["id"]), "session_status": str(session["status"])},
        }

    if snapshot.status == "no_current_question":
        answered = get_answered_questions_count(conn, int(snapshot.session_id)) if snapshot.session_id else 0
        return {
            "state": "in_progress",
            "status": "no_current_question",
            "server_derived": True,
            "session": {"session_id": snapshot.session_id, "session_status": "in_progress"},
            "progress": {
                "current_question_number": None,
                "total_questions": answered,
                "answered_count": answered,
                "remaining_count": 0,
                "session_status": "in_progress",
                "server_derived": True,
            },
        }

    answered = get_answered_questions_count(conn, int(snapshot.session_id))
    total_questions = int(snapshot.total_questions or 0)
    current_number = int(snapshot.order_index or answered + 1)
    remaining = max(total_questions - answered, 0)
    return {
        "state": "in_progress",
        "status": "ok",
        "server_derived": True,
        "session": {"session_id": snapshot.session_id, "session_status": "in_progress"},
        "progress": {
            "current_question_number": current_number,
            "total_questions": total_questions,
            "answered_count": answered,
            "remaining_count": remaining,
            "session_status": "in_progress",
            "server_derived": True,
        },
        "current_question": {
            "session_id": snapshot.session_id,
            "question_id": snapshot.question_id,
            "question_text": snapshot.question_text,
            "order_index": snapshot.order_index,
            "total_questions": snapshot.total_questions,
            "status": snapshot.status,
            "session_status": snapshot.session_status,
            "options": list(snapshot.options),
        },
    }
