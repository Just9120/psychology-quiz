#!/usr/bin/env python3
"""Validate question JSON files used for seeding the quiz database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

QUESTION_FILES_GLOB = "content/questions/**/*.json"
REQUIRED_FIELDS = {
    "id",
    "category",
    "question",
    "options",
    "correct_option_index",
    "status",
    "source_ref",
}


def validate() -> list[str]:
    errors: list[str] = []
    seen_ids: dict[str, Path] = {}

    question_files = sorted(Path(".").glob(QUESTION_FILES_GLOB))
    if not question_files:
        errors.append(f"No question files found with glob: {QUESTION_FILES_GLOB}")
        return errors

    for path in question_files:
        try:
            raw_data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: invalid JSON ({exc})")
            continue

        if not isinstance(raw_data, list):
            errors.append(f"{path}: top-level value must be a list")
            continue

        for idx, question in enumerate(raw_data):
            label = f"{path}[{idx}]"
            if not isinstance(question, dict):
                errors.append(f"{label}: question must be an object")
                continue

            missing = [field for field in REQUIRED_FIELDS if field not in question]
            if missing:
                errors.append(f"{label}: missing required fields: {', '.join(sorted(missing))}")

            question_id = question.get("id")
            if question_id is None or (isinstance(question_id, str) and not question_id.strip()):
                errors.append(f"{label}: id must be present and non-empty")
            else:
                canonical_id = str(question_id)
                if canonical_id in seen_ids:
                    errors.append(
                        f"{label}: duplicate id '{canonical_id}' also found in {seen_ids[canonical_id]}"
                    )
                else:
                    seen_ids[canonical_id] = path

            options = question.get("options")
            if not isinstance(options, list) or len(options) < 2:
                errors.append(f"{label}: options must be a list with at least 2 items")

            correct_idx = question.get("correct_option_index")
            if isinstance(options, list):
                if type(correct_idx) is not int:
                    errors.append(f"{label}: correct_option_index must be an integer")
                elif correct_idx < 0 or correct_idx >= len(options):
                    errors.append(
                        f"{label}: correct_option_index {correct_idx} out of range for options size {len(options)}"
                    )

            status = question.get("status")
            if status is None or not str(status).strip():
                errors.append(f"{label}: status must be present and non-empty")

            if "source_ref" in question:
                source_ref = question.get("source_ref")
                if source_ref is None or not str(source_ref).strip():
                    errors.append(f"{label}: source_ref must be non-empty")

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
