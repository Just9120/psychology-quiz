"""Read-only manifests for native PostgreSQL backup/restore reconciliation."""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit

from app.database import Connection, is_postgres_target
from app.postgres_import import projection, target_sequences
from app.postgres_schema import TABLES, table_columns, verify_schema

RESTORE_NAME = re.compile(r"psychology_restore_[0-9a-f]{32}")
# Content can be rebuilt from approved repository inputs. Every other table
# belongs to preserved runtime state, including tables added in later schemas.
REBUILDABLE_TABLES = frozenset({
    "categories", "questions", "question_options", "schema_migrations",
})


def recovery_target(target: str, database: str) -> str:
    if not is_postgres_target(target) or RESTORE_NAME.fullmatch(database) is None:
        raise ValueError("Owned isolated restore database required")
    return urlunsplit(urlsplit(target)._replace(path="/" + database))


def manifest(conn: Connection) -> dict:
    verify_schema(conn, allow_legacy=True)
    columns = {name: values for name, values in table_columns(conn).items() if name in TABLES}
    storage = list(conn.execute("SELECT * FROM postgres_storage WHERE singleton=1").fetchone())
    import_record = conn.execute(
        "SELECT import_manifest FROM postgres_storage WHERE singleton=1").fetchone()[0]
    return {
        "format": "psychology-postgres-backup-v1",
        "columns": {name: list(values) for name, values in columns.items()},
        "tables": projection(conn, columns),
        "sequences": target_sequences(conn),
        "storage_sha256": hashlib.sha256(json.dumps(storage, separators=(",", ":")).encode()).hexdigest(),
        "import_manifest_sha256": hashlib.sha256(
            json.dumps(import_record, separators=(",", ":")).encode()).hexdigest(),
    }


def verify_user_state(before: dict, after: dict) -> None:
    # Content publication may change serving content, never pre-existing history.
    if before.get("format") != "psychology-postgres-backup-v1" or after.get("format") != before["format"]:
        raise ValueError("Unknown PostgreSQL preservation manifest")
    before_columns, after_columns = before["columns"], after["columns"]
    if (set(before_columns) != set(before["tables"])
            or set(after_columns) != set(after["tables"])):
        raise ValueError("Incomplete PostgreSQL preservation manifest")
    # Schema version/digest may change during a migration, but the original
    # import provenance must survive. Old recovery records lack this field.
    if ("import_manifest_sha256" in before
            and after.get("import_manifest_sha256") != before["import_manifest_sha256"]):
        raise ValueError("PostgreSQL migration changed import provenance")
    for table in before_columns.keys() - REBUILDABLE_TABLES:
        if (table not in after_columns
                or before_columns[table] != after_columns[table]
                or before["tables"][table] != after["tables"][table]):
            raise ValueError("PostgreSQL migration changed pre-existing user state")
        if table in before["sequences"] and after["sequences"].get(table) != before["sequences"][table]:
            raise ValueError("PostgreSQL migration changed a user identity sequence")
    for table in after_columns.keys() - before_columns.keys() - REBUILDABLE_TABLES:
        if (after["tables"][table]["rows"] != 0
                or after["sequences"].get(table, 0) != 0):
            raise ValueError("New user-state table must be empty during migration")
