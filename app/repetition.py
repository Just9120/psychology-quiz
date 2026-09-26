"""Personal, edition-aware review dates; no content or answer mutation."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import json

from app.attempt_content import capture_question
from app.content_publication import fingerprint
from app.glossary import GLOSSARY_TOPICS, load_glossary_entries
from app.glossary_projection import projected_questions


def _matches_published_projection(snapshot: dict, projected: dict) -> bool:
    """A quiz edition shares term history only while it is the exact published projection."""
    fields = {"external_id": "id", "question_text": "question", "category": "category",
              "explanation": "explanation", "source_ref": "source_ref",
              "difficulty": "difficulty", "kind": "kind"}
    if any(snapshot.get(field) != projected.get(source) for field, source in fields.items()):
        return False
    expected = [{"option_index": index, "option_text": text,
                 "is_correct": int(index == projected["correct_option_index"])}
                for index, text in enumerate(projected["options"])]
    return snapshot.get("options") == expected


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _day(value: str) -> date:
    return _instant(value).date()


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
        JOIN categories c ON c.id=q.category_id WHERE q.status='approved'
        AND q.kind!='glossary' AND q.id IN ({placeholders})""", ids)
    items = []
    for question_id, topic in approved:
        current = capture_question(conn, int(question_id))[1]
        items.append({"kind": "quiz", "question_id": int(question_id), "topic": topic,
                      **schedule(grouped[int(question_id)], current, today=today)})
    return items


def glossary_history(conn, actor: int) -> dict[tuple[str, str], dict]:
    """Merge captured term answers from both attempt formats for one actor."""
    current = {}
    for topic_id, topic in GLOSSARY_TOPICS:
        for entry in load_glossary_entries(topic_id) or []:
            current[(topic_id, entry.id)] = {
                "topic": topic, "edition": fingerprint(asdict(entry)),
                "question_id": None, "events": [],
            }
    grouped = defaultdict(list)
    sessions = conn.execute("""SELECT id,snapshot,state,updated_at FROM glossary_sessions
        WHERE user_id=? ORDER BY created_at,id""", (actor,)).fetchall()
    for session_id, snapshot_json, state_json, updated_at in sessions:
        snapshot, state = json.loads(snapshot_json), json.loads(state_json)
        for step, answer in state.get("answers", {}).items():
            try:
                entry = snapshot["questions"][int(step) - 1]["entry"]
                key = (entry["topic_id"], entry["id"])
                timestamp = answer.get("answered_at") or updated_at
                correct = bool(answer["response"]["feedback"]["is_correct"])
            except (IndexError, KeyError, TypeError, ValueError):
                continue
            if key in current:
                grouped[key].append((timestamp, correct,
                                     "current" if fingerprint(entry) == current[key]["edition"] else "stale",
                                     "captured" if answer.get("answered_at") else "legacy_backfill_current",
                                     "glossary", f"{session_id}:{step}"))
    rows = conn.execute("""SELECT a.id,a.question_id,a.answered_at,a.is_correct,
                                  sq.content_sha256,sq.snapshot_provenance
        FROM quiz_sessions s JOIN quiz_answers a ON a.session_id=s.id
        JOIN quiz_session_questions sq ON sq.session_id=a.session_id AND sq.question_id=a.question_id
        JOIN questions q ON q.id=a.question_id
        WHERE s.user_id=? AND q.kind='glossary' AND q.status='approved'""", (actor,)).fetchall()
    answered_question_ids = {int(row[1]) for row in rows}
    if not grouped and not answered_question_ids:
        return {}
    question_keys = {}
    projections = {item["id"]: item for item in projected_questions()}
    for question_id, external_id in conn.execute(
            "SELECT id,external_id FROM questions WHERE kind='glossary' AND status='approved'"):
        parts = str(external_id).split(":", 2)
        if len(parts) != 3 or parts[0] != "glossary":
            continue
        key = (parts[1], parts[2])
        if key not in current or (key not in grouped and int(question_id) not in answered_question_ids):
            continue
        captured, edition = capture_question(conn, int(question_id))
        expected = projections.get(str(external_id))
        projection_valid = expected is not None and _matches_published_projection(json.loads(captured), expected)
        if projection_valid:
            current[key]["question_id"] = int(question_id)
        current[key]["projection_valid"] = projection_valid
        current[key]["quiz_edition"] = edition
        question_keys[int(question_id)] = key
    for answer_id, question_id, timestamp, correct, edition, provenance in rows:
        key = question_keys.get(int(question_id))
        if key is not None:
            grouped[key].append((timestamp, bool(correct),
                                 "current" if current[key]["projection_valid"] and
                                     edition == current[key]["quiz_edition"] else "stale",
                                 provenance, "quiz", str(answer_id)))
    for key, events in grouped.items():
        events.sort(key=lambda event: _instant(event[0]))
        current[key]["events"] = [event[:4] for event in events]
        current[key]["answer_refs"] = [event[4:] for event in events]
    return {key: current[key] for key in grouped}


