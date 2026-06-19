#!/usr/bin/env python3
"""Validate canonical active question JSON files used for seeding the quiz database."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TOPICS_PATH = REPO_ROOT / "content" / "topics.json"
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
REQUIRED_FIELDS = {
    "id",
    "category",
    "question",
    "options",
    "correct_option_index",
    "difficulty",
    "status",
    "source_ref",
    "explanation",
}


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value)).casefold()).strip()


def load_active_question_topics() -> list[dict[str, Any]]:
    raw = json.loads(TOPICS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{TOPICS_PATH}: top-level value must be a list")
    return [
        topic for topic in raw
        if isinstance(topic, dict)
        and topic.get("status") == "active"
        and "questions" in topic.get("available_contours", [])
        and topic.get("question_file")
    ]


def validate() -> list[str]:
    errors: list[str] = []
    seen_ids: dict[str, str] = {}
    seen_questions: dict[str, str] = {}

    try:
        topics = load_active_question_topics()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"Unable to load active topics: {exc}"]

    if not topics:
        return ["No active question topics found in content/topics.json"]

    for topic in sorted(topics, key=lambda item: (item.get("order", 0), str(item.get("id", "")))):
        path = REPO_ROOT / str(topic["question_file"])
        topic_title = str(topic.get("title", "")).strip()
        topic_id = str(topic.get("id", "")).strip()
        try:
            raw_data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.relative_to(REPO_ROOT)}: unable to read valid JSON ({exc})")
            continue

        if not isinstance(raw_data, list):
            errors.append(f"{path.relative_to(REPO_ROOT)}: top-level value must be a list")
            continue

        for idx, question in enumerate(raw_data):
            rel = path.relative_to(REPO_ROOT)
            label = f"{rel}[{idx}]"
            if not isinstance(question, dict):
                errors.append(f"{label}: question must be an object")
                continue
            missing = [field for field in REQUIRED_FIELDS if field not in question]
            if missing:
                errors.append(f"{label}: missing required fields: {', '.join(sorted(missing))}")

            status = str(question.get("status", "")).strip()
            qid = str(question.get("id", "")).strip()
            if not qid:
                errors.append(f"{label}: id must be present and non-empty")
            elif qid in seen_ids:
                errors.append(f"{label}: duplicate id '{qid}' also found in {seen_ids[qid]}")
            else:
                seen_ids[qid] = label

            if status != "approved":
                continue

            text = question.get("question")
            if not isinstance(text, str) or not text.strip():
                errors.append(f"{label}: approved question text must be a non-empty string")
            else:
                norm = normalize_text(text)
                if norm in seen_questions:
                    errors.append(f"{label}: duplicate normalized question text also found in {seen_questions[norm]}")
                else:
                    seen_questions[norm] = label

            explanation = question.get("explanation")
            if not isinstance(explanation, str) or not explanation.strip():
                errors.append(f"{label}: approved explanation must be a non-empty string")

            source_ref = question.get("source_ref")
            if not isinstance(source_ref, str) or not source_ref.strip():
                errors.append(f"{label}: approved source_ref must be a non-empty string")

            difficulty = question.get("difficulty")
            if difficulty not in VALID_DIFFICULTIES:
                errors.append(f"{label}: difficulty must be one of {sorted(VALID_DIFFICULTIES)}")

            category = question.get("category")
            if category != topic_title:
                errors.append(f"{label}: category {category!r} must match active topic '{topic_id}' title {topic_title!r}")

            options = question.get("options")
            if not isinstance(options, list):
                errors.append(f"{label}: options must be a list with exactly 4 items")
                continue
            if len(options) != 4:
                errors.append(f"{label}: approved options must contain exactly 4 items")
            normalized_options: list[str] = []
            for option_idx, option in enumerate(options):
                if not isinstance(option, str) or not option.strip():
                    errors.append(f"{label}: option #{option_idx} must be a non-empty string")
                normalized_options.append(normalize_text(option))
            non_empty_normalized = [item for item in normalized_options if item]
            if len(set(non_empty_normalized)) != len(non_empty_normalized):
                errors.append(f"{label}: options must be unique after NFKC/casefold/whitespace normalization")

            correct_idx = question.get("correct_option_index")
            if type(correct_idx) is not int:
                errors.append(f"{label}: correct_option_index must be an integer")
            elif correct_idx < 0 or correct_idx >= len(options):
                errors.append(f"{label}: correct_option_index {correct_idx} out of range for options size {len(options)}")
            elif options:
                correct_norm = normalize_text(options[correct_idx])
                if normalized_options.count(correct_norm) != 1:
                    errors.append(f"{label}: correct option must appear exactly once after normalization")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Question validation failed:")
        for err in errors:
            print(f"- {err}")
        return 1
    print("Question validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
