#!/usr/bin/env python3
"""Audit canonical question content and optional read-only SQLite parity."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_questions import validate

TOPICS_PATH = REPO_ROOT / "content" / "topics.json"
COMPARE_FIELDS = ["external_id", "category", "difficulty", "status", "source_ref", "question_text", "explanation", "options"]


def active_topics() -> list[dict[str, Any]]:
    topics = json.loads(TOPICS_PATH.read_text(encoding="utf-8"))
    return [t for t in topics if t.get("status") == "active" and "questions" in t.get("available_contours", [])]


def _canonical_row(topic: dict[str, Any], q: dict[str, Any], order: int) -> dict[str, Any]:
    return {
        "topic_id": topic["id"],
        "order": order,
        "external_id": str(q["id"]).strip(),
        "category": str(q.get("category", topic["title"])).strip(),
        "difficulty": str(q.get("difficulty", "")).strip(),
        "status": str(q.get("status", "")).strip(),
        "source_ref": str(q.get("source_ref", "")).strip(),
        "question_text": str(q.get("question", "")).strip(),
        "explanation": str(q.get("explanation", "")).strip(),
        "options": [str(o) for o in q.get("options", [])],
        "correct_option_index": q.get("correct_option_index"),
    }


def load_canonical_inventory() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    topic_summary: dict[str, Any] = {}
    for topic in sorted(active_topics(), key=lambda t: (t.get("order", 0), t.get("id", ""))):
        path = REPO_ROOT / topic["question_file"]
        data = json.loads(path.read_text(encoding="utf-8"))
        approved = [q for q in data if q.get("status") == "approved"]
        topic_summary[topic["id"]] = {
            "title": topic["title"],
            "question_file": topic["question_file"],
            "canonical_rows": len(data),
            "approved_questions": len(approved),
        }
        for order, q in enumerate(data):
            rows.append(_canonical_row(topic, q, order))
    return rows, topic_summary


def load_canonical() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, topics = load_canonical_inventory()
    return [row for row in rows if row["status"] == "approved"], topics


def read_only_connection(db_path: str) -> sqlite3.Connection:
    uri = f"file:{Path(db_path).resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def db_projection(conn: sqlite3.Connection) -> tuple[dict[str, Any], dict[str, Any]]:
    qrows = conn.execute(
        """
        SELECT q.id, q.external_id, c.name AS category, q.difficulty, q.status,
               q.source_ref, q.question_text, q.explanation
        FROM questions q JOIN categories c ON c.id = q.category_id
        ORDER BY q.id
        """
    ).fetchall()
    by_external: dict[str, Any] = {}
    for row in qrows:
        options = conn.execute(
            "SELECT id, option_index, option_text, is_correct FROM question_options WHERE question_id = ? ORDER BY option_index",
            (row["id"],),
        ).fetchall()
        by_external[str(row["external_id"])] = {
            "db_id": int(row["id"]),
            "external_id": str(row["external_id"]),
            "category": str(row["category"]),
            "difficulty": str(row["difficulty"]),
            "status": str(row["status"]),
            "source_ref": "" if row["source_ref"] is None else str(row["source_ref"]),
            "question_text": str(row["question_text"]),
            "explanation": "" if row["explanation"] is None else str(row["explanation"]),
            "options": [str(o["option_text"]) for o in options],
            "correct_option_indices": [int(o["option_index"]) for o in options if int(o["is_correct"]) == 1],
        }
    duplicate_external_ids = [r["external_id"] for r in conn.execute("SELECT external_id FROM questions GROUP BY external_id HAVING COUNT(*) > 1")]
    orphan_options = [dict(r) for r in conn.execute("SELECT qo.* FROM question_options qo LEFT JOIN questions q ON q.id = qo.question_id WHERE q.id IS NULL")]
    meta = {"duplicate_external_ids": duplicate_external_ids, "orphan_options": orphan_options}
    return by_external, meta


def compare_db(db_path: str, canonical_inventory: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "db_path": db_path,
        "integrity_check": [],
        "foreign_key_check": [],
        "missing_approved_db_rows": [],
        "retired_canonical_db_rows": [],
        "unknown_db_rows": [],
        "mismatched_approved_rows": [],
        "orphan_option_rows": [],
        "duplicate_external_ids": [],
    }
    with read_only_connection(db_path) as conn:
        result["integrity_check"] = [row[0] for row in conn.execute("PRAGMA integrity_check")]
        result["foreign_key_check"] = [dict(row) for row in conn.execute("PRAGMA foreign_key_check")]
        db_rows, meta = db_projection(conn)

    canonical_by_id = {row["external_id"]: row for row in canonical_inventory}
    approved_by_id = {row["external_id"]: row for row in canonical_inventory if row["status"] == "approved"}
    retired_by_id = {row["external_id"]: row for row in canonical_inventory if row["status"] != "approved"}

    result["missing_approved_db_rows"] = sorted(set(approved_by_id) - set(db_rows))
    result["retired_canonical_db_rows"] = sorted(set(retired_by_id) & set(db_rows))
    result["unknown_db_rows"] = sorted(set(db_rows) - set(canonical_by_id))
    result["orphan_option_rows"] = meta["orphan_options"]
    result["duplicate_external_ids"] = sorted(meta["duplicate_external_ids"])

    for external_id in sorted(set(approved_by_id) & set(db_rows)):
        exp = approved_by_id[external_id]
        got = db_rows[external_id]
        mismatches: dict[str, Any] = {}
        for field in COMPARE_FIELDS:
            if exp[field] != got[field]:
                mismatches[field] = {"expected": exp[field], "actual": got[field]}
        if got["correct_option_indices"] != [exp["correct_option_index"]]:
            mismatches["correct_option_indices"] = {"expected": [exp["correct_option_index"]], "actual": got["correct_option_indices"]}
        if len(got["options"]) != 4:
            mismatches["option_count"] = {"expected": 4, "actual": len(got["options"])}
        if mismatches:
            result["mismatched_approved_rows"].append({"external_id": external_id, "mismatches": mismatches})
    return result


def has_blockers(report: dict[str, Any]) -> bool:
    db = report.get("sqlite") or {}
    return bool(
        report["structural_errors"]
        or (db and db.get("integrity_check") != ["ok"])
        or (db and db.get("foreign_key_check"))
        or (db and (
            db.get("missing_approved_db_rows")
            or db.get("mismatched_approved_rows")
            or db.get("unknown_db_rows")
            or db.get("orphan_option_rows")
            or db.get("duplicate_external_ids")
        ))
    )


def build_report(db_path: str | None = None) -> dict[str, Any]:
    errors = validate()
    canonical_inventory, topics = load_canonical_inventory()
    approved_count = sum(1 for row in canonical_inventory if row["status"] == "approved")
    report: dict[str, Any] = {
        "canonical_source": "content/topics.json active questions contours and referenced JSON question files",
        "active_topic_count": len(topics),
        "canonical_row_count": len(canonical_inventory),
        "approved_question_count": approved_count,
        "topics": topics,
        "structural_errors": errors,
        "sqlite": None,
    }
    if db_path:
        report["sqlite"] = compare_db(db_path, canonical_inventory)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", help="SQLite database to audit in read-only mode")
    parser.add_argument("--report-path", help="Write machine-readable JSON report")
    args = parser.parse_args()
    report = build_report(args.db_path)
    print(f"Active question topics: {report['active_topic_count']}")
    print(f"Canonical question rows: {report['canonical_row_count']}")
    print(f"Approved canonical questions: {report['approved_question_count']}")
    for tid, summary in report["topics"].items():
        print(f"- {tid}: {summary['approved_questions']} approved / {summary['canonical_rows']} canonical rows")
    if report["structural_errors"]:
        print("Structural blockers:")
        for err in report["structural_errors"]:
            print(f"- {err}")
    if report["sqlite"]:
        db = report["sqlite"]
        print("SQLite read-only audit:")
        print(f"- integrity_check: {db['integrity_check']}")
        print(f"- foreign_key_check rows: {len(db['foreign_key_check'])}")
        print(f"- missing approved rows: {len(db['missing_approved_db_rows'])}")
        print(f"- retired canonical rows retained: {len(db['retired_canonical_db_rows'])}")
        print(f"- unknown rows: {len(db['unknown_db_rows'])}")
        print(f"- mismatched approved rows: {len(db['mismatched_approved_rows'])}")
        print(f"- orphan option rows: {len(db['orphan_option_rows'])}")
        print(f"- duplicate external IDs: {len(db['duplicate_external_ids'])}")
    if args.report_path:
        path = Path(args.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if has_blockers(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
