from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from app.content_publication import load_policy

LITERATURE_DIR = Path("content/literature")
TOPICS_FILE = Path("content/topics.json")
PUBLIC_ITEM_FIELDS = (
    "work_id", "module", "source", "content_access", "metadata_warnings",
    "id",
    "topic_id",
    "title",
    "authors",
    "year",
    "type",
    "reading_level",
    "status",
    "priority",
    "topic_order",
    "global_order",
    "estimated_minutes",
    "tags",
    "why_read",
    "learning_outcomes",
    "prerequisites",
)
USER_STATE_FIELDS = (
    "reading_status",
    "progress_percent",
    "started_at",
    "completed_at",
    "updated_at",
    "last_opened_at",
    "remind_at",
)


def _load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_topic_registry() -> dict[str, dict[str, Any]]:
    raw_topics = _load_json_file(TOPICS_FILE)
    if not isinstance(raw_topics, list):
        return {}
    topics: dict[str, dict[str, Any]] = {}
    for topic in raw_topics:
        if not isinstance(topic, dict):
            continue
        topic_id = topic.get("id")
        if isinstance(topic_id, str) and topic.get("status") == "active":
            topics[topic_id] = topic
    return topics


def _public_literature_item(entry: dict[str, Any]) -> dict[str, Any]:
    return {field: entry.get(field) for field in PUBLIC_ITEM_FIELDS}


def load_literature_items(topic_id: str | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    publication = load_policy()
    for path in sorted(LITERATURE_DIR.glob("*.json")):
        raw_items = _load_json_file(path)
        if not isinstance(raw_items, list):
            continue
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            if not publication.can_publish("literature", entry):
                continue
            if topic_id is not None and entry.get("topic_id") != topic_id:
                continue
            items.append(_public_literature_item(entry))
    if topic_id is None:
        return sorted(items, key=lambda item: (int(item.get("global_order") or 0), str(item.get("id") or "")))
    return sorted(items, key=lambda item: (int(item.get("topic_order") or 0), str(item.get("id") or "")))


def list_literature_topic_payloads(user_states: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    topics = load_topic_registry()
    items = load_literature_items()
    by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        item_topic_id = item.get("topic_id")
        if isinstance(item_topic_id, str):
            by_topic[item_topic_id].append(item)

    payloads: list[dict[str, Any]] = []
    user_states = user_states or {}
    for topic_id, topic_items in by_topic.items():
        topic = topics.get(topic_id, {})
        literature_ids = {str(item.get("id")) for item in topic_items if isinstance(item.get("id"), str)}
        reading_status_counts = Counter(
            str(state.get("reading_status"))
            for literature_id, state in user_states.items()
            if literature_id in literature_ids and isinstance(state.get("reading_status"), str)
        )
        payload: dict[str, Any] = {
            "topic_id": topic_id,
            "title": str(topic.get("title") or topic_id),
            "item_count": len(topic_items),
            "status_counts": dict(sorted(Counter(str(item.get("status")) for item in topic_items).items())),
        }
        if reading_status_counts:
            payload["user_reading_status_counts"] = dict(sorted(reading_status_counts.items()))
        payloads.append(payload)
    return sorted(payloads, key=lambda payload: (int(topics.get(str(payload["topic_id"]), {}).get("order") or 0), str(payload["topic_id"])))


def state_row_to_payload(row: Any) -> dict[str, Any]:
    payload = {"literature_id": str(row["literature_id"])}
    for field in USER_STATE_FIELDS:
        payload[field] = row[field]
    return payload


def state_row_to_item_user_state(row: Any) -> dict[str, Any]:
    return {field: row[field] for field in USER_STATE_FIELDS}
