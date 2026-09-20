"""Reading state shared by authenticated PWA and Telegram adapters.

An entry identifies a reading list association. Grouping works never merges personal state.
"""
from datetime import datetime, timezone
from typing import Any
from app.database import begin_write
from app.db import USER_LITERATURE_READING_STATUSES
from app.literature import load_literature_items, load_topic_registry, state_row_to_payload, state_row_to_item_user_state


def catalog(conn, actor_user_id: int) -> dict[str, Any]:
    states = load_progress(conn, actor_user_id)
    topics = load_topic_registry()
    works: dict[str, dict] = {}
    used_topics: set[str] = set()
    for item in load_literature_items():
        work_id = item["work_id"]
        work = works.setdefault(work_id, {"work_id": work_id, "title": item["title"],
            "authors": item["authors"], "type": item["type"], "entries": []})
        used_topics.add(item["topic_id"])
        work["entries"].append({**item, "topic_title": topics[item["topic_id"]]["title"],
            "user_state": states.get(item["id"])})
    return {"ok": True, "works": list(works.values()), "topics": [
        {"topic_id": topic_id, "title": topic["title"], "module": topic["module"]}
        for topic_id, topic in sorted(topics.items(), key=lambda pair: pair[1]["order"])
        if topic_id in used_topics]}

def load_progress(conn, actor_user_id: int) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT literature_id, reading_status, progress_percent, started_at, completed_at, updated_at, last_opened_at, remind_at
        FROM user_literature_progress
        WHERE user_id = ?
        ORDER BY updated_at DESC, literature_id ASC
        """,
        (actor_user_id,),
    ).fetchall()
    return {str(row["literature_id"]): state_row_to_payload(row) for row in rows}


def load_item_states(conn, actor_user_id: int) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT literature_id, reading_status, progress_percent, started_at, completed_at, updated_at, last_opened_at, remind_at
        FROM user_literature_progress
        WHERE user_id = ?
        """,
        (actor_user_id,),
    ).fetchall()
    return {str(row["literature_id"]): state_row_to_item_user_state(row) for row in rows}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _known_literature_ids() -> set[str]:
    return {str(item["id"]) for item in load_literature_items() if isinstance(item.get("id"), str)}


def validate_progress(payload: dict[str, Any]) -> tuple[str, str, int | None] | str:
    literature_id = payload.get("literature_id")
    if not isinstance(literature_id, str) or not literature_id.strip():
        return "invalid_literature_id"
    literature_id = literature_id.strip()
    if literature_id not in _known_literature_ids():
        return "unknown_literature_id"

    reading_status = payload.get("reading_status")
    if not isinstance(reading_status, str) or reading_status not in USER_LITERATURE_READING_STATUSES:
        return "invalid_reading_status"

    progress_percent = payload.get("progress_percent")
    if progress_percent is None:
        return literature_id, str(reading_status), None
    if type(progress_percent) is not int or progress_percent < 0 or progress_percent > 100:
        return "invalid_progress_percent"
    return literature_id, str(reading_status), progress_percent


def _build_literature_progress_values(existing: Any, reading_status: str, requested_progress: int | None, now: str) -> dict[str, Any]:
    existing_status = existing["reading_status"] if existing is not None else None
    existing_progress = existing["progress_percent"] if existing is not None else None
    existing_started = existing["started_at"] if existing is not None else None
    existing_completed = existing["completed_at"] if existing is not None else None
    existing_last_opened = existing["last_opened_at"] if existing is not None else None

    progress_percent = requested_progress
    started_at = existing_started
    completed_at = existing_completed
    last_opened_at = existing_last_opened

    if reading_status == "read":
        progress_percent = 100
        started_at = started_at or now
        if not completed_at or existing_status != "read":
            completed_at = now
        last_opened_at = now
    elif reading_status == "not_started":
        progress_percent = 0
        started_at = None
        completed_at = None
        last_opened_at = None
    else:
        if progress_percent is None:
            progress_percent = existing_progress
        if reading_status in {"in_progress", "revisit"}:
            started_at = started_at or now
            last_opened_at = now
        elif reading_status == "skipped":
            completed_at = None

    return {
        "reading_status": reading_status,
        "progress_percent": progress_percent,
        "started_at": started_at,
        "completed_at": completed_at,
        "updated_at": now,
        "last_opened_at": last_opened_at,
    }


def save_progress(conn, actor_user_id: int, literature_id: str, reading_status: str, progress_percent: int | None) -> dict[str, Any]:
    begin_write(conn, f"actor:{actor_user_id}")
    existing = conn.execute(
        """
        SELECT reading_status, progress_percent, started_at, completed_at, last_opened_at
        FROM user_literature_progress
        WHERE user_id = ? AND literature_id = ?
        LIMIT 1
        """,
        (actor_user_id, literature_id),
    ).fetchone()
    values = _build_literature_progress_values(existing, reading_status, progress_percent, _utc_timestamp())
    conn.execute(
        """
        INSERT INTO user_literature_progress (
            user_id, literature_id, reading_status, progress_percent,
            started_at, completed_at, updated_at, last_opened_at, remind_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT(user_id, literature_id) DO UPDATE SET
            reading_status = excluded.reading_status,
            progress_percent = excluded.progress_percent,
            started_at = excluded.started_at,
            completed_at = excluded.completed_at,
            updated_at = excluded.updated_at,
            last_opened_at = excluded.last_opened_at
        """,
        (
            actor_user_id,
            literature_id,
            values["reading_status"],
            values["progress_percent"],
            values["started_at"],
            values["completed_at"],
            values["updated_at"],
            values["last_opened_at"],
        ),
    )
    row = conn.execute(
        """
        SELECT literature_id, reading_status, progress_percent, started_at, completed_at, updated_at, last_opened_at, remind_at
        FROM user_literature_progress
        WHERE user_id = ? AND literature_id = ?
        LIMIT 1
        """,
        (actor_user_id, literature_id),
    ).fetchone()
    return state_row_to_payload(row)
