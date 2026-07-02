#!/usr/bin/env python3
"""Validate static literature JSON files against the topic registry."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

LITERATURE_FILES_GLOB = "content/literature/*.json"
TOPICS_FILE = Path("content/topics.json")
REQUIRED_FIELDS = {
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
    "source_refs",
    "notes",
}
VALID_TYPES = {"book", "article", "chapter", "course_material", "video", "other"}
VALID_READING_LEVELS = {"foundation", "core", "applied", "deepening", "advanced", "reference"}
VALID_STATUSES = {"draft", "review", "approved", "deprecated", "placeholder"}
USER_READING_STATUSES = {"not_started", "in_progress", "read", "revisit", "skipped"}
VALID_PRIORITIES = {"low", "medium", "high"}
ID_RE = re.compile(r"^[a-z0-9_]+$")
TAG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def load_json(path: Path, errors: list[str], label: str) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{label}: file not found: {path}")
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: invalid JSON ({exc})")
    return None


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load_active_topic_ids(errors: list[str]) -> set[str]:
    topics = load_json(TOPICS_FILE, errors, str(TOPICS_FILE))
    if topics is None:
        return set()
    if not isinstance(topics, list):
        errors.append(f"{TOPICS_FILE}: top-level value must be a list")
        return set()

    topic_ids: set[str] = set()
    for idx, topic in enumerate(topics):
        label = f"{TOPICS_FILE}[{idx}]"
        if not isinstance(topic, dict):
            errors.append(f"{label}: topic must be an object")
            continue
        topic_id = topic.get("id")
        if topic.get("status") == "active" and is_non_empty_string(topic_id):
            topic_ids.add(topic_id)
    return topic_ids


def validate_string_list(value: Any, field: str, label: str, errors: list[str], *, require_non_empty: bool) -> None:
    if not isinstance(value, list):
        errors.append(f"{label}: {field} must be a list")
        return
    if require_non_empty and not value:
        errors.append(f"{label}: {field} must contain at least one item")
    for item_idx, item in enumerate(value):
        if not is_non_empty_string(item):
            errors.append(f"{label}: {field}[{item_idx}] must be a non-empty string")


def validate_positive_int(value: Any, field: str, label: str, errors: list[str]) -> None:
    if type(value) is not int or value <= 0:
        errors.append(f"{label}: {field} must be a positive integer")


def validate_entry(
    entry: dict[str, Any],
    label: str,
    file_topic_id: str,
    active_topic_ids: set[str],
    seen_ids: dict[str, str],
    errors: list[str],
) -> None:
    missing = sorted(REQUIRED_FIELDS - entry.keys())
    if missing:
        errors.append(f"{label}: missing required fields: {', '.join(missing)}")

    entry_id = entry.get("id")
    if not is_non_empty_string(entry_id):
        errors.append(f"{label}: id must be a non-empty string")
    else:
        if not entry_id.isascii() or entry_id.lower() != entry_id or not ID_RE.match(entry_id):
            errors.append(f"{label}: id must be lowercase ASCII and match ^[a-z0-9_]+$: {entry_id}")
        if entry_id in seen_ids:
            errors.append(f"{label}: duplicate id '{entry_id}' also found at {seen_ids[entry_id]}")
        else:
            seen_ids[entry_id] = label

    topic_id = entry.get("topic_id")
    if not is_non_empty_string(topic_id):
        errors.append(f"{label}: topic_id must be a non-empty string")
    else:
        if topic_id != file_topic_id:
            errors.append(f"{label}: topic_id '{topic_id}' must match literature filename topic '{file_topic_id}'")
        if topic_id not in active_topic_ids:
            errors.append(f"{label}: topic_id '{topic_id}' is not an active topic in {TOPICS_FILE}")

    for field in ("title", "notes"):
        if field in entry and not isinstance(entry.get(field), str):
            errors.append(f"{label}: {field} must be a string")

    validate_string_list(entry.get("authors"), "authors", label, errors, require_non_empty=True)

    year = entry.get("year")
    if year is not None and (type(year) is not int or year < 1800 or year > 2100):
        errors.append(f"{label}: year must be an integer between 1800 and 2100 or null")

    item_type = entry.get("type")
    if item_type not in VALID_TYPES:
        errors.append(f"{label}: type must be one of {', '.join(sorted(VALID_TYPES))}")

    reading_level = entry.get("reading_level")
    if reading_level not in VALID_READING_LEVELS:
        errors.append(f"{label}: reading_level must be one of {', '.join(sorted(VALID_READING_LEVELS))}")

    status = entry.get("status")
    if status in USER_READING_STATUSES:
        errors.append(
            f"{label}: status '{status}' is a per-user reading state; "
            "repository literature content must use static lifecycle statuses only"
        )
    elif status not in VALID_STATUSES:
        errors.append(f"{label}: status must be one of {', '.join(sorted(VALID_STATUSES))}")

    priority = entry.get("priority")
    if priority not in VALID_PRIORITIES:
        errors.append(f"{label}: priority must be one of {', '.join(sorted(VALID_PRIORITIES))}")

    validate_positive_int(entry.get("topic_order"), "topic_order", label, errors)
    validate_positive_int(entry.get("global_order"), "global_order", label, errors)

    estimated_minutes = entry.get("estimated_minutes")
    if estimated_minutes is not None and (type(estimated_minutes) is not int or estimated_minutes <= 0):
        errors.append(f"{label}: estimated_minutes must be a positive integer or null")

    tags = entry.get("tags")
    if not isinstance(tags, list):
        errors.append(f"{label}: tags must be a list")
    else:
        for tag_idx, tag in enumerate(tags):
            if not is_non_empty_string(tag):
                errors.append(f"{label}: tags[{tag_idx}] must be a non-empty string")
            elif not tag.isascii() or not TAG_RE.match(tag):
                errors.append(f"{label}: tags[{tag_idx}] must be lowercase ASCII snake_case: {tag}")

    if not is_non_empty_string(entry.get("why_read")):
        errors.append(f"{label}: why_read must be a non-empty string")

    validate_string_list(
        entry.get("learning_outcomes"),
        "learning_outcomes",
        label,
        errors,
        require_non_empty=True,
    )

    prerequisites = entry.get("prerequisites")
    if not isinstance(prerequisites, list):
        errors.append(f"{label}: prerequisites must be a list")
    else:
        for prerequisite_idx, prerequisite in enumerate(prerequisites):
            if not is_non_empty_string(prerequisite):
                errors.append(f"{label}: prerequisites[{prerequisite_idx}] must be a non-empty literature entry id")
            elif prerequisite == entry_id:
                errors.append(f"{label}: prerequisites[{prerequisite_idx}] must not reference the entry itself")

    source_refs = entry.get("source_refs")
    if not isinstance(source_refs, list):
        errors.append(f"{label}: source_refs must be a list")
    elif not source_refs:
        errors.append(f"{label}: source_refs must contain at least one item for real reading entries")
    else:
        for ref_idx, source_ref in enumerate(source_refs):
            if not is_non_empty_string(source_ref):
                errors.append(f"{label}: source_refs[{ref_idx}] must be a non-empty string")


def validate() -> list[str]:
    errors: list[str] = []
    active_topic_ids = load_active_topic_ids(errors)
    literature_files = sorted(Path(".").glob(LITERATURE_FILES_GLOB))
    if not literature_files:
        errors.append(f"No literature files found with glob: {LITERATURE_FILES_GLOB}")
        return errors

    seen_ids: dict[str, str] = {}
    seen_global_orders: dict[int, str] = {}
    prerequisite_refs: list[tuple[str, str]] = []
    for path in literature_files:
        raw_data = load_json(path, errors, str(path))
        if raw_data is None:
            continue
        if not isinstance(raw_data, list):
            errors.append(f"{path}: top-level value must be a list")
            continue

        file_topic_id = path.stem
        if file_topic_id not in active_topic_ids:
            errors.append(f"{path}: filename topic '{file_topic_id}' is not an active topic in {TOPICS_FILE}")

        seen_topic_orders: dict[int, str] = {}
        for idx, entry in enumerate(raw_data):
            label = f"{path}[{idx}]"
            if not isinstance(entry, dict):
                errors.append(f"{label}: literature entry must be an object")
                continue
            validate_entry(entry, label, file_topic_id, active_topic_ids, seen_ids, errors)

            topic_order = entry.get("topic_order")
            if type(topic_order) is int:
                if topic_order in seen_topic_orders:
                    errors.append(
                        f"{label}: duplicate topic_order '{topic_order}' also found at {seen_topic_orders[topic_order]}"
                    )
                else:
                    seen_topic_orders[topic_order] = label

            global_order = entry.get("global_order")
            if type(global_order) is int:
                if global_order in seen_global_orders:
                    errors.append(
                        f"{label}: duplicate global_order '{global_order}' also found at "
                        f"{seen_global_orders[global_order]}"
                    )
                else:
                    seen_global_orders[global_order] = label

            prerequisites = entry.get("prerequisites")
            if isinstance(prerequisites, list):
                for prerequisite in prerequisites:
                    if is_non_empty_string(prerequisite):
                        prerequisite_refs.append((label, prerequisite))

    for label, prerequisite in prerequisite_refs:
        if prerequisite not in seen_ids:
            errors.append(f"{label}: prerequisite '{prerequisite}' does not match any literature entry id")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Literature validation failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Literature validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