def glossary_queue(conn, actor: int, *, today: date) -> list[dict]:
    items = []
    for (topic_id, term_id), record in glossary_history(conn, actor).items():
        item = {"kind": "glossary", "topic_id": topic_id, "term_id": term_id,
                "topic": record["topic"],
                **schedule(record["events"], "current", today=today)}
        if record["question_id"] is not None:
            item["question_id"] = record["question_id"]
        items.append(item)
    return items


def queue(conn, actor: int, *, today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    items = quiz_queue(conn, actor, today=today) + glossary_queue(conn, actor, today=today)
    items.sort(key=lambda item: (not item["is_due"], item["due_on"], item["kind"],
                                 str(item.get("question_id", item.get("term_id")))))
    return {"ok": True, "today": today.isoformat(), "due_count": sum(item["is_due"] for item in items),
            "items": items}


def adaptive_questions(conn, actor: int | None, candidates: list[int], count: int | None,
                       *, today: date | None = None) -> list[int]:
    """Select due/weak material while reserving room for unseen questions.

    The caller supplies only eligible approved IDs in a randomized order;
    this function never broadens that scope or changes the regular random mode.
    """
    if not candidates or actor is None:
        return candidates[:count]
    due_ids = {item["question_id"] for item in queue(conn, actor,
               today=today or datetime.now(timezone.utc).date())["items"]
               if item["is_due"] and item.get("question_id") is not None}
    seen = set()
    weakness = defaultdict(lambda: [0, 0])
    for question_id, correct, snapshot in conn.execute("""SELECT a.question_id,a.is_correct,sq.content_snapshot
        FROM quiz_sessions s JOIN quiz_answers a ON a.session_id=s.id
        JOIN quiz_session_questions sq ON sq.session_id=a.session_id AND sq.question_id=a.question_id
        WHERE s.user_id=?""", (actor,)):
        seen.add(int(question_id))
        topic = json.loads(snapshot).get("category")
        if isinstance(topic, str):
            weakness[topic][0] += int(not correct)
            weakness[topic][1] += 1
    ids = sorted(set(candidates))
    metadata = {int(row[0]): row[1] for row in conn.execute(
        f"SELECT q.id,c.name FROM questions q JOIN categories c ON c.id=q.category_id WHERE q.id IN ({','.join('?' for _ in ids)})", ids)}
    position = {question_id: index for index, question_id in enumerate(candidates)}

    def rank(question_id):
        wrong, total = weakness[metadata[question_id]]
        return (-(wrong / total if total else -1), position[question_id])

    due = sorted((qid for qid in candidates if qid in due_ids), key=rank)
    new = sorted((qid for qid in candidates if qid not in seen), key=rank)
    other = sorted((qid for qid in candidates if qid not in due_ids and qid in seen), key=rank)
    if count is None:
        return due + new + other
    reserve_new = min(len(new), max(1, count // 4)) if due and count > 1 else (min(len(new), count) if not due else 0)
    chosen = due[:count - reserve_new] + new[:reserve_new]
    for question_id in due[count - reserve_new:] + new[reserve_new:] + other:
        if len(chosen) >= count:
            break
        chosen.append(question_id)
    return chosen
