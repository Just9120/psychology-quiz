#!/usr/bin/env python3
"""Validate static glossary JSON files against the topic registry."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

GLOSSARY_FILES_GLOB = "content/glossary/*.json"
TOPICS_FILE = Path("content/topics.json")
REQUIRED_FIELDS = {
    "id",
    "topic_id",
    "term",
    "aliases",
    "definition",
    "short_definition",
    "examples",
    "confusable_with",
    "source_refs",
    "difficulty",
    "status",
}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
VALID_STATUSES = {"approved", "draft", "review", "deprecated", "placeholder"}
ID_RE = re.compile(r"^[a-z0-9_]+$")


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
        if not entry_id.startswith("qual_methods_"):
            errors.append(f"{label}: id must use the qual_methods_ prefix: {entry_id}")
        if entry_id in seen_ids:
            errors.append(f"{label}: duplicate id '{entry_id}' also found at {seen_ids[entry_id]}")
        else:
            seen_ids[entry_id] = label

    topic_id = entry.get("topic_id")
    if not is_non_empty_string(topic_id):
        errors.append(f"{label}: topic_id must be a non-empty string")
    else:
        if topic_id != file_topic_id:
            errors.append(f"{label}: topic_id '{topic_id}' must match glossary filename topic '{file_topic_id}'")
        if topic_id not in active_topic_ids:
            errors.append(f"{label}: topic_id '{topic_id}' is not an active topic in {TOPICS_FILE}")

    for field in ("term", "definition", "short_definition"):
        if field in entry and not is_non_empty_string(entry.get(field)):
            errors.append(f"{label}: {field} must be a non-empty string")

    validate_string_list(entry.get("aliases"), "aliases", label, errors, require_non_empty=False)
    validate_string_list(entry.get("examples"), "examples", label, errors, require_non_empty=True)
    validate_string_list(entry.get("confusable_with"), "confusable_with", label, errors, require_non_empty=False)
    validate_string_list(entry.get("source_refs"), "source_refs", label, errors, require_non_empty=True)

    difficulty = entry.get("difficulty")
    if difficulty not in VALID_DIFFICULTIES:
        errors.append(f"{label}: difficulty must be one of {', '.join(sorted(VALID_DIFFICULTIES))}")

    status = entry.get("status")
    if status not in VALID_STATUSES:
        errors.append(f"{label}: status must be one of {', '.join(sorted(VALID_STATUSES))}")
    elif status == "approved" and not entry.get("source_refs"):
        errors.append(f"{label}: approved entries must include at least one source_ref")


def validate() -> list[str]:
    errors: list[str] = []
    active_topic_ids = load_active_topic_ids(errors)
    glossary_files = sorted(Path(".").glob(GLOSSARY_FILES_GLOB))
    if not glossary_files:
        errors.append(f"No glossary files found with glob: {GLOSSARY_FILES_GLOB}")
        return errors

    seen_ids: dict[str, str] = {}
    for path in glossary_files:
        raw_data = load_json(path, errors, str(path))
        if raw_data is None:
            continue
        if not isinstance(raw_data, list):
            errors.append(f"{path}: top-level value must be a list")
            continue

        file_topic_id = path.stem
        if file_topic_id not in active_topic_ids:
            errors.append(f"{path}: filename topic '{file_topic_id}' is not an active topic in {TOPICS_FILE}")

        for idx, entry in enumerate(raw_data):
            label = f"{path}[{idx}]"
            if not isinstance(entry, dict):
                errors.append(f"{label}: glossary entry must be an object")
                continue
            validate_entry(entry, label, file_topic_id, active_topic_ids, seen_ids, errors)

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Glossary validation failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Glossary validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
