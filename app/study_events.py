"""One completed study event per durable quiz or dedicated glossary attempt."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json


def utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def glossary_completion(state: dict, updated_at: str) -> str | None:
    # Old completed attempts did not store their completion time separately.
    # Until their first restart, updated_at is that time. Older restarted rows
    # no longer contain it: do not substitute the restart or last-answer date.
    return state.get("completed_at") or (updated_at if not state.get("restarted") else None)


@dataclass(frozen=True)
class StudyEvent:
    kind: str
    key: str
    completed_at: datetime
    glossary_topics: frozenset[str] = frozenset()


def completed_studies(conn, actor: int) -> list[StudyEvent]:
    events = [StudyEvent("quiz", str(sid), utc(at)) for sid, at in conn.execute(
        """SELECT id,finished_at FROM quiz_sessions
        WHERE user_id=? AND status='finished' AND finished_at IS NOT NULL""", (actor,))]
    for sid, encoded, snapshot_json, updated_at in conn.execute(
            """SELECT id,state,snapshot,updated_at FROM glossary_sessions
            WHERE user_id=? AND status='completed'""", (actor,)):
        state, snapshot = json.loads(encoded), json.loads(snapshot_json)
        at = glossary_completion(state, updated_at)
        if at is None:
            continue
        topics = frozenset(question['entry']['topic_id']
                           for question in snapshot.get('questions', []))
        events.append(StudyEvent("glossary", sid, utc(at), topics))
    return sorted(events, key=lambda event: (event.completed_at, event.kind, event.key))
