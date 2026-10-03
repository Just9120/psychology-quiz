"""Reading state shared by authenticated PWA and Telegram adapters.

An entry identifies a reading-list association; personal status belongs to its proven work identity.
Legacy association rows remain unchanged migration history.
"""
from datetime import datetime, timezone
from typing import Any
from app.database import begin_write
from app.reading_schema import STATUS_MAP
READING_STATUSES = frozenset(STATUS_MAP.values())
from app.literature import load_literature_items, load_topic_registry


def reading_summary(items: list[dict], states: dict) -> dict:
    """Count works in the selected scope without resolving legacy state conflicts."""
    works = {}
    for item in items:
        works.setdefault(item.get("work_id", item["id"]), []).append(item)
    read, conflicts, current = 0, 0, []
    for entries in works.values():
        statuses = {states.get(item["id"], {}).get("reading_status", "not_started") for item in entries}
        read += statuses == {"read"}
        conflicts += len(statuses) > 1
        reading = next((item for item in entries if states.get(item["id"], {}).get("reading_status") == "in_progress"), None)
        if reading:
            current.append(reading)
    return {"read": read, "total": len(works), "conflicts": conflicts, "current": current}


def reading_continuation_reason(item: dict) -> str:
    if item.get("type") == "video":
        return "Вы уже начали этот видеоматериал. Продолжите просмотр перед выбором следующего."
    if item.get("type") in {"article", "chapter", "other"}:
        return "Вы уже начали этот материал. Продолжите работу с ним перед выбором следующего."
    return "Вы уже начали эту книгу. Продолжите чтение перед выбором следующей."


def reading_next_step(items: list[dict], states: dict, all_items: list[dict] | None = None) -> dict | None:
    """Continue started reading, then use explicitly reviewed recommendation metadata.

    Conflicting association states require a decision before a recommendation.
    Only canonical UTC timestamps rank recency; missing dates tie by stable ID.
    """
    works = {}
    for item in items:
        works.setdefault(item.get("work_id", item["id"]), []).append(item)
    candidates = []
    for entries in works.values():
        if {states.get(item["id"], {}).get("reading_status", "not_started")
                for item in entries} == {"in_progress"}:
            candidates.extend(entries)
    def recency(item):
        value = states.get(item["id"], {}).get("updated_at")
        if not isinstance(value, str) or len(value) != 20 or not value.endswith("Z"):
            return ""
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
        return value if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value else ""
    if not candidates:
        known = {item["id"]: item for item in (all_items if all_items is not None else items)}
        all_works = {}
        for item in known.values():
            all_works.setdefault(item.get("work_id", item["id"]), []).append(item)
        def status(item):
            return states.get(item["id"], {}).get("reading_status", "not_started")
        def completed(reference):
            prerequisite = known.get(reference)
            if prerequisite is None:
                return False
            group = all_works[prerequisite.get("work_id", prerequisite["id"])]
            return all(status(item) == "read" for item in group)
        rank = {"basic": 0, "important": 1, "additional": 2, "advanced": 3}
        stages = {"foundation": 0, "core": 1, "applied": 2,
                  "deepening": 3, "advanced": 4, "reference": 5}
        recommendations = []
        for item in items:
            group = all_works.get(item.get("work_id", item["id"]), [])
            prerequisites = item.get("prerequisites")
            if (not group or any(status(entry) != "not_started" for entry in group)
                    or item.get("importance") not in rank
                    or item.get("importance_source") not in {"agent", "teacher"}
                    or item.get("reading_level") not in stages
                    or not isinstance(item.get("why_read"), str) or not item["why_read"].strip()
                    or not isinstance(prerequisites, list)
                    or not all(isinstance(ref, str) and completed(ref) for ref in prerequisites)):
                continue
            recommendations.append(item)
        if not recommendations:
            return None
        # Reviewed stages resolve equal priority, never arbitrary bibliography order.
        recommendations.sort(key=lambda item: (rank[item["importance"]],
                             stages[item["reading_level"]], str(item["id"])))
        item = recommendations[0]
        reason = f"Рекомендация агента. {item['why_read']}"
        if item["importance_source"] == "teacher":
            reason += (" Приоритет материала — из учебного списка." if item.get("type") in {"video", "article", "chapter", "other"} else " Приоритет книги — из учебного списка.")
        return {"item": item, "kind": "start", "reason": reason,
                "basis": "agent", "priority_source": item["importance_source"]}
    # Two stable sorts avoid deriving a preference from bibliography position.
    candidates.sort(key=lambda item: str(item["id"]))
    candidates.sort(key=recency, reverse=True)
    return {"item": candidates[0], "kind": "continue",
            "reason": reading_continuation_reason(candidates[0]),
            "basis": "personal_reading_state"}


