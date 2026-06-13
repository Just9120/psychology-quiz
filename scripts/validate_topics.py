#!/usr/bin/env python3
"""Validate the static topic registry against question JSON files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TOPICS_FILE = Path("content/topics.json")
QUESTION_FILES_GLOB = "content/questions/**/*.json"
REQUIRED_FIELDS = {
    "id",
    "title",
    "module",
    "question_file",
    "status",
    "order",
    "available_contours",
    "source_notes",
}
VALID_STATUSES = {"active", "draft", "deprecated", "placeholder"}
VALID_CONTOURS = {"questions"}
TOPIC_ID_RE = re.compile(r"^[a-z0-9_]+$")


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


def validate_question_file(topic: dict[str, Any], label: str, errors: list[str]) -> Path | None:
    question_file = topic.get("question_file")
    if not is_non_empty_string(question_file):
        return None

    question_path = Path(question_file)
    if not question_path.exists():
        errors.append(f"{label}: question_file does not exist: {question_file}")
        return question_path

    module = topic.get("module")
    if is_non_empty_string(module) and question_path.parent.name != module:
        errors.append(
            f"{label}: question_file parent module '{question_path.parent.name}' does not match module '{module}'"
        )

    questions = load_json(question_path, errors, f"{label}: {question_file}")
    if questions is None:
        return question_path
    if not isinstance(questions, list):
        errors.append(f"{label}: {question_file}: top-level value must be a list")
        return question_path

    approved_count = 0
    categories: set[Any] = set()
    for idx, question in enumerate(questions):
        item_label = f"{label}: {question_file}[{idx}]"
        if not isinstance(question, dict):
            errors.append(f"{item_label}: question must be an object")
            continue
        if question.get("status") == "approved":
            approved_count += 1
        if "category" in question:
            categories.add(question.get("category"))
        else:
            errors.append(f"{item_label}: missing category")

    if approved_count == 0:
        errors.append(f"{label}: {question_file}: must contain at least one approved question")
    if len(categories) != 1:
        errors.append(
            f"{label}: {question_file}: must use exactly one category value; found {len(categories)}"
        )
    else:
        category = next(iter(categories))
        if category != topic.get("title"):
            errors.append(
                f"{label}: {question_file}: category '{category}' does not match title '{topic.get('title')}'"
            )

    return question_path


def validate() -> list[str]:
    errors: list[str] = []
    topics = load_json(TOPICS_FILE, errors, str(TOPICS_FILE))
    if topics is None:
        return errors
    if not isinstance(topics, list):
        return [f"{TOPICS_FILE}: top-level value must be a list"]

    seen_ids: dict[str, int] = {}
    active_orders: dict[int, str] = {}
    represented_question_files: list[Path] = []

    for idx, topic in enumerate(topics):
        label = f"{TOPICS_FILE}[{idx}]"
        if not isinstance(topic, dict):
            errors.append(f"{label}: topic must be an object")
            continue

        missing = sorted(REQUIRED_FIELDS - topic.keys())
        if missing:
            errors.append(f"{label}: missing required fields: {', '.join(missing)}")

        topic_id = topic.get("id")
        if not is_non_empty_string(topic_id):
            errors.append(f"{label}: id must be a non-empty string")
        else:
            if not topic_id.isascii() or topic_id.lower() != topic_id or not TOPIC_ID_RE.match(topic_id):
                errors.append(f"{label}: id must be lowercase ASCII and match ^[a-z0-9_]+$: {topic_id}")
            if topic_id in seen_ids:
                errors.append(f"{label}: duplicate id '{topic_id}' also found at index {seen_ids[topic_id]}")
            else:
                seen_ids[topic_id] = idx

        for field in ("title", "module", "question_file", "source_notes"):
            if field in topic and not is_non_empty_string(topic.get(field)):
                errors.append(f"{label}: {field} must be a non-empty string")

        status = topic.get("status")
        if status not in VALID_STATUSES:
            errors.append(f"{label}: status must be one of {', '.join(sorted(VALID_STATUSES))}")

        order = topic.get("order")
        if type(order) is not int:
            errors.append(f"{label}: order must be an integer")
        elif status == "active":
            if order in active_orders:
                errors.append(
                    f"{label}: active order {order} duplicates topic id '{active_orders[order]}'"
                )
            elif is_non_empty_string(topic_id):
                active_orders[order] = topic_id

        contours = topic.get("available_contours")
        if not isinstance(contours, list) or not contours:
            errors.append(f"{label}: available_contours must be a non-empty list")
            contours = []
        else:
            for contour in contours:
                if contour not in VALID_CONTOURS:
                    errors.append(
                        f"{label}: unsupported available_contours value '{contour}'; Phase 1b allows only questions"
                    )

        if "questions" in contours:
            question_path = validate_question_file(topic, label, errors)
            if question_path is not None:
                represented_question_files.append(question_path)

    question_files = sorted(Path(".").glob(QUESTION_FILES_GLOB))
    represented_counts: dict[Path, int] = {}
    for path in represented_question_files:
        represented_counts[path] = represented_counts.get(path, 0) + 1

    for path in question_files:
        count = represented_counts.get(path, 0)
        if count == 0:
            errors.append(f"{path}: question file is not represented in {TOPICS_FILE}")
        elif count > 1:
            errors.append(f"{path}: question file is represented {count} times in {TOPICS_FILE}")

    for path, count in represented_counts.items():
        if path not in question_files and count > 1:
            errors.append(f"{path}: question file is represented {count} times in {TOPICS_FILE}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Topic registry validation failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Topic registry validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
