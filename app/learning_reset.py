"""Explicit, actor-scoped quiz/glossary reset; caller owns the transaction.

Preview fingerprints the current practice, including unanswered attempts. An
answer/setup/reset serialized on the same actor invalidates that confirmation.
Only learning rows are removed: the bank, identity and literature are untouched.
"""
from collections import defaultdict
import hashlib
import hmac
import json
import re

from app.database import begin_write, timestamp_sql
from app.progress_service import ProgressError


def _scope(payload):
    mode, topic = payload.get("scope"), payload.get("topic")
    if mode not in ("all", "topic") or (mode == "all" and topic is not None):
        raise ProgressError("invalid_reset_scope")
    if mode == "topic" and (not isinstance(topic, str) or not topic or len(topic) > 500):
        raise ProgressError("invalid_reset_scope")
    return mode, topic


def _read(conn, actor, payload):
    mode, topic = _scope(payload)
    begin_write(conn, f"actor:{actor}")
    sessions = conn.execute("SELECT * FROM quiz_sessions WHERE user_id=? ORDER BY id", (actor,)).fetchall()
    questions = conn.execute("""SELECT sq.* FROM quiz_session_questions sq
        JOIN quiz_sessions s ON s.id=sq.session_id WHERE s.user_id=? ORDER BY sq.id""", (actor,)).fetchall()
    answers = conn.execute("""SELECT a.* FROM quiz_answers a
        JOIN quiz_sessions s ON s.id=a.session_id WHERE s.user_id=? ORDER BY a.id""", (actor,)).fetchall()
    topics = {row["id"]: json.loads(row["content_snapshot"])["category"] for row in questions}
    glossary = conn.execute('SELECT * FROM glossary_sessions WHERE user_id=? ORDER BY id', (actor,)).fetchall()
    available = sorted(set(topics.values()) | {row['topic_title'] for row in glossary})
    if mode == "topic" and topic not in available:
        raise ProgressError("reset_changed", 409)
    selected = [row for row in questions if mode == "all" or topics[row["id"]] == topic]
    pairs = {(row["session_id"], row["question_id"]) for row in selected}
    affected = {row["session_id"] for row in selected} if mode == "topic" else {row["id"] for row in sessions}
    selected_glossary = [row for row in glossary if mode == 'all' or row['topic_title'] == topic]
    state = [actor, mode, topic, *[[list(row) for row in rows] for rows in (sessions, questions, answers, glossary)]]
    revision = hashlib.sha256(json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    preview = {"ok": True, "scope": mode, "topic": topic, "topics": available,
               "revision": revision, "questions": len(selected),
               "answers": sum((row["session_id"], row["question_id"]) in pairs for row in answers),
               "attempts": len(affected) + len(selected_glossary),
               "glossary_attempts": len(selected_glossary),
               "glossary_answers": sum(len(json.loads(row['state'])['answers']) for row in selected_glossary),
               "active_attempts": sum(row["id"] in affected and row["status"] == "in_progress" for row in sessions)
                   + sum(row['status'] == 'in_progress' for row in selected_glossary)}
    return preview, selected, affected


def preview(conn, actor, payload):
    return _read(conn, actor, payload)[0]


def confirm(conn, actor, payload):
    revision = payload.get("expected_revision")
    if payload.get("confirm") is not True or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
        raise ProgressError("reset_confirmation_required")
    current, selected, affected = _read(conn, actor, payload)
    if not hmac.compare_digest(current["revision"], revision):
        raise ProgressError("reset_changed", 409)
    if not current['attempts']:
        raise ProgressError("nothing_to_reset", 409)
    if current["scope"] == "all":
        # FK cascades are restricted to this actor's learning attempts.
        conn.execute("DELETE FROM quiz_sessions WHERE user_id=?", (actor,))
        conn.execute('DELETE FROM glossary_sessions WHERE user_id=?', (actor,))
    else:
        conn.execute('DELETE FROM glossary_sessions WHERE user_id=? AND topic_title=?', (actor, current['topic']))
        by_session = defaultdict(list)
        for row in selected:
            by_session[row["session_id"]].append(row["question_id"])
        for sid, question_ids in by_session.items():
            for offset in range(0, len(question_ids), 400):
                chunk = question_ids[offset:offset + 400]
                condition = "session_id=? AND question_id IN (" + ",".join("?" for _ in chunk) + ")"
                conn.execute("DELETE FROM quiz_answers WHERE " + condition, (sid, *chunk))
                conn.execute("DELETE FROM quiz_session_questions WHERE " + condition, (sid, *chunk))
            remaining = conn.execute("SELECT count(*) FROM quiz_session_questions WHERE session_id=?", (sid,)).fetchone()[0]
            if not remaining:
                conn.execute("DELETE FROM quiz_sessions WHERE id=? AND user_id=?", (sid, actor))
                continue
            # Other topics retain original snapshots/answers and ordering. A
            # partially cleared active attempt cannot accept a delayed answer.
            conn.execute(f"""UPDATE quiz_sessions SET total_questions=?,
                score=(SELECT COALESCE(sum(is_correct),0) FROM quiz_answers WHERE session_id=?),
                finished_at=CASE WHEN status='in_progress' THEN {timestamp_sql(conn)} ELSE finished_at END,
                status=CASE WHEN status='in_progress' THEN 'abandoned' ELSE status END
                WHERE id=? AND user_id=?""", (remaining, sid, sid, actor))
    return {"ok": True, "deleted_answers": current["answers"], "deleted_questions": current["questions"],
            "deleted_glossary_answers": current['glossary_answers']}
