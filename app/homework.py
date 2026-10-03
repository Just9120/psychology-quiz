"""Reviewed homework tests backed by the shared question bank and quiz attempts.

The catalog contains only learner-facing derivatives. Source documents and
editorial locators remain outside the serving repository and API responses.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re

from app.curriculum import load_catalog as load_curriculum
from app.database import is_postgres
from app.quiz_service import PreparedQuiz, QuizSetupError, start_confirmed_quiz

CATALOG_PATH = Path(__file__).resolve().parents[1] / "content" / "homework.json"
PASS_NUMERATOR = 4
PASS_DENOMINATOR = 5


class HomeworkError(ValueError):
    pass


def passed(score: int, total: int) -> bool:
    return total > 0 and score * PASS_DENOMINATOR >= total * PASS_NUMERATOR


@lru_cache(maxsize=1)
def load_catalog() -> tuple[dict, ...]:
    document = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Invalid homework catalog")
    assignments = document.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        raise ValueError("Empty homework catalog")
    curriculum = load_curriculum()
    seen = set()
    for item in assignments:
        if not isinstance(item, dict) or set(item) != {
                "id", "title", "module", "discipline_id", "topic_id", "description", "question_ids"}:
            raise ValueError("Invalid homework assignment")
        key = item["id"]
        if not isinstance(key, str) or re.fullmatch(r"[a-z][a-z0-9_]{2,48}", key) is None or key in seen:
            raise ValueError("Invalid homework identity")
        seen.add(key)
        topic = curriculum["topics"].get(item["topic_id"])
        if topic is None or topic["discipline_id"] != item["discipline_id"]:
            raise ValueError("Invalid homework classification")
        for field in ("title", "module", "description"):
            if not isinstance(item[field], str) or not item[field].strip() or len(item[field]) > 300:
                raise ValueError("Invalid homework text")
        discipline = curriculum["disciplines"][item["discipline_id"]]
        modules = discipline.get("modules", [discipline.get("module")])
        allowed_labels = {module.replace("module", "Модуль ") for module in modules
                          if isinstance(module, str) and module}
        if not allowed_labels and discipline.get("modules") == [] and discipline.get("module") is None:
            allowed_labels = {"Другое"}
        if item["module"] not in allowed_labels:
            raise ValueError("Homework module does not match curriculum")
        questions = item["question_ids"]
        if not isinstance(questions, list) or len(questions) < 5 or len(set(questions)) != len(questions):
            raise ValueError("Invalid homework question set")
        if any(not isinstance(question, str) or not re.fullmatch(r"[a-z0-9_]+", question)
               for question in questions):
            raise ValueError("Invalid homework question identity")
    return tuple(assignments)


def validate_bank(conn) -> None:
    """Publication gate: a test never starts with missing or retired content."""
    for item in load_catalog():
        rows = conn.execute(
            f"SELECT external_id,status,question_text,explanation FROM questions WHERE external_id IN "
            f"({','.join('?' for _ in item['question_ids'])})", item["question_ids"]
        ).fetchall()
        found = {row[0]: row for row in rows}
        if set(found) != set(item["question_ids"]):
            raise ValueError("Homework question missing")
        for row in found.values():
            if row[1] != "approved" or not row[2] or not row[3]:
                raise ValueError("Homework question is not publishable")
            correct = conn.execute("SELECT COUNT(*) FROM question_options WHERE question_id="
                                   "(SELECT id FROM questions WHERE external_id=?) AND is_correct=1",
                                   (row[0],)).fetchone()[0]
            if correct != 1:
                raise ValueError("Homework question must have one correct answer")


def catalog_for_actor(conn, actor_user_id: int) -> dict:
    rows = conn.execute("""SELECT h.assignment_id,s.id,s.status,s.score,s.total_questions
        FROM homework_attempts h JOIN quiz_sessions s ON s.id=h.session_id
        WHERE s.user_id=? ORDER BY s.id DESC""", (actor_user_id,)).fetchall()
    by_assignment: dict[str, list] = {}
    for row in rows:
        by_assignment.setdefault(row[0], []).append(row)
    curriculum = load_curriculum()
    output = []
    for item in load_catalog():
        attempts = by_assignment.get(item["id"], [])
        finished = [row for row in attempts if row[2] == "finished" and row[4] > 0]
        best = max(finished, key=lambda row: row[3] * 100 / row[4]) if finished else None
        completed = any(passed(int(row[3]), int(row[4])) for row in finished)
        active = next((row for row in attempts if row[2] == "in_progress"), None)
        output.append({"id": item["id"], "title": item["title"], "module": item["module"],
                       "discipline": curriculum["disciplines"][item["discipline_id"]]["title"],
                       "topic": curriculum["topics"][item["topic_id"]]["title"],
                       "description": item["description"], "question_count": len(item["question_ids"]),
                       "completed": completed, "finished_attempts": len(finished),
                       "best_score": int(best[3]) if best else None,
                       "best_total": int(best[4]) if best else None,
                       "active_session_id": int(active[1]) if active else None})
    return {"ok": True, "assignments": output}


def start_homework(conn, *, actor_user_id: int, assignment_id: str, payload: dict) -> dict:
    if not isinstance(assignment_id, str):
        raise HomeworkError("invalid_homework")
    assignment = next((item for item in load_catalog() if item["id"] == assignment_id), None)
    if assignment is None:
        raise HomeworkError("homework_unavailable")
    question_ids = assignment["question_ids"]
    rows = conn.execute(
        f"SELECT id,external_id,status,explanation FROM questions WHERE external_id IN "
        f"({','.join('?' for _ in question_ids)})", question_ids
    ).fetchall()
    by_id = {row[1]: row for row in rows}
    if any(qid not in by_id or by_id[qid][2] != "approved" or not by_id[qid][3]
           for qid in question_ids):
        raise HomeworkError("homework_unavailable")
    prepared = PreparedQuiz(None, (), None, tuple(int(by_id[qid][0]) for qid in question_ids))
    try:
        state = start_confirmed_quiz(conn, actor_user_id=actor_user_id, prepared=prepared, payload=payload)
    except QuizSetupError as exc:
        raise HomeworkError(str(exc)) from None
    session_id = int(state["session"]["session_id"])
    conn.execute("INSERT INTO homework_attempts(session_id,assignment_id) VALUES(?,?)",
                 (session_id, assignment_id))
    return {"ok": True, "assignment_id": assignment_id, "runner_state": state}


def outcome_for_session(conn, *, actor_user_id: int, session_id: int) -> dict | None:
    # Older isolated quiz fixtures use the base SQLite schema without optional
    # homework migration. A regular quiz remains valid in those databases.
    if not is_postgres(conn) and conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='homework_attempts'"
    ).fetchone() is None:
        return None
    row = conn.execute("""SELECT h.assignment_id,s.status,s.score,s.total_questions
        FROM homework_attempts h JOIN quiz_sessions s ON s.id=h.session_id
        WHERE s.id=? AND s.user_id=?""", (session_id, actor_user_id)).fetchone()
    if row is None:
        return None
    complete = row[1] == "finished" and row[3] > 0
    return {"assignment_id": row[0], "attempt_finished": complete,
            "passed": bool(complete and passed(int(row[2]), int(row[3]))),
            "score": int(row[2]), "total_questions": int(row[3])}
