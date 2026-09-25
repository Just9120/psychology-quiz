"""Derive private achievements from completed attempts and captured review evidence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from app.content_publication import fingerprint
from app.curriculum import classification


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _award(conn, actor: int, kind: str, key: str, at: str) -> None:
    conn.execute("""INSERT INTO user_achievements(user_id,achievement_kind,evidence_key,earned_at)
        VALUES(?,?,?,?) ON CONFLICT(user_id,achievement_kind,evidence_key) DO NOTHING""",
        (actor, kind, key, at))


def _quiz_evidence(conn, actor: int) -> list[dict]:
    rows = conn.execute("""SELECT s.id AS session_id,s.status,s.finished_at,a.id AS answer_id,
            a.question_id,a.is_correct,a.answered_at,sq.content_sha256,sq.snapshot_provenance,
            sq.content_snapshot
        FROM quiz_sessions s JOIN quiz_answers a ON a.session_id=s.id
        JOIN quiz_session_questions sq ON sq.session_id=a.session_id AND sq.question_id=a.question_id
        WHERE s.user_id=? ORDER BY a.answered_at,a.id""", (actor,)).fetchall()
    return [dict(row) for row in rows]


def _glossary_review_awards(conn, actor: int) -> None:
    history = {}
    for sid, snapshot_text, state_text, updated in conn.execute("""SELECT id,snapshot,state,updated_at
            FROM glossary_sessions WHERE user_id=? ORDER BY created_at,id""", (actor,)):
        snapshot, state = json.loads(snapshot_text), json.loads(state_text)
        for step_text, answer in state.get("answers", {}).items():
            try:
                step = int(step_text)
                entry = snapshot["questions"][step - 1]["entry"]
                at = answer.get("answered_at")
                if not at:
                    continue  # old backfills do not establish edition or answer time
                key = f"{entry['topic_id']}:{entry['id']}:{fingerprint(entry)}"
                history.setdefault(key, []).append((at, bool(answer["response"]["feedback"]["is_correct"]), sid, step))
            except (IndexError, KeyError, TypeError, ValueError):
                continue
    reviewed = {(sid, int(step)) for kind, answer_key in conn.execute("""SELECT answer_kind,answer_key
        FROM user_review_events WHERE user_id=? AND answer_kind='glossary'""", (actor,))
                if kind == "glossary" for sid, separator, step in [answer_key.rpartition(":")]
                if separator and step.isdigit()}
    for key, events in history.items():
        wrong_seen = False
        for at, correct, sid, step in sorted(events, key=lambda event: _utc(event[0])):
            if correct and wrong_seen and (sid, step) in reviewed:
                _award(conn, actor, "corrected_error", "glossary:" + key, at)
                break
            if not correct:
                wrong_seen = True


def refresh(conn, actor: int) -> dict:
    """Idempotent materialization; caller holds the actor transaction."""
    completed = conn.execute("""SELECT id,finished_at FROM quiz_sessions
        WHERE user_id=? AND status='finished' AND finished_at IS NOT NULL
        ORDER BY finished_at,id""", (actor,)).fetchall()
    completed_at = {int(row[0]): row[1] for row in completed}
    known_topics = set()
    wrong = set()
    reviewed_answers = {str(row[0]) for row in conn.execute("""SELECT answer_key FROM user_review_events
        WHERE user_id=? AND answer_kind='quiz'""", (actor,))}
    evidence = _quiz_evidence(conn, actor)
    for item in sorted(evidence, key=lambda value: (completed_at.get(value["session_id"], ""), value["session_id"])):
        if item["session_id"] not in completed_at or item["snapshot_provenance"] != "captured":
            continue
        content = json.loads(item["content_snapshot"])
        topic = classification({**content, "content_sha256": item["content_sha256"],
                                "snapshot_provenance": item["snapshot_provenance"]})["topic_id"]
        if topic and topic not in known_topics:
            _award(conn, actor, "new_topic", topic, completed_at[item["session_id"]])
            known_topics.add(topic)
    for item in sorted(evidence, key=lambda value: (_utc(value["answered_at"]), value["answer_id"])):
        if item["snapshot_provenance"] != "captured":
            continue
        key = (int(item["question_id"]), item["content_sha256"])
        if item["is_correct"] and key in wrong and str(item["answer_id"]) in reviewed_answers:
            _award(conn, actor, "corrected_error", f"quiz:{key[0]}:{key[1]}", item["answered_at"])
        elif not item["is_correct"]:
            wrong.add(key)
    weeks = sorted({_utc(at).date() - timedelta(days=_utc(at).weekday()) for at in completed_at.values()})
    for earlier, later in zip(weeks, weeks[1:]):
        if later - earlier == timedelta(days=7):
            at = next(value for value in completed_at.values() if _utc(value).date() >= later)
            _award(conn, actor, "regularity", f"{earlier}:{later}", at)
            break
    _glossary_review_awards(conn, actor)
    return {"ok": True, "achievements": [
        {"kind": row[0], "evidence_key": row[1], "earned_at": row[2]}
        for row in conn.execute("""SELECT achievement_kind,evidence_key,earned_at FROM user_achievements
            WHERE user_id=? ORDER BY earned_at,achievement_kind,evidence_key""", (actor,))]}
