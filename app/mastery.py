"""Edition-aware mastery from durable answer evidence.

This module never changes an answer or the content bank. Transport adapters
must pass a verified actor; legacy backfills cannot prove a captured edition.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.attempt_content import capture_question


FIRST_INTERVAL = timedelta(days=1)
SECOND_INTERVAL = timedelta(days=3)
TOTAL_INTERVAL = timedelta(days=7)


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def evaluate(events: list[tuple[str, bool]], *, edition_confirmed: bool = True) -> dict:
    """Return a conservative status for ordered answers to one captured edition.

    An incorrect answer starts a new streak. Within the current streak, any
    qualifying ordered triple proves mastery; subsequent correct answers keep
    it until an error or a new edition. The caller must isolate actor/edition.
    """
    if not edition_confirmed:
        return {"status": "insufficient_data", "correct_streak": 0}
    first: datetime | None = None
    second: datetime | None = None
    streak_count = 0
    mastered = False
    for timestamp, is_correct in events:
        instant = _instant(timestamp)
        if not is_correct:
            first = second = None
            streak_count = 0
            mastered = False
            continue
        streak_count += 1
        if first is None:
            first = instant
            continue
        if mastered:
            continue
        if second is None:
            if instant - first >= FIRST_INTERVAL:
                second = instant
            continue
        if instant - second >= SECOND_INTERVAL and instant - first >= TOTAL_INTERVAL:
            mastered = True
    return {"status": "mastered" if mastered else "insufficient_data",
            "correct_streak": streak_count}


def quiz_states(conn, actor: int) -> dict:
    """Assess only answered, currently approved questions for one actor.

    A different captured edition breaks the streak. Legacy backfills never
    contribute proof, even if their bytes match the current bank by chance.
    """
    rows = conn.execute("""SELECT a.question_id,a.answered_at,a.is_correct,
                                  sq.content_sha256,sq.snapshot_provenance
        FROM quiz_sessions s JOIN quiz_answers a ON a.session_id=s.id
        JOIN quiz_session_questions sq ON sq.session_id=a.session_id AND sq.question_id=a.question_id
        WHERE s.user_id=? ORDER BY a.question_id,a.answered_at,a.id""", (actor,)).fetchall()
    approved = {int(row[0]) for row in conn.execute("SELECT id FROM questions WHERE status='approved'")}
    by_question = {}
    for row in rows:
        by_question.setdefault(int(row[0]), []).append(row)
    items = []
    for question_id in sorted(by_question.keys() & approved):
        current_sha = capture_question(conn, question_id)[1]
        events = []
        for row in by_question[question_id]:
            if row[3] != current_sha or row[4] != "captured":
                events.clear()
                continue
            events.append((row[1], bool(row[2])))
        items.append({"question_id": question_id, "content_sha256": current_sha,
                      **evaluate(events)})
    return {"ok": True, "items": items,
            "mastered_count": sum(item["status"] == "mastered" for item in items),
            "assessed_count": len(items)}
