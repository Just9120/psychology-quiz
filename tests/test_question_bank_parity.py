from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.db import upsert_approved_questions
from scripts import audit_question_bank
from scripts.audit_question_bank import build_report, load_canonical, load_canonical_inventory

REPO_ROOT = Path(__file__).resolve().parent.parent


def _question_payload(row: dict) -> dict:
    return {
        "id": row["external_id"],
        "category": row["category"],
        "source_ref": row["source_ref"],
        "difficulty": row["difficulty"],
        "status": row["status"],
        "question": row["question_text"],
        "explanation": row["explanation"],
        "options": row["options"],
        "correct_option_index": row["correct_option_index"],
    }


def _init_seeded_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "quiz.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript((REPO_ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
        upsert_approved_questions(conn, [_question_payload(row) for row in load_canonical()[0]])
    return db_path


def _insert_question(conn: sqlite3.Connection, *, external_id: str, category_name: str = "Injected") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO categories (slug, name) VALUES (?, ?)",
        (category_name.lower(), category_name),
    )
    category_id = conn.execute("SELECT id FROM categories WHERE name = ?", (category_name,)).fetchone()[0]
    conn.execute(
        "INSERT INTO questions (external_id, category_id, source_ref, difficulty, status, question_text, explanation) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (external_id, category_id, "local/test", "easy", "approved", "Injected?", "Injected."),
    )


def test_seeded_database_matches_canonical_json_exactly(tmp_path: Path) -> None:
    db_path = _init_seeded_db(tmp_path)
    canonical, _ = load_canonical()
    report = build_report(str(db_path))

    assert report["structural_errors"] == []
    sqlite_report = report["sqlite"]
    assert sqlite_report["integrity_check"] == ["ok"]
    assert sqlite_report["foreign_key_check"] == []
    assert sqlite_report["missing_approved_db_rows"] == []
    assert sqlite_report["retired_canonical_db_rows"] == []
    assert sqlite_report["unknown_db_rows"] == []
    assert sqlite_report["mismatched_approved_rows"] == []
    assert sqlite_report["orphan_option_rows"] == []
    assert sqlite_report["duplicate_external_ids"] == []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for expected in canonical:
            question = conn.execute(
                """
                SELECT q.*, c.name AS category
                FROM questions q JOIN categories c ON c.id = q.category_id
                WHERE q.external_id = ?
                """,
                (expected["external_id"],),
            ).fetchone()
            assert question is not None
            assert question["category"] == expected["category"]
            assert question["difficulty"] == expected["difficulty"]
            assert question["status"] == "approved"
            assert question["source_ref"] == expected["source_ref"]
            assert question["question_text"] == expected["question_text"]
            assert question["explanation"] == expected["explanation"]
            options = conn.execute(
                "SELECT option_index, option_text, is_correct FROM question_options WHERE question_id = ? ORDER BY option_index",
                (question["id"],),
            ).fetchall()
            assert [row["option_index"] for row in options] == list(range(4))
            assert [row["option_text"] for row in options] == expected["options"]
            assert [row["option_index"] for row in options if row["is_correct"]] == [expected["correct_option_index"]]


def test_audit_reports_missing_unknown_mismatched_rows_without_mutating(tmp_path: Path) -> None:
    db_path = _init_seeded_db(tmp_path)
    canonical, _ = load_canonical()
    removed_external_id = canonical[0]["external_id"]
    changed_external_id = canonical[1]["external_id"]
    with sqlite3.connect(db_path) as conn:
        removed_db_id = conn.execute("SELECT id FROM questions WHERE external_id = ?", (removed_external_id,)).fetchone()[0]
        conn.execute("DELETE FROM question_options WHERE question_id = ?", (removed_db_id,))
        conn.execute("DELETE FROM questions WHERE id = ?", (removed_db_id,))
        conn.execute("UPDATE questions SET question_text = ? WHERE external_id = ?", ("Injected mismatch", changed_external_id))
        _insert_question(conn, external_id="unknown-question")
        before = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    report = build_report(str(db_path))["sqlite"]
    assert report["missing_approved_db_rows"] == [removed_external_id]
    assert report["unknown_db_rows"] == ["unknown-question"]
    assert any(row["external_id"] == changed_external_id and row["mismatches"].get("question_text") for row in report["mismatched_approved_rows"])
    with sqlite3.connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        mutated_text = conn.execute("SELECT question_text FROM questions WHERE external_id = ?", (changed_external_id,)).fetchone()[0]
    assert after == before
    assert mutated_text == "Injected mismatch"


def test_retired_canonical_db_rows_are_informational_not_blocking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = _init_seeded_db(tmp_path)
    inventory, topics = load_canonical_inventory()
    retired = dict(inventory[0])
    retired["external_id"] = "retired-canonical-question"
    retired["status"] = "retired"
    with sqlite3.connect(db_path) as conn:
        _insert_question(conn, external_id=retired["external_id"])
    monkeypatch.setattr(audit_question_bank, "load_canonical_inventory", lambda: (inventory + [retired], topics))

    report = audit_question_bank.build_report(str(db_path))

    assert report["sqlite"]["retired_canonical_db_rows"] == [retired["external_id"]]
    assert report["sqlite"]["unknown_db_rows"] == []
    assert not audit_question_bank.has_blockers(report)


def test_review_queue_is_compact_unique_and_capped() -> None:
    queue_path = REPO_ROOT / "docs" / "audits" / "question_bank_review_queue.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    items = queue["items"]
    max_items = queue["metadata"]["max_items"]
    assert queue["metadata"]["item_count"] == len(items)
    assert max_items == 50
    assert len(items) <= max_items
    identities = [item.get("question_id") or tuple(item.get("question_ids", [])) for item in items]
    assert len(identities) == len(set(identities))
    for item in items:
        assert set(item) == {"question_id", "topic_id", "issue_type", "evidence", "severity", "recommended_next_action"}
        assert item["severity"] in {"medium", "high"}
        if item["issue_type"] == "answer_length_cue":
            evidence = item["evidence"]
            assert evidence["correct_length_to_median_distractor_ratio"] >= 2.75
            assert evidence["correct_length_minus_longest_distractor"] >= 45
