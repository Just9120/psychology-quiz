"""Derive private achievements from completed attempts and captured review evidence."""
from __future__ import annotations

from datetime import timedelta
import json

from app.curriculum import classification
from app.repetition import glossary_history
from app.study_events import completed_studies, utc as _utc


def _award(conn, actor: int, kind: str, key: str, at: str) -> None:
    conn.execute("""INSERT INTO user_achievements(user_id,achievement_kind,evidence_key,earned_at)
        VALUES(?,?,?,?) ON CONFLICT(user_id,achievement_kind,evidence_key) DO NOTHING""",
        (actor, kind, key, at))


def _quiz_evidence(conn, actor: int) -> list[dict]:
    rows = conn.execute("""SELECT s.id AS session_id,s.status,s.finished_at,a.id AS answer_id,
            a.question_id,a.is_correct,a.answered_at,sq.content_sha256,sq.snapshot_provenance,
            sq.content_snapshot,q.kind AS question_kind
        FROM quiz_sessions s JOIN quiz_answers a ON a.session_id=s.id
        JOIN quiz_session_questions sq ON sq.session_id=a.session_id AND sq.question_id=a.question_id
        JOIN questions q ON q.id=a.question_id
        WHERE s.user_id=? ORDER BY a.answered_at,a.id""", (actor,)).fetchall()
    return [dict(row) for row in rows]


def _glossary_review_awards(conn, actor: int) -> None:
    reviewed = {(str(kind), str(key)) for kind, key in conn.execute("""SELECT answer_kind,answer_key
        FROM user_review_events WHERE user_id=?""", (actor,))}
    for (topic_id, term_id), record in glossary_history(conn, actor).items():
        wrong_seen = False
        for (at, correct, edition, provenance), ref in zip(record["events"], record["answer_refs"]):
            if edition != "current" or provenance != "captured":
                wrong_seen = False
                continue
            if correct and wrong_seen and ref in reviewed:
                key = f"glossary:{topic_id}:{term_id}:{record['edition']}"
                _award(conn, actor, "corrected_error", key, at)
                break
            if not correct:
                wrong_seen = True


def refresh(conn, actor: int) -> dict:
    """Idempotent materialization; caller holds the actor transaction."""
    completed = completed_studies(conn, actor)
    completed_at = {int(event.key): event.completed_at for event in completed if event.kind == "quiz"}
    topic_events = [(event.completed_at, f"glossary:{topic}") for event in completed
                    for topic in event.glossary_topics]
    wrong = set()
    reviewed_answers = {str(row[0]) for row in conn.execute("""SELECT answer_key FROM user_review_events
        WHERE user_id=? AND answer_kind='quiz'""", (actor,))}
    evidence = _quiz_evidence(conn, actor)
    for item in evidence:
        if item["session_id"] not in completed_at or item["snapshot_provenance"] != "captured":
            continue
        content = json.loads(item["content_snapshot"])
        parts = content.get("external_id", "").split(":", 2)
        if content.get("kind") == "glossary" and len(parts) == 3 and parts[0] == "glossary":
            topic = f"glossary:{parts[1]}"
        else:
            topic = classification({**content, "content_sha256": item["content_sha256"],
                                    "snapshot_provenance": item["snapshot_provenance"]})["topic_id"]
        if topic:
            topic_events.append((completed_at[item["session_id"]], topic))
    known_topics = set()
    for at, topic in sorted(topic_events):
        if topic not in known_topics:
            _award(conn, actor, "new_topic", topic, at.isoformat())
            known_topics.add(topic)
    for item in sorted(evidence, key=lambda value: (_utc(value["answered_at"]), value["answer_id"])):
        if item["snapshot_provenance"] != "captured" or item["question_kind"] == "glossary":
            continue
        key = (int(item["question_id"]), item["content_sha256"])
        if item["is_correct"] and key in wrong and str(item["answer_id"]) in reviewed_answers:
            _award(conn, actor, "corrected_error", f"quiz:{key[0]}:{key[1]}", item["answered_at"])
        elif not item["is_correct"]:
            wrong.add(key)
    weeks = sorted({event.completed_at.date() - timedelta(days=event.completed_at.weekday())
                    for event in completed})
    regularity_earned = conn.execute("""SELECT 1 FROM user_achievements
        WHERE user_id=? AND achievement_kind='regularity'""", (actor,)).fetchone()
    for earlier, later in zip(weeks, weeks[1:]) if not regularity_earned else ():
        if later - earlier == timedelta(days=7):
            at = next(event.completed_at for event in completed if event.completed_at.date() >= later)
            _award(conn, actor, "regularity", f"{earlier}:{later}", at.isoformat())
            break
    _glossary_review_awards(conn, actor)
    return {"ok": True, "achievements": [
        {"kind": row[0], "evidence_key": row[1], "earned_at": row[2]}
        for row in conn.execute("""SELECT achievement_kind,evidence_key,earned_at FROM user_achievements
            WHERE user_id=? ORDER BY earned_at,achievement_kind,evidence_key""", (actor,))]}
