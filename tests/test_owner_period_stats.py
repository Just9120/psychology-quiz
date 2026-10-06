"""Owner learning aggregates use the selected window and never return identities."""
import sqlite3
from datetime import datetime, timezone

import pytest

from app.db import get_owner_period_stats


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE quiz_sessions(id INTEGER PRIMARY KEY,user_id INTEGER,started_at TEXT,finished_at TEXT,status TEXT);
        CREATE TABLE quiz_answers(id INTEGER PRIMARY KEY,answered_at TEXT);
        CREATE TABLE glossary_sessions(id TEXT PRIMARY KEY,user_id INTEGER,created_at TEXT,updated_at TEXT,status TEXT);
        CREATE TABLE user_review_events(user_id INTEGER,answered_at TEXT);
        CREATE TABLE user_literature_work_progress(user_id INTEGER,updated_at TEXT);
        INSERT INTO quiz_sessions VALUES
          (1,10,'2026-09-29 10:00:00','2026-09-29 11:00:00','finished'),
          (2,10,'2026-09-25 10:00:00',NULL,'in_progress'),
          (3,20,'2026-09-10 10:00:00','2026-09-10 11:00:00','finished');
        INSERT INTO quiz_answers VALUES(1,'2026-09-29 10:30:00'),(2,'2026-09-10 10:30:00');
        INSERT INTO glossary_sessions VALUES
          ('one',20,'2026-09-26T10:00:00+00:00','2026-09-26T11:00:00+00:00','completed');
        INSERT INTO user_review_events VALUES(10,'2026-09-29T09:00:00+00:00');
        INSERT INTO user_literature_work_progress VALUES(30,'2026-09-29T09:00:00+00:00');
    """)
    try:
        yield db
    finally:
        db.close()


def test_period_aggregates_are_deidentified_and_change_with_window(conn):
    now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
    day = get_owner_period_stats(conn, "24h", now=now)
    week = get_owner_period_stats(conn, "7d", now=now)
    month = get_owner_period_stats(conn, "30d", now=now)
    assert (day["active_users"], week["active_users"], month["active_users"]) == (2, 3, 3)
    assert (day["quiz_started"], week["quiz_started"], month["quiz_started"]) == (1, 2, 3)
    assert (day["quiz_completed"], week["quiz_completed"], month["quiz_completed"]) == (1, 1, 2)
    assert week["glossary_completed"] == 1 and day["glossary_completed"] == 0
    assert week["reading_items_updated"] == 1
    assert week["quiz_answers"] == 1
    assert not any(key in str(week).lower() for key in ("email", "username", "telegram", "user_id"))


def test_same_day_iso_events_before_cutoff_do_not_inflate_quiz_counts(conn):
    conn.execute("UPDATE quiz_sessions SET started_at=?,finished_at=?,status='finished' WHERE id=2",
                 ('2026-09-28T11:59:59+00:00', '2026-09-28T11:59:59+00:00'))
    conn.execute("UPDATE quiz_answers SET answered_at=? WHERE id=2",
                 ('2026-09-28T11:59:59+00:00',))
    now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
    result = get_owner_period_stats(conn, "24h", now=now)
    assert (result['quiz_started'], result['quiz_completed'], result['quiz_answers']) == (1, 1, 1)
    # The rolling period includes the exact cutoff in either stored format.
    conn.execute("UPDATE quiz_sessions SET started_at=?,finished_at=? WHERE id=2",
                 ('2026-09-28T12:00:00+00:00', '2026-09-28T12:00:00+00:00'))
    conn.execute("UPDATE quiz_answers SET answered_at=? WHERE id=2",
                 ('2026-09-28T12:00:00+00:00',))
    result = get_owner_period_stats(conn, "24h", now=now)
    assert (result['quiz_started'], result['quiz_completed'], result['quiz_answers']) == (2, 2, 2)


@pytest.mark.parametrize("period", ["all", "", None, [], 7])
def test_period_is_allowlisted(conn, period):
    with pytest.raises(ValueError, match="invalid_period"):
        get_owner_period_stats(conn, period)
