from __future__ import annotations

import json
import re
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
    "curriculum_topic_ids",
)
PUBLIC_SOURCE_FIELDS = ("citation",)
def _valid_offer_target(provider: object, fmt: object, parsed) -> bool:
    if (parsed is None or parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        return False
    if provider == "Литрес":
        prefix = "/book/" if fmt == "text" else "/audiobook/"
        return parsed.netloc == "www.litres.ru" and parsed.path.startswith(prefix)
    if provider == "Юрайт":
        return fmt == "text" and parsed.netloc == "urait.ru" and re.fullmatch(r"/bcode/[0-9]+", parsed.path) is not None
    return False


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
            if (not isinstance(fmt, str) or fmt not in {"text", "audio"} or not isinstance(url, str) or url in seen
                    or offer["access"] != "provider_terms"
                    or not checked_date
                    or not _valid_offer_target(offer["provider"], fmt, parsed)):
                raise ValueError("Invalid literature access offer")
            seen.add(url)
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


def literature_curriculum_topics(entry: dict[str, Any]) -> list[dict[str, str]]:
    """Expose only explicitly reviewed lesson IDs, never source metadata.

    The optional field is part of the publication fingerprint. A discipline
    reading list without a lesson binding stays discipline-wide.
    """
    ids = entry.get("curriculum_topic_ids", [])
    if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("Invalid literature curriculum topics")
    if not ids:
        return []
    from app.curriculum import load_catalog
    topics = load_catalog()["topics"]
    private_labels = entry.get("reviewed_curriculum_topics", [])
    if (not isinstance(private_labels, list)
            or any(not isinstance(value, dict) or set(value) != {"id", "title", "discipline_id"}
                   or not isinstance(value["id"], str) or re.fullmatch(r"t_[0-9a-f]{12}", value["id"]) is None
                   or not isinstance(value["title"], str) or not value["title"].strip()
                   or value["discipline_id"] != entry.get("topic_id") for value in private_labels)
            or len({value["id"] for value in private_labels}) != len(private_labels)
            or any(value["id"] not in ids for value in private_labels)):
        raise ValueError("Invalid private literature lesson labels")
    if private_labels and ("source_refs" in entry or "source_ref" in entry
                           or not load_policy().can_publish("literature", entry)):
        raise ValueError("Signed private literature lesson labels required")
    labels = {value["id"]: value for value in private_labels}
    result = []
    for value in ids:
        topic = topics.get(value) or labels.get(value)
        if topic is None or topic["discipline_id"] != entry.get("topic_id"):
            raise ValueError("Literature curriculum discipline mismatch")
        if value in topics and value in labels and topic["title"] != labels[value]["title"]:
            raise ValueError("Literature curriculum title mismatch")
        result.append({"id": value, "title": topic["title"]})
    return result


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
            item["curriculum_topics"] = literature_curriculum_topics(entry)
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
            "module": str(topic.get("module") or ""),
            "item_count": len(topic_items),
            "status_counts": dict(sorted(Counter(str(item.get("status")) for item in topic_items).items())),
        }
        if reading_status_counts:
            payload["user_reading_status_counts"] = dict(sorted(reading_status_counts.items()))
        payloads.append(payload)
    return sorted(payloads, key=lambda payload: (int(topics.get(str(payload["topic_id"]), {}).get("order") or 0), str(payload["topic_id"])))
