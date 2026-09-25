"""Personal, edition-aware review dates; no content or answer mutation."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import json

from app.attempt_content import capture_question
from app.content_publication import fingerprint
from app.glossary import GLOSSARY_TOPICS, load_glossary_entries


def _day(value: str) -> date:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date()


def schedule(events: list[tuple[str, bool, str, str]], edition: str, *, today: date) -> dict:
    """events are chronological (timestamp, correct, edition, provenance)."""
    matching: list[tuple[str, bool]] = []
    for timestamp, correct, answered_edition, provenance in events:
        if answered_edition != edition or provenance != "captured":
            matching.clear()
        else:
            matching.append((timestamp, bool(correct)))
    if not matching:
        return {"due_on": today.isoformat(), "is_due": True,
                "correct_streak": 0, "reason": "new_edition"}
    streak = 0
    for _, correct in matching:
        streak = streak + 1 if correct else 0
    interval = 1 if streak == 0 else 3 if streak == 1 else 7 if streak == 2 else 14
    due_on = _day(matching[-1][0]) + timedelta(days=interval)
    return {"due_on": due_on.isoformat(), "is_due": due_on <= today,
            "correct_streak": streak, "reason": "error" if streak == 0 else "scheduled"}


def quiz_queue(conn, actor: int, *, today: date) -> list[dict]:
    rows = conn.execute("""SELECT a.question_id,a.answered_at,a.is_correct,
                                  sq.content_sha256,sq.snapshot_provenance
        FROM quiz_sessions s JOIN quiz_answers a ON a.session_id=s.id
        JOIN quiz_session_questions sq ON sq.session_id=a.session_id AND sq.question_id=a.question_id
        WHERE s.user_id=? ORDER BY a.question_id,a.answered_at,a.id""", (actor,)).fetchall()
    grouped = defaultdict(list)
    for row in rows:
        grouped[int(row[0])].append((row[1], bool(row[2]), row[3], row[4]))
    if not grouped:
        return []
    ids = sorted(grouped)
    placeholders = ",".join("?" for _ in ids)
    approved = conn.execute(f"""SELECT q.id,c.name FROM questions q
        JOIN categories c ON c.id=q.category_id WHERE q.status='approved' AND q.id IN ({placeholders})""", ids)
    items = []
    for question_id, topic in approved:
        current = capture_question(conn, int(question_id))[1]
        items.append({"kind": "quiz", "question_id": int(question_id), "topic": topic,
                      **schedule(grouped[int(question_id)], current, today=today)})
    return items


def glossary_queue(conn, actor: int, *, today: date) -> list[dict]:
    current = {}
    for topic_id, topic in GLOSSARY_TOPICS:
        for entry in load_glossary_entries(topic_id) or []:
            current[(topic_id, entry.id)] = (topic, fingerprint(asdict(entry)))
    grouped = defaultdict(list)
    sessions = conn.execute("""SELECT snapshot,state FROM glossary_sessions
        WHERE user_id=? ORDER BY created_at,id""", (actor,)).fetchall()
    for snapshot_json, state_json in sessions:
        snapshot, state = json.loads(snapshot_json), json.loads(state_json)
        for step, answer in state.get("answers", {}).items():
            try:
                entry = snapshot["questions"][int(step) - 1]["entry"]
                key = (entry["topic_id"], entry["id"])
                timestamp = answer["answered_at"]
                correct = bool(answer["response"]["feedback"]["is_correct"])
            except (IndexError, KeyError, TypeError, ValueError):
                continue
            if key in current:
                grouped[key].append((timestamp, correct, fingerprint(entry), "captured"))
    items = []
    for (topic_id, term_id), events in grouped.items():
        events.sort(key=lambda event: event[0])
        topic, edition = current[(topic_id, term_id)]
        items.append({"kind": "glossary", "topic_id": topic_id, "term_id": term_id,
                      "topic": topic, **schedule(events, edition, today=today)})
    return items


def queue(conn, actor: int, *, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    items = quiz_queue(conn, actor, today=today) + glossary_queue(conn, actor, today=today)
    items.sort(key=lambda item: (not item["is_due"], item["due_on"], item["kind"],
                                 str(item.get("question_id", item.get("term_id")))))
    return {"ok": True, "today": today.isoformat(), "due_count": sum(item["is_due"] for item in items),
            "items": items}
