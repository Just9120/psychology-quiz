"""Client-independent, immutable question editions owned by quiz attempts."""
from __future__ import annotations

import hashlib
import json
from app.database import Connection, begin_write, is_postgres


def capture_question(conn: Connection, question_id: int) -> tuple[str, str]:
    return capture_questions(conn, [question_id])[question_id]


def capture_questions(conn: Connection, question_ids: list[int]) -> dict[int, tuple[str, str]]:
    """Capture exact current editions in bounded batches, preserving byte identity.

    Callers own the transaction/content lock. This replaces per-question bank
    queries in actor history views; it never updates stored attempt snapshots.
    """
    ids = list(dict.fromkeys(question_ids))
    captured = {}
    for offset in range(0, len(ids), 500):
        batch = ids[offset:offset + 500]
        placeholders = ','.join('?' for _ in batch)
        rows = conn.execute(f"""SELECT q.id,q.external_id,q.question_text,q.explanation,q.source_ref,
                          c.name,q.difficulty,q.kind,q.case_content
            FROM questions q JOIN categories c ON c.id=q.category_id WHERE q.id IN ({placeholders})""", batch).fetchall()
        if len(rows) != len(batch):
            raise ValueError("Cannot snapshot a missing question")
        options = {qid: [] for qid in batch}
        for qid, index, text, correct in conn.execute(f"""SELECT question_id,option_index,option_text,is_correct
                FROM question_options WHERE question_id IN ({placeholders}) ORDER BY question_id,option_index""", batch):
            options[qid].append({'option_index': index, 'option_text': text, 'is_correct': correct})
        for row in rows:
            content = dict(zip(
                ('external_id', 'question_text', 'explanation', 'source_ref', 'category', 'difficulty'), row[1:7]))
            if row[7] != 'theory':
                content['kind'] = row[7]
            if row[8] is not None:
                content['case'] = json.loads(row[8])
            content['version'] = 1
            content['options'] = options[row[0]]
            encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            captured[row[0]] = encoded, hashlib.sha256(encoded.encode()).hexdigest()
    return captured


def ensure_attempt_snapshots(conn: Connection) -> None:
    """Idempotent additive migration; caller owns transaction and commit.

    Legacy rows capture only the edition still available before content sync.
    Never claim it is the original edition and never recalculate saved answers.
    """
    if is_postgres(conn):
        # PostgreSQL schema/import is explicit, never migrated by a request.
        if conn.execute("SELECT 1 FROM quiz_session_questions WHERE content_snapshot IS NULL LIMIT 1").fetchone():
            raise ValueError("Attempt snapshots require migration/recovery")
        return
    begin_write(conn)
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


def get_attempt_content(conn: Connection, session_id: int, question_id: int) -> dict | None:
    row = conn.execute(
        """SELECT content_snapshot, content_sha256, snapshot_provenance
           FROM quiz_session_questions WHERE session_id=? AND question_id=?""",
        (session_id, question_id),
    ).fetchone()
    if row is None:
        return None
    return decode_attempt_content(*row)


def decode_attempt_content(encoded: str, digest: str, provenance: str) -> dict:
    """Validate an immutable edition loaded alone or in an actor-scoped join."""
    if not encoded or hashlib.sha256(encoded.encode()).hexdigest() != digest:
        raise ValueError("Attempt content is missing or corrupt; migration/recovery required")
    content = json.loads(encoded)
    if content.get("version") != 1:
        raise ValueError("Unsupported attempt content version")
    content["content_sha256"] = digest
    content["snapshot_provenance"] = provenance
    return content
