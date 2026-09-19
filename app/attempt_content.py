"""Client-independent, immutable question editions owned by quiz attempts."""
from __future__ import annotations

import hashlib
import json
import sqlite3


def capture_question(conn: sqlite3.Connection, question_id: int) -> tuple[str, str]:
    row = conn.execute(
        """SELECT q.external_id, q.question_text, q.explanation, q.source_ref,
                  c.name, q.difficulty
           FROM questions q JOIN categories c ON c.id=q.category_id WHERE q.id=?""",
        (question_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Cannot snapshot a missing question")
    content = dict(zip(
        ("external_id", "question_text", "explanation", "source_ref", "category", "difficulty"), row
    ))
    content["version"] = 1
    content["options"] = [
        {"option_index": option[0], "option_text": option[1], "is_correct": option[2]}
        for option in conn.execute(
            "SELECT option_index, option_text, is_correct FROM question_options WHERE question_id=? ORDER BY option_index",
            (question_id,),
        )
    ]
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return encoded, hashlib.sha256(encoded.encode()).hexdigest()


def ensure_attempt_snapshots(conn: sqlite3.Connection) -> None:
    """Idempotent additive migration; caller owns transaction and commit.

    Legacy rows capture only the edition still available before content sync.
    Never claim it is the original edition and never recalculate saved answers.
    """
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(quiz_session_questions)")}
    for name in ("content_snapshot", "content_sha256", "snapshot_provenance"):
        if name not in columns:
            conn.execute(f"ALTER TABLE quiz_session_questions ADD COLUMN {name} TEXT")
    for row in conn.execute(
        "SELECT id, question_id FROM quiz_session_questions WHERE content_snapshot IS NULL"
    ).fetchall():
        encoded, digest = capture_question(conn, row[1])
        conn.execute(
            """UPDATE quiz_session_questions SET content_snapshot=?, content_sha256=?,
               snapshot_provenance='legacy_backfill_current' WHERE id=? AND content_snapshot IS NULL""",
            (encoded, digest, row[0]),
        )
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS immutable_attempt_content
        BEFORE UPDATE OF content_snapshot, content_sha256, snapshot_provenance, session_id, question_id
        ON quiz_session_questions WHEN OLD.content_snapshot IS NOT NULL AND (
            NEW.content_snapshot IS NOT OLD.content_snapshot OR
            NEW.content_sha256 IS NOT OLD.content_sha256 OR
            NEW.snapshot_provenance IS NOT OLD.snapshot_provenance OR
            NEW.session_id IS NOT OLD.session_id OR NEW.question_id IS NOT OLD.question_id
        ) BEGIN SELECT RAISE(ABORT, 'Attempt content is immutable'); END
    """)


def get_attempt_content(conn: sqlite3.Connection, session_id: int, question_id: int) -> dict | None:
    row = conn.execute(
        """SELECT content_snapshot, content_sha256, snapshot_provenance
           FROM quiz_session_questions WHERE session_id=? AND question_id=?""",
        (session_id, question_id),
    ).fetchone()
    if row is None:
        return None
    encoded, digest, provenance = row
    if not encoded or hashlib.sha256(encoded.encode()).hexdigest() != digest:
        raise ValueError("Attempt content is missing or corrupt; migration/recovery required")
    content = json.loads(encoded)
    if content.get("version") != 1:
        raise ValueError("Unsupported attempt content version")
    content["content_sha256"] = digest
    content["snapshot_provenance"] = provenance
    return content
