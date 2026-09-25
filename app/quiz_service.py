"""Quiz use cases shared by authenticated transport adapters.

actor_user_id is a verified users.id supplied by the adapter, never a client ID.
The caller owns the transaction; commit successful results before replying.
"""
from __future__ import annotations

from app.database import begin_write

from dataclasses import dataclass
from typing import Any
from app.attempt_content import get_attempt_content
from app.payload_validation import valid_quiz_setup
from app.db import (
    abandon_in_progress_sessions_for_user, get_active_categories,
    select_random_approved_question_ids_across_active_categories,
    select_random_approved_question_ids_by_categories,
    select_random_approved_question_ids_by_category, set_selected_categories_for_session,
    start_quiz_session, store_session_questions, finalize_quiz_session,
)
from app.quiz_runner import build_runner_state, submit_answer_event


class QuizSetupError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedQuiz:
    category_id: int | None
    selected_ids: tuple[int, ...]
    difficulty: str | None
    question_ids: tuple[int, ...]


def prepare_quiz(conn, payload: dict) -> PreparedQuiz:
    if not valid_quiz_setup(payload):
        raise QuizSetupError("invalid_setup")
    active_ids = {int(row["id"]) for row in get_active_categories(conn)}
    if not active_ids:
        raise QuizSetupError("no_categories")
    category_ids = payload["category_ids"]
    if any(category_id not in active_ids for category_id in category_ids):
        raise QuizSetupError("invalid_setup")
    mode, count = payload["quiz_mode"], payload["question_count"]
    difficulty = None if payload["difficulty"] == "any" else payload["difficulty"]
    category_id, selected = None, ()
    if mode == "single":
        if len(category_ids) != 1:
            raise QuizSetupError("invalid_setup")
        category_id = category_ids[0]
        questions = select_random_approved_question_ids_by_category(conn, category_id, count, difficulty)
    elif mode == "selected_mix":
        if not category_ids:
            raise QuizSetupError("invalid_setup")
        selected = tuple(category_ids)
        questions = select_random_approved_question_ids_by_categories(conn, list(selected), count, difficulty)
    else:
        questions = select_random_approved_question_ids_across_active_categories(conn, count, difficulty)
    if not questions:
        raise QuizSetupError("no_questions")
    return PreparedQuiz(category_id, selected, difficulty, tuple(questions))


def start_prepared_quiz(conn, *, actor_user_id: int, prepared: PreparedQuiz) -> dict:
    # Serialization starts before abandoning/creating attempts; one active attempt.
    begin_write(conn, f"actor:{actor_user_id}")
    abandon_in_progress_sessions_for_user(conn, actor_user_id)
    session_id = start_quiz_session(conn, actor_user_id, prepared.category_id, difficulty_mode=prepared.difficulty)
    if prepared.selected_ids:
        set_selected_categories_for_session(conn, session_id, list(prepared.selected_ids))
    store_session_questions(conn, session_id, list(prepared.question_ids))
    return build_runner_state(conn, actor_user_id=actor_user_id, session_id=session_id)


def quiz_setup_options(conn) -> dict:
    return {
        "categories": [{"id": int(row["id"]), "name": str(row["name"])} for row in get_active_categories(conn)],
        "question_count_choices": [5, 10, 15, "all"],
        "difficulty_choices": ["any", "easy", "medium", "hard"],
    }


def quiz_state(conn, *, actor_user_id: int) -> dict:
    result = {"ok": True, "runner_state": build_runner_state(conn, actor_user_id=actor_user_id)}
    feedback = build_recent_answer_feedback(conn, actor_user_id=actor_user_id)
    if feedback is not None:
        result["recent_answer_feedback"] = feedback
    return result


def answer_quiz(conn, *, actor_user_id: int, session_id: int, question_id: int, selected_option_index: int) -> dict:
    submission = submit_answer_event(conn, actor_user_id=actor_user_id, session_id=session_id,
                                     question_id=question_id, selected_option_index=selected_option_index)
    result = {"ok": True, "submission_status": submission.status}
    if submission.status in {"accepted", "duplicate"}:
        state = build_runner_state(conn, actor_user_id=actor_user_id, session_id=session_id)
        if state.get("state") == "in_progress" and state.get("status") == "no_current_question":
            finalize_quiz_session(conn, session_id)
            state = build_runner_state(conn, actor_user_id=actor_user_id, session_id=session_id)
        result.update(runner_state=state, feedback=build_answer_feedback(
            conn, session_id, question_id, submission.selected_option_index, bool(submission.is_correct)))
    elif submission.status != "forbidden":
        result["runner_state"] = build_runner_state(conn, actor_user_id=actor_user_id)
    return result


def _find_latest_session_id_for_feedback(conn, actor_user_id: int) -> int | None:
    row = conn.execute(
        """
        SELECT id
        FROM quiz_sessions
        WHERE user_id = ?
          AND status IN ('in_progress', 'finished')
        ORDER BY
          CASE WHEN status = 'in_progress' THEN 0 ELSE 1 END,
          COALESCE(finished_at, started_at) DESC,
          started_at DESC,
          id DESC
        LIMIT 1
        """,
        (actor_user_id,),
    ).fetchone()
    return int(row["id"]) if row is not None else None


def build_recent_answer_feedback(conn, *, actor_user_id: int) -> dict[str, Any] | None:
    session_id = _find_latest_session_id_for_feedback(conn, actor_user_id)
    if session_id is None:
        return None
    row = conn.execute(
        """
        SELECT question_id, selected_option_index, is_correct
        FROM quiz_answers
        WHERE session_id = ?
        ORDER BY answered_at DESC, id DESC
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    question_id = int(row["question_id"])
    selected_option_index = row["selected_option_index"]
    is_correct = bool(int(row["is_correct"]))
    feedback = build_answer_feedback(conn, session_id, question_id, selected_option_index, is_correct)
    feedback["question_id"] = question_id
    return feedback

def build_answer_feedback(conn, session_id: int, question_id: int, selected_option_index: int | None, is_correct: bool) -> dict[str, Any]:
    content = get_attempt_content(conn, session_id, question_id)
    if content is None:
        raise ValueError("Question is not part of this attempt")
    options = content["options"]
    selected = next((opt for opt in options if opt["option_index"] == selected_option_index), None)
    correct = next((opt for opt in options if opt["is_correct"]), None)
    feedback = {
        "selected_option_index": selected_option_index,
        "selected_option_text": selected["option_text"] if selected else None,
        "is_correct": bool(is_correct),
        "correct_option_index": correct["option_index"] if correct else None,
        "correct_option_text": correct["option_text"] if correct else None,
        "explanation": content["explanation"],
        "content_sha256": content["content_sha256"],
        "snapshot_provenance": content["snapshot_provenance"],
    }
    if content.get("kind") == "case":
        feedback["case_review"] = {key: content["case"][key] for key in
                                   ("approach", "conditions", "ambiguity", "option_rationales")}
    return feedback
