"""Compatibility imports for existing Telegram entrypoints and consumers."""
from app.quiz_runner import (
    AnswerSubmissionResult as MiniAppAnswerSubmissionResult,
    QuestionSnapshotResult as MiniAppQuestionSnapshotResult,
    SnapshotStatus,
    SubmissionStatus,
    build_runner_state as build_miniapp_runner_state,
    get_current_question_snapshot as get_current_miniapp_question_snapshot,
    submit_answer_event as submit_miniapp_answer_event,
)
