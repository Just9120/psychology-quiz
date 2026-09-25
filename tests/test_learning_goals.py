from contextlib import closing
from datetime import datetime, timezone

import pytest

from app.db import create_or_load_user, get_connection
from app.learning_goals import GoalError, overview, set_target
from tests.test_attempt_content import bank
from tests.test_progress import record


def test_weekly_units_are_personal_durable_and_event_based(bank):
    now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
    with closing(get_connection(str(bank))) as conn, conn:
        other = create_or_load_user(conn, 991, None, None, None)["id"]
        old = record(conn, actor=1)
        current = record(conn, actor=1)
        foreign = record(conn, actor=other)
        conn.execute("UPDATE quiz_sessions SET finished_at='2026-09-14 12:00:00' WHERE id=?", (old,))
        conn.execute("UPDATE quiz_sessions SET finished_at='2026-09-24 12:00:00' WHERE id IN (?,?)", (current, foreign))
        conn.execute("""INSERT INTO user_review_events(user_id,answer_kind,answer_key,answered_at)
            VALUES(1,'quiz','1','2026-09-24 12:00:00'),(1,'glossary','s:1','2026-09-25 12:00:00'),
                  (?,'quiz','2','2026-09-24 12:00:00')""", (other,))
        conn.execute("""INSERT INTO user_literature_progress(user_id,literature_id,reading_status,completed_at,updated_at)
            VALUES(1,'book','read','2026-09-23 12:00:00','2026-09-23 12:00:00'),
                  (?,'other','read','2026-09-23 12:00:00','2026-09-23 12:00:00')""", (other,))
        for kind, target in (("study", 1), ("review", 2), ("reading", 1)):
            set_target(conn, 1, {"goal_kind": kind, "weekly_target": target})
        result = overview(conn, 1, now=now)
        assert result["week_start"] == "2026-09-21"
        assert [(item["goal_kind"], item["completed"], item["reached"]) for item in result["goals"]] == [
            ("study", 1, True), ("review", 2, True), ("reading", 1, True)]
        before = conn.execute("SELECT updated_at FROM user_learning_goals WHERE user_id=1 AND goal_kind='study'").fetchone()[0]
        set_target(conn, 1, {"goal_kind": "study", "weekly_target": 1})
        assert conn.execute("SELECT updated_at FROM user_learning_goals WHERE user_id=1 AND goal_kind='study'").fetchone()[0] == before
        assert [item["weekly_target"] for item in overview(conn, other, now=now)["goals"]] == [None] * 3
        assert [item["completed"] for item in overview(conn, other, now=now)["goals"]] == [1, 1, 1]


def test_invalid_goal_never_mutates_target(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        for payload in ({"goal_kind": "study", "weekly_target": True},
                        {"goal_kind": "study", "weekly_target": 0},
                        {"goal_kind": "unknown", "weekly_target": 1},
                        {"goal_kind": "reading", "weekly_target": 2**64}):
            with pytest.raises(GoalError):
                set_target(conn, 1, payload)
        assert conn.execute("SELECT count(*) FROM user_learning_goals").fetchone()[0] == 0
