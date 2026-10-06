"""Read-only manifests for native PostgreSQL backup/restore reconciliation."""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.database import Connection

RESTORE_NAME = re.compile(r"psychology_restore_[0-9a-f]{32}")
# Content can be rebuilt from approved repository inputs. Every other table
# belongs to preserved runtime state, including tables added in later schemas.
REBUILDABLE_TABLES = frozenset({
    "categories", "questions", "question_options", "schema_migrations",
})


def recovery_target(target: str, database: str) -> str:
    if (not str(target).lower().startswith(("postgresql://", "postgres://"))
            or RESTORE_NAME.fullmatch(database) is None):
        raise ValueError("Owned isolated restore database required")
    return urlunsplit(urlsplit(target)._replace(path="/" + database))


def manifest(conn: Connection) -> dict:
    # Database access runs inside the pinned application image, not on the host.
    from app.postgres_import import projection, target_sequences
    from app.postgres_schema import TABLES, table_columns, verify_schema

    verify_schema(conn, allow_legacy=True)
    columns = {name: values for name, values in table_columns(conn).items() if name in TABLES}
    storage = list(conn.execute("SELECT * FROM postgres_storage WHERE singleton=1").fetchone())
    import_record = conn.execute(
        "SELECT import_manifest FROM postgres_storage WHERE singleton=1").fetchone()[0]
    result = {
        "format": "psychology-postgres-backup-v1",
        "columns": {name: list(values) for name, values in columns.items()},
        "tables": projection(conn, columns),
        "sequences": target_sequences(conn),
        "storage_sha256": hashlib.sha256(json.dumps(storage, separators=(",", ":")).encode()).hexdigest(),
        "import_manifest_sha256": hashlib.sha256(
            json.dumps(import_record, separators=(",", ":")).encode()).hexdigest(),
    }
    from app.literature import load_literature_items
    from app.reading_schema import TABLE, planned_projection, catalog_mapping_digest
    items = load_literature_items()
    if TABLE not in columns:
        # Capture the exact allowed derivation before schema/data writes.
        result["reading_work_migration"] = planned_projection(conn, items)
    else:
        result["reading_work_catalog_sha256"] = catalog_mapping_digest(items)
    return result



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
    for table in sorted(before_columns.keys() - REBUILDABLE_TABLES):
        if (table not in after_columns
                or before_columns[table] != after_columns[table]
                or before["tables"][table] != after["tables"][table]):
            raise ValueError("PostgreSQL migration changed pre-existing user state")
        if table in before["sequences"] and after["sequences"].get(table) != before["sequences"][table]:
            raise ValueError("PostgreSQL migration changed a user identity sequence")
    for table in sorted(after_columns.keys() - before_columns.keys() - REBUILDABLE_TABLES):
        if table == "user_literature_work_progress":
            from app.reading_contract import FIELDS, VERSION as READING_VERSION
            proof = before.get("reading_work_migration")
            if ("user_literature_progress" not in before_columns
                    or not isinstance(proof, dict) or proof.get("version") != READING_VERSION
                    or not isinstance(proof.get("catalog_sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", proof["catalog_sha256"]) is None
                    or proof.get("columns") != list(FIELDS)
                    or after_columns[table] != list(FIELDS)
                    or proof.get("projection") != after["tables"][table]
                    or proof.get("catalog_sha256") != after.get("reading_work_catalog_sha256")
                    or after["sequences"].get(table, 0) != 0):
                raise ValueError("New reading state does not match the verified legacy derivation")
            continue
        if (after["tables"][table]["rows"] != 0
                or after["sequences"].get(table, 0) != 0):
            raise ValueError("New user-state table must be empty during migration")