def catalog(conn, actor_user_id: int) -> dict[str, Any]:
    states = load_progress(conn, actor_user_id)
    topics = load_topic_registry()
    works: dict[str, dict] = {}
    used_topics: set[str] = set()
    for item in load_literature_items():
        work_id = item["work_id"]
        work = works.setdefault(work_id, {"work_id": work_id, "title": item["title"],
            "authors": item["authors"], "type": item["type"],
            "access_links": item["access_links"], "book_search": item["book_search"], "entries": []})
        used_topics.add(item["topic_id"])
        work["entries"].append({**item, "topic_title": topics[item["topic_id"]]["title"],
            "user_state": states.get(item["id"])})
    return {"ok": True, "works": list(works.values()), "topics": [
        {"topic_id": topic_id, "title": topic["title"], "module": topic["module"],
         "modules": topic.get("modules", [topic["module"]])}
        for topic_id, topic in sorted(topics.items(), key=lambda pair: pair[1]["order"])
        if topic_id in used_topics]}

def _state_payload(row, literature_id: str) -> dict:
    return {"literature_id": literature_id, "work_id": row["work_id"],
            "reading_status": row["reading_status"], "progress_percent": None,
            "started_at": row["started_at"], "completed_at": row["completed_at"],
            "updated_at": row["updated_at"], "last_opened_at": row["last_opened_at"],
            "remind_at": None}


def load_progress(conn, actor_user_id: int) -> dict[str, dict[str, Any]]:
    states = {row["work_id"]: row for row in conn.execute(
        "SELECT * FROM user_literature_work_progress WHERE user_id=? ORDER BY updated_at DESC,work_id",
        (actor_user_id,))}
    return {item["id"]: _state_payload(states[item["work_id"]], item["id"])
            for item in load_literature_items() if item["work_id"] in states}


def load_item_states(conn, actor_user_id: int) -> dict[str, dict[str, Any]]:
    return load_progress(conn, actor_user_id)


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
    if not isinstance(reading_status, str) or reading_status not in READING_STATUSES:
        return "invalid_reading_status"

    if payload.get("progress_percent") is not None:
        return "manual_progress_not_supported"
    return literature_id, str(reading_status), None


def save_progress(conn, actor_user_id: int, literature_id: str, reading_status: str, progress_percent: int | None) -> dict[str, Any]:
    if reading_status not in READING_STATUSES:
        raise ValueError("invalid_reading_status")
    if progress_percent is not None:
        raise ValueError("manual_progress_not_supported")
    item = next((item for item in load_literature_items() if item["id"] == literature_id), None)
    if item is None:
        raise ValueError("unknown_literature_id")
    work_id = item["work_id"]
    begin_write(conn, f"actor:{actor_user_id}")
    existing = conn.execute(
        "SELECT * FROM user_literature_work_progress WHERE user_id=? AND work_id=?",
        (actor_user_id, work_id)).fetchone()
    now = _utc_timestamp()
    started = existing["started_at"] if existing is not None else None
    completed = existing["completed_at"] if existing is not None else None
    opened = existing["last_opened_at"] if existing is not None else None
    if reading_status == "not_started":
        started = completed = opened = None
    elif reading_status in {"read", "in_progress"}:
        started = started or now
        opened = now
        if reading_status == "read":
            if existing is None or existing["reading_status"] != "read" or not completed:
                completed = now
        else:
            completed = None
    else:
        completed = None
    conn.execute("""INSERT INTO user_literature_work_progress
        (user_id,work_id,reading_status,started_at,completed_at,updated_at,last_opened_at,source_literature_id)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user_id,work_id) DO UPDATE SET
        reading_status=excluded.reading_status,started_at=excluded.started_at,
        completed_at=excluded.completed_at,updated_at=excluded.updated_at,
        last_opened_at=excluded.last_opened_at,source_literature_id=excluded.source_literature_id""",
        (actor_user_id, work_id, reading_status, started, completed, now, opened, literature_id))
    row = conn.execute("SELECT * FROM user_literature_work_progress WHERE user_id=? AND work_id=?",
                       (actor_user_id, work_id)).fetchone()
    return _state_payload(row, literature_id)
