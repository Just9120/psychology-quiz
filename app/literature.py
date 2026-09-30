from __future__ import annotations

import json
from copy import deepcopy
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from app.content_publication import load_policy

ROOT = Path(__file__).resolve().parents[1]
LITERATURE_DIR = ROOT / "content/literature"
TOPICS_FILE = ROOT / "content/topics.json"
ACCESS_FILE = ROOT / "content/literature-access.json"
PUBLIC_ITEM_FIELDS = (
    "work_id", "module", "content_access", "metadata_warnings",
    "id",
    "topic_id",
    "title",
    "authors",
    "year",
    "type",
    "reading_level",
    "status",
    "priority", "importance", "importance_source",
    "topic_order",
    "global_order",
    "estimated_minutes",
    "tags",
    "why_read",
    "learning_outcomes",
    "prerequisites",
)
PUBLIC_SOURCE_FIELDS = ("citation",)
@lru_cache(maxsize=1)
def load_access_links() -> dict[str, list[dict[str, str]]]:
    """Curated outbound offers; a link never means that the user owns a copy."""
    raw = _load_json_file(ACCESS_FILE)
    if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("works"), dict):
        raise ValueError("Invalid literature access catalog")
    links: dict[str, list[dict[str, str]]] = {}
    for work_id, offers in raw["works"].items():
        if not isinstance(work_id, str) or not isinstance(offers, list):
            raise ValueError("Invalid literature access entry")
        seen: set[str] = set()
        links[work_id] = []
        for offer in offers:
            if not isinstance(offer, dict) or set(offer) != {"format", "provider", "url", "access", "checked_at"}:
                raise ValueError("Invalid literature access offer")
            fmt, url = offer["format"], offer["url"]
            parsed = urlsplit(url) if isinstance(url, str) else None
            checked = offer["checked_at"]
            try:
                checked_date = isinstance(checked, str) and date.fromisoformat(checked).isoformat() == checked
            except ValueError:
                checked_date = False
            if (not isinstance(fmt, str) or fmt not in {"text", "audio"} or fmt in seen
                    or offer["provider"] != "Литрес" or offer["access"] != "provider_terms"
                    or not checked_date
                    or parsed is None or parsed.scheme != "https" or parsed.hostname != "www.litres.ru"
                    or parsed.netloc != "www.litres.ru" or parsed.username or parsed.password
                    or parsed.query or parsed.fragment
                    or not parsed.path.startswith("/book/" if fmt == "text" else "/audiobook/")):
                raise ValueError("Invalid literature access offer")
            seen.add(fmt)
            links[work_id].append(offer)
    return links


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
    item = {field: entry.get(field) for field in PUBLIC_ITEM_FIELDS}
    source = entry.get("source")
    item["source"] = (
        {field: source.get(field) for field in PUBLIC_SOURCE_FIELDS}
        if isinstance(source, dict) else None
    )
    return item


@lru_cache(maxsize=4)
def _published_literature_items(directory: Path) -> tuple[dict[str, Any], ...]:
    """Content is immutable within one deployed process; a new deploy restarts it."""
    items: list[dict[str, Any]] = []
    publication = load_policy()
    access_links = load_access_links()
    for path in sorted(directory.glob("*.json")):
        raw_items = _load_json_file(path)
        if not isinstance(raw_items, list):
            continue
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            if not publication.can_publish("literature", entry):
                continue
            item = _public_literature_item(entry)
            item["access_links"] = access_links.get(item["work_id"], [])
            items.append(item)
    return tuple(sorted(items, key=lambda item: (int(item.get("global_order") or 0), str(item.get("id") or ""))))


def load_literature_items(topic_id: str | None = None) -> list[dict[str, Any]]:
    items = _published_literature_items(LITERATURE_DIR)
    selected = (item for item in items if topic_id is None or item.get("topic_id") == topic_id)
    if topic_id is None:
        return [deepcopy(item) for item in selected]
    return sorted((deepcopy(item) for item in selected),
                  key=lambda item: (int(item.get("topic_order") or 0), str(item.get("id") or "")))


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
