"""Read-only owner activity aggregates, independent of quiz write operations.

Transport adapters authorize the owner before invoking these queries. The db
module retains compatibility imports for existing callers.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.database import Connection


def get_owner_stats(conn: Connection) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoffs = {days: (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S") for days in (1, 7, 30)}

    def _fetch_count(query: str, parameters=()) -> int:
        row = conn.execute(query, parameters).fetchone()
        if row is None:
            return 0
        return int(row[0])

    questions_by_category_rows = conn.execute(
        """
        SELECT c.name AS category_name, COUNT(q.id) AS question_count
        FROM categories c
        LEFT JOIN questions q
          ON q.category_id = c.id
         AND q.status = 'approved'
        GROUP BY c.id, c.name
        HAVING COUNT(q.id) > 0
        ORDER BY c.name ASC
        """
    ).fetchall()

    top_categories_30d_rows = conn.execute(
        """
        SELECT c.name, COUNT(DISTINCT qs.id) AS started_sessions
        FROM quiz_sessions qs
        JOIN quiz_session_questions qsq ON qsq.session_id = qs.id
        JOIN questions q ON q.id = qsq.question_id
        JOIN categories c ON c.id = q.category_id
        WHERE qs.started_at >= ?
        GROUP BY c.id, c.name
        ORDER BY started_sessions DESC, c.name ASC
        LIMIT 5
        """, (cutoffs[30],)
    ).fetchall()

    return {
        "total_users": _fetch_count("SELECT COUNT(*) FROM users"),
        "new_users_24h": _fetch_count(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (cutoffs[1],)
        ),
        "new_users_7d": _fetch_count(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (cutoffs[7],)
        ),
        "new_users_30d": _fetch_count(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (cutoffs[30],)
        ),
        "active_users_24h": _fetch_count(
            "SELECT COUNT(DISTINCT user_id) FROM quiz_sessions WHERE started_at >= ?", (cutoffs[1],)
        ),
        "active_users_7d": _fetch_count(
            "SELECT COUNT(DISTINCT user_id) FROM quiz_sessions WHERE started_at >= ?", (cutoffs[7],)
        ),
        "active_users_30d": _fetch_count(
            "SELECT COUNT(DISTINCT user_id) FROM quiz_sessions WHERE started_at >= ?", (cutoffs[30],)
        ),
        "total_quiz_sessions": _fetch_count("SELECT COUNT(*) FROM quiz_sessions"),
        "completed_quiz_sessions": _fetch_count("SELECT COUNT(*) FROM quiz_sessions WHERE status = 'finished'"),
        "in_progress_quiz_sessions": _fetch_count(
            "SELECT COUNT(*) FROM quiz_sessions WHERE status = 'in_progress'"
        ),
        "total_quiz_answers": _fetch_count("SELECT COUNT(*) FROM quiz_answers"),
        "total_approved_questions": _fetch_count("SELECT COUNT(*) FROM questions WHERE status = 'approved'"),
        "active_categories_count": _fetch_count(
            """
            SELECT COUNT(*)
            FROM categories c
            WHERE EXISTS (
                SELECT 1 FROM questions q
                WHERE q.category_id = c.id
                  AND q.status = 'approved'
            )
            """
        ),
        "questions_by_category": [
            {
                "category_name": str(row["category_name"]),
                "question_count": int(row["question_count"]),
            }
            for row in questions_by_category_rows
        ],
        "top_categories_30d": [
            {
                "category_name": str(row["name"]),
                "started_sessions": int(row["started_sessions"]),
            }
            for row in top_categories_30d_rows
        ],
    }


OWNER_STATS_PERIODS = {"24h": 1, "7d": 7, "30d": 30}


def get_owner_period_stats(conn: Connection, period: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Aggregate learning activity for an allowed rolling UTC period, without identities."""
    if not isinstance(period, str) or period not in OWNER_STATS_PERIODS:
        raise ValueError("invalid_period")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = (current - timedelta(days=OWNER_STATS_PERIODS[period])).strftime("%Y-%m-%d %H:%M:%S")

    def count(query: str, *params: object) -> int:
        return int(conn.execute(query, params).fetchone()[0])

    # SQLite and PostgreSQL both store these UTC timestamps as text. Some
    # learning events use ISO's T separator; normalize only for comparison.
    active = count("""
        SELECT COUNT(DISTINCT user_id) FROM (
            SELECT user_id FROM quiz_sessions WHERE replace(substr(started_at,1,19),'T',' ') >= ?
            UNION ALL SELECT user_id FROM glossary_sessions WHERE replace(substr(created_at,1,19),'T',' ') >= ?
            UNION ALL SELECT user_id FROM user_review_events WHERE replace(substr(answered_at,1,19),'T',' ') >= ?
            UNION ALL SELECT user_id FROM user_literature_work_progress WHERE replace(substr(updated_at,1,19),'T',' ') >= ?
        ) activity
    """, cutoff, cutoff, cutoff, cutoff)
    return {
        "ok": True,
        "period": period,
        "active_users": active,
        "quiz_started": count("SELECT COUNT(*) FROM quiz_sessions WHERE started_at >= ?", cutoff),
        "quiz_completed": count("SELECT COUNT(*) FROM quiz_sessions WHERE status='finished' AND finished_at >= ?", cutoff),
        "quiz_answers": count("SELECT COUNT(*) FROM quiz_answers WHERE answered_at >= ?", cutoff),
        "glossary_started": count("SELECT COUNT(*) FROM glossary_sessions WHERE replace(substr(created_at,1,19),'T',' ') >= ?", cutoff),
        "glossary_completed": count("SELECT COUNT(*) FROM glossary_sessions WHERE status='completed' AND replace(substr(updated_at,1,19),'T',' ') >= ?", cutoff),
        "reading_items_updated": count("SELECT COUNT(*) FROM user_literature_work_progress WHERE replace(substr(updated_at,1,19),'T',' ') >= ?", cutoff),
    }
