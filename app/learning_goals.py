"""Private weekly learning goals computed from durable events, not counters."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database import begin_write
from app.payload_validation import is_sqlite_integer

KINDS = ("study", "review", "reading")


class GoalError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def set_target(conn, actor: int, payload: dict) -> dict:
    kind, target = payload.get("goal_kind"), payload.get("weekly_target")
    if kind not in KINDS or not is_sqlite_integer(target, minimum=1):
        raise GoalError("invalid_goal")
    begin_write(conn, f"actor:{actor}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""INSERT INTO user_learning_goals(user_id,goal_kind,weekly_target,updated_at)
        VALUES(?,?,?,?) ON CONFLICT(user_id,goal_kind) DO UPDATE SET
        weekly_target=excluded.weekly_target,updated_at=excluded.updated_at
        WHERE user_learning_goals.weekly_target IS DISTINCT FROM excluded.weekly_target""",
        (actor, kind, target, now))
    return overview(conn, actor)


def overview(conn, actor: int, *, now: datetime | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = now.date() - timedelta(days=now.weekday())
    end = start + timedelta(days=7)
    lower, upper = start.isoformat(), end.isoformat()
    targets = {row[0]: int(row[1]) for row in conn.execute(
        "SELECT goal_kind,weekly_target FROM user_learning_goals WHERE user_id=?", (actor,))}
    completed = {
        "study": conn.execute("""SELECT count(*) FROM quiz_sessions
            WHERE user_id=? AND status='finished' AND finished_at>=? AND finished_at<?""",
            (actor, lower, upper)).fetchone()[0],
        "review": conn.execute("""SELECT count(*) FROM user_review_events
            WHERE user_id=? AND answered_at>=? AND answered_at<?""",
            (actor, lower, upper)).fetchone()[0],
        "reading": conn.execute("""SELECT count(*) FROM user_literature_progress
            WHERE user_id=? AND reading_status='read' AND completed_at>=? AND completed_at<?""",
            (actor, lower, upper)).fetchone()[0],
    }
    return {"ok": True, "week_start": lower, "week_end_exclusive": upper,
            "goals": [{"goal_kind": kind, "weekly_target": targets.get(kind),
                       "completed": int(completed[kind]),
                       "reached": (int(completed[kind]) >= targets[kind]) if kind in targets else None}
                      for kind in KINDS]}
