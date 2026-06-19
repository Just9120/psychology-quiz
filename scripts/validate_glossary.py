#!/usr/bin/env python3
"""Validate static glossary JSON files against the topic and question registries."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

GLOSSARY_FILES_GLOB = "content/glossary/*.json"
TOPICS_FILE = Path("content/topics.json")
REQUIRED_FIELDS = {
    "id", "topic_id", "term", "aliases", "definition", "short_definition",
    "examples", "confusable_with", "source_refs", "difficulty", "status",
}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
VALID_STATUSES = {"approved", "draft", "review", "deprecated", "placeholder"}
ID_RE = re.compile(r"^[a-z0-9_]+$")
QUESTION_REF_PREFIX = "question:"
SUPPORTED_SOURCE_REF_PREFIXES = (QUESTION_REF_PREFIX, "supplied_snippet:")
MIN_APPROVED_ENTRIES_PER_ACTIVE_TOPIC = 10


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


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def load_active_topics(errors: list[str]) -> dict[str, dict[str, Any]]:
    topics = load_json(TOPICS_FILE, errors, str(TOPICS_FILE))
    if topics is None:
        return {}
    if not isinstance(topics, list):
        errors.append(f"{TOPICS_FILE}: top-level value must be a list")
        return {}

    active_topics: dict[str, dict[str, Any]] = {}
    for idx, topic in enumerate(topics):
        label = f"{TOPICS_FILE}[{idx}]"
        if not isinstance(topic, dict):
            errors.append(f"{label}: topic must be an object")
            continue
        topic_id = topic.get("id")
        if topic.get("status") != "active":
            continue
        if not is_non_empty_string(topic_id):
            errors.append(f"{label}: active topic id must be a non-empty string")
            continue
        if "questions" not in topic.get("available_contours", []):
            continue
        if "glossary" not in topic.get("available_contours", []):
            errors.append(f"{label}: active question topic must include 'glossary' in available_contours")
        active_topics[topic_id] = topic
    return active_topics


def load_approved_questions(active_topics: dict[str, dict[str, Any]], errors: list[str]) -> dict[str, tuple[str, str]]:
    questions: dict[str, tuple[str, str]] = {}
    for topic_id, topic in active_topics.items():
        question_file = topic.get("question_file")
        title = topic.get("title")
        if not is_non_empty_string(question_file):
            errors.append(f"{TOPICS_FILE}:{topic_id}: question_file must be a non-empty string")
            continue
        if not is_non_empty_string(title):
            errors.append(f"{TOPICS_FILE}:{topic_id}: title must be a non-empty string")
            continue
        raw_questions = load_json(Path(question_file), errors, question_file)
        if raw_questions is None:
            continue
        if not isinstance(raw_questions, list):
            errors.append(f"{question_file}: top-level value must be a list")
            continue
        for idx, question in enumerate(raw_questions):
            label = f"{question_file}[{idx}]"
            if not isinstance(question, dict):
                errors.append(f"{label}: question must be an object")
                continue
            question_id = question.get("id")
            if question.get("status") == "approved" and is_non_empty_string(question_id):
                if question_id in questions:
                    errors.append(f"{label}: duplicate approved question id '{question_id}'")
                questions[question_id] = (topic_id, str(question.get("category", "")))
    return questions


def validate_string_list(value: Any, field: str, label: str, errors: list[str], *, require_non_empty: bool) -> None:
    if not isinstance(value, list):
        errors.append(f"{label}: {field} must be a list")
        return
    if require_non_empty and not value:
        errors.append(f"{label}: {field} must contain at least one item")
    for item_idx, item in enumerate(value):
        if not is_non_empty_string(item):
            errors.append(f"{label}: {field}[{item_idx}] must be a non-empty string")


def validate_entry(entry: dict[str, Any], label: str, file_topic_id: str, active_topics: dict[str, dict[str, Any]], approved_questions: dict[str, tuple[str, str]], seen_ids: dict[str, str], errors: list[str]) -> None:
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
            errors.append(f"{label}: topic_id '{topic_id}' must match glossary filename topic '{file_topic_id}'")
        if topic_id not in active_topics:
            errors.append(f"{label}: topic_id '{topic_id}' is not an active question topic in {TOPICS_FILE}")

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

    for source_ref in entry.get("source_refs", []):
        if not isinstance(source_ref, str):
            continue
        if not source_ref.startswith(SUPPORTED_SOURCE_REF_PREFIXES):
            errors.append(f"{label}: unsupported source_ref format: {source_ref}")
            continue
        if source_ref.startswith(QUESTION_REF_PREFIX):
            question_id = source_ref.removeprefix(QUESTION_REF_PREFIX)
            question_topic = approved_questions.get(question_id)
            if question_topic is None:
                errors.append(f"{label}: question source_ref does not resolve to an approved question: {source_ref}")
            elif question_topic[0] != file_topic_id:
                errors.append(f"{label}: question source_ref {source_ref} belongs to topic '{question_topic[0]}', not '{file_topic_id}'")


def validate_topic_entries(path: Path, raw_data: list[Any], active_topics: dict[str, dict[str, Any]], errors: list[str]) -> None:
    file_topic_id = path.stem
    approved_entries = [entry for entry in raw_data if isinstance(entry, dict) and entry.get("status") == "approved"]
    if len(approved_entries) < MIN_APPROVED_ENTRIES_PER_ACTIVE_TOPIC:
        errors.append(f"{path}: must contain at least {MIN_APPROVED_ENTRIES_PER_ACTIVE_TOPIC} approved entries")

    valid_ids = {entry.get("id") for entry in raw_data if isinstance(entry, dict) and is_non_empty_string(entry.get("id"))}
    seen_terms: dict[str, str] = {}
    seen_short_definitions: dict[str, str] = {}
    for idx, entry in enumerate(raw_data):
        if not isinstance(entry, dict):
            continue
        label = f"{path}[{idx}]"
        entry_id = entry.get("id")
        term = entry.get("term")
        short_definition = entry.get("short_definition")
        if is_non_empty_string(term):
            normalized_term = normalize_text(term)
            if normalized_term in seen_terms:
                errors.append(f"{label}: duplicate normalized term '{term}' also found at {seen_terms[normalized_term]}")
            else:
                seen_terms[normalized_term] = label
        if is_non_empty_string(short_definition):
            normalized_short_definition = normalize_text(short_definition)
            if normalized_short_definition in seen_short_definitions:
                errors.append(f"{label}: duplicate normalized short_definition also found at {seen_short_definitions[normalized_short_definition]}")
            else:
                seen_short_definitions[normalized_short_definition] = label
        for ref in entry.get("confusable_with", []):
            if ref == entry_id:
                errors.append(f"{label}: confusable_with must not reference the entry itself: {ref}")
            if ref not in valid_ids:
                errors.append(f"{label}: confusable_with reference does not exist in the same topic: {ref}")


def validate() -> list[str]:
    errors: list[str] = []
    active_topics = load_active_topics(errors)
    approved_questions = load_approved_questions(active_topics, errors)
    glossary_files = sorted(Path(".").glob(GLOSSARY_FILES_GLOB))
    if not glossary_files:
        errors.append(f"No glossary files found with glob: {GLOSSARY_FILES_GLOB}")
        return errors

    file_topic_ids = {path.stem for path in glossary_files}
    expected_topic_ids = set(active_topics)
    if file_topic_ids != expected_topic_ids:
        errors.append(
            "glossary files must exactly match active question topics: "
            f"missing={sorted(expected_topic_ids - file_topic_ids)}, extra={sorted(file_topic_ids - expected_topic_ids)}"
        )

    seen_ids: dict[str, str] = {}
    for path in glossary_files:
        raw_data = load_json(path, errors, str(path))
        if raw_data is None:
            continue
        if not isinstance(raw_data, list):
            errors.append(f"{path}: top-level value must be a list")
            continue

        file_topic_id = path.stem
        if file_topic_id not in active_topics:
            errors.append(f"{path}: filename topic '{file_topic_id}' is not an active question topic in {TOPICS_FILE}")
        validate_topic_entries(path, raw_data, active_topics, errors)
        for idx, entry in enumerate(raw_data):
            label = f"{path}[{idx}]"
            if not isinstance(entry, dict):
                errors.append(f"{label}: glossary entry must be an object")
                continue
            validate_entry(entry, label, file_topic_id, active_topics, approved_questions, seen_ids, errors)

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
