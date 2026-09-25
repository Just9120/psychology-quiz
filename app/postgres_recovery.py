"""Read-only manifests for native PostgreSQL backup/restore reconciliation."""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit

from app.database import Connection, is_postgres_target
from app.postgres_import import projection, target_sequences
from app.postgres_schema import TABLES, table_columns, verify_schema
from app.auth_schema import AUTH_TABLES

RESTORE_NAME = re.compile(r"psychology_restore_[0-9a-f]{32}")
USER_TABLES = (
    "users", "quiz_sessions", "quiz_session_selected_categories",
    "quiz_session_questions", "quiz_answers", "user_literature_progress",
    "glossary_sessions", "user_learning_goals", "user_achievements", "user_review_events",
)


def recovery_target(target: str, database: str) -> str:
    if not is_postgres_target(target) or RESTORE_NAME.fullmatch(database) is None:
        raise ValueError("Owned isolated restore database required")
    return urlunsplit(urlsplit(target)._replace(path="/" + database))


def manifest(conn: Connection) -> dict:
    verify_schema(conn, allow_legacy=True)
    columns = {name: values for name, values in table_columns(conn).items() if name in TABLES}
    storage = list(conn.execute("SELECT * FROM postgres_storage WHERE singleton=1").fetchone())
    return {
        "format": "psychology-postgres-backup-v1",
        "columns": {name: list(values) for name, values in columns.items()},
        "tables": projection(conn, columns),
        "sequences": target_sequences(conn),
        "storage_sha256": hashlib.sha256(json.dumps(storage, separators=(",", ":")).encode()).hexdigest(),
    }


def verify_user_state(before: dict, after: dict) -> None:
    # Content publication may change serving content, never pre-existing history.
    if before.get("format") != "psychology-postgres-backup-v1" or after.get("format") != before["format"]:
        raise ValueError("Unknown PostgreSQL preservation manifest")
    for table in USER_TABLES + AUTH_TABLES:
        if table in {"glossary_sessions", "user_learning_goals", "user_achievements", "user_review_events"} and table not in before["columns"]:
            if table in after["tables"] and after["tables"][table]["rows"] != 0:
                raise ValueError("New user-state table must be empty during migration")
            continue
        if before["columns"][table] != after["columns"][table] or before["tables"][table] != after["tables"][table]:
            raise ValueError("PostgreSQL migration changed pre-existing user state")
        if table in before["sequences"] and after["sequences"][table] < before["sequences"][table]:
            raise ValueError("PostgreSQL migration lowered a user identity sequence")
