"""Read-only copy of one actor's learning rows, excluding authentication storage.

The caller must establish the actor from a verified request. This module does
not resolve usernames, accept another actor through a public API, or send files.
"""
import json
from datetime import datetime, timezone

from app.database import is_postgres
from app.privacy_data import LEARNING_TABLES, PrivacyError

# Snapshots describe shared teaching content, not the actor's personal answers.
# Keep actor-owned state separately without exporting private source locators.
OMITTED_COLUMNS = {"content_snapshot", "snapshot", "content_sha256", "snapshot_provenance"}
CHILD_TABLES = ("quiz_answers", "quiz_session_selected_categories",
                "quiz_session_questions", "homework_attempts")


def write_learning_copy(conn, actor_user_id, output, *, expected_telegram_user_id=None):
    """Stream a consistent copy to an already private file; own transaction."""
    if type(actor_user_id) is not int or actor_user_id <= 0:
        raise PrivacyError("invalid_actor")
    if conn.in_transaction:
        raise PrivacyError("export_requires_new_transaction")
    if is_postgres(conn):
        conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
    else:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
    try:
        if conn.execute("SELECT 1 FROM users WHERE id=?", (actor_user_id,)).fetchone() is None:
            raise PrivacyError("unknown_actor")
        if expected_telegram_user_id is not None:
            identity = conn.execute("SELECT telegram_user_id FROM users WHERE id=?", (actor_user_id,)).fetchone()
            if identity[0] != expected_telegram_user_id:
                raise PrivacyError("identity_changed")
        metadata = {
            "schema_version": 1, "scope": "learning_data_copy",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "excluded": ["authentication_and_identity", "shared_content_snapshots",
                         "private_sources", "infrastructure_logs_and_backups"],
        }
        output.write(json.dumps(metadata, ensure_ascii=False)[:-1] + ', "tables": {')
        counts = {}
        for number, table in enumerate((*LEARNING_TABLES, *CHILD_TABLES)):
            if table in CHILD_TABLES:
                cursor = conn.execute(
                    f"SELECT t.* FROM {table} t JOIN quiz_sessions s ON s.id=t.session_id WHERE s.user_id=?",
                    (actor_user_id,))
            else:
                cursor = conn.execute(f"SELECT * FROM {table} WHERE user_id=?", (actor_user_id,))
            columns = [column[0] for column in cursor.description]
            output.write((", " if number else "") + json.dumps(table) + ": [")
            count = 0
            for row in cursor:
                record = {name: row[index] for index, name in enumerate(columns)
                          if name not in OMITTED_COLUMNS}
                # Glossary state contains the actor's recorded selections and
                # public feedback; its source-bearing teaching snapshot is omitted.
                output.write((", " if count else "") + json.dumps(record, ensure_ascii=False))
                count += 1
            counts[table] = count
            output.write("]")
        output.write("}, " + json.dumps("row_counts") + ": " + json.dumps(counts) + ', "complete": true}\n')
        return counts
    finally:
        conn.rollback()
