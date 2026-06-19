from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.db import upsert_approved_questions
from scripts.audit_question_bank import build_report, load_canonical

REPO_ROOT = Path(__file__).resolve().parent.parent


def _init_seeded_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "quiz.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript((REPO_ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
        questions = []
        for row in load_canonical()[0]:
            questions.append({
                "id": row["external_id"],
                "category": row["category"],
                "source_ref": row["source_ref"],
                "difficulty": row["difficulty"],
                "status": row["status"],
                "question": row["question_text"],
                "explanation": row["explanation"],
                "options": row["options"],
                "correct_option_index": row["correct_option_index"],
            })
        upsert_approved_questions(conn, questions)
    return db_path


def test_seeded_database_matches_canonical_json_exactly(tmp_path: Path) -> None:
    db_path = _init_seeded_db(tmp_path)
    canonical, _ = load_canonical()
    report = build_report(str(db_path))

    assert report["structural_errors"] == []
    sqlite_report = report["sqlite"]
    assert sqlite_report["integrity_check"] == ["ok"]
    assert sqlite_report["foreign_key_check"] == []
    assert sqlite_report["missing_db_rows"] == []
    assert sqlite_report["stale_db_rows"] == []
    assert sqlite_report["mismatched_rows"] == []
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


def test_audit_reports_stale_and_mismatched_rows_without_mutating(tmp_path: Path) -> None:
    db_path = _init_seeded_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        first = conn.execute("SELECT id, question_text FROM questions ORDER BY id LIMIT 1").fetchone()
        before = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        conn.execute("UPDATE questions SET question_text = ? WHERE id = ?", ("Injected mismatch", first[0]))
        conn.execute("INSERT INTO categories (slug, name) VALUES (?, ?)", ("stale", "Stale"))
        category_id = conn.execute("SELECT id FROM categories WHERE slug = 'stale'").fetchone()[0]
        conn.execute(
            "INSERT INTO questions (external_id, category_id, source_ref, difficulty, status, question_text, explanation) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("stale-question", category_id, "local/stale", "easy", "approved", "Stale?", "Stale."),
        )
    report = build_report(str(db_path))["sqlite"]
    assert report["stale_db_rows"] == ["stale-question"]
    assert any(row["mismatches"].get("question_text") for row in report["mismatched_rows"])
    with sqlite3.connect(db_path) as conn:
        after = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        mutated_text = conn.execute("SELECT question_text FROM questions WHERE id = ?", (first[0],)).fetchone()[0]
    assert after == before + 1
    assert mutated_text == "Injected mismatch"


def test_review_manifest_matches_active_approved_question_ids() -> None:
    canonical, _ = load_canonical()
    manifest = json.loads((REPO_ROOT / "docs" / "audits" / "question_bank_review_manifest.json").read_text(encoding="utf-8"))
    assert [row["question_id"] for row in manifest] == [row["external_id"] for row in canonical]
    assert {row["review_status"] for row in manifest} <= {"ok", "corrected", "needs_source_or_SME_review"}
