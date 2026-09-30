"""Explicit additive work-level reading migration; legacy rows remain history.

The caller owns the transaction and deployment preconditions (stopped writers,
verified backup). This module never commits, deletes, or rewrites legacy rows.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from app.database import begin_write, is_postgres

VERSION = "reading-work-v1"
TABLE = "user_literature_work_progress"
SQL_PATH = Path(__file__).resolve().parent.parent / "sql" / "reading-work-v1.sql"
STATUS_MAP = {"not_started": "not_started", "in_progress": "in_progress",
              "read": "read", "revisit": "deferred", "skipped": "deferred"}
FIELDS = ("user_id", "work_id", "reading_status", "started_at", "completed_at",
          "updated_at", "last_opened_at", "source_literature_id")
COLUMNS = set(FIELDS)
LEGACY_FIELDS = ("user_id", "literature_id", "reading_status", "progress_percent", "started_at",
                 "completed_at", "updated_at", "last_opened_at", "private_note", "remind_at")


def _timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Legacy SQLite CURRENT_TIMESTAMP is UTC without an explicit offset.
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def plan_legacy_reading(rows, items):
    """Select only proven catalog identities; ambiguity prevents all writes."""
    identities = {}
    for item in items:
        identity, work = item["id"], item["work_id"]
        if not isinstance(work, str) or not work.strip():
            raise ValueError("Invalid reading work identity")
        if identity in identities and identities[identity] != work:
            raise ValueError("Ambiguous reading work identity")
        identities[identity] = work
    groups = defaultdict(list)
    unknown = 0
    for row in rows:
        row = dict(row)
        if row["reading_status"] not in STATUS_MAP:
            raise ValueError("Unknown legacy reading status")
        work = identities.get(row["literature_id"])
        if work is None:
            unknown += 1
            continue
        groups[(row["user_id"], work)].append(row)
    result = []
    for (user, work), entries in sorted(groups.items()):
        statuses = {STATUS_MAP[row["reading_status"]] for row in entries}
        times = [_timestamp(row["updated_at"]) for row in entries]
        if len(statuses) > 1 and any(stamp is None for stamp in times):
            raise ValueError("Reading state conflict requires a valid timestamp")
        dated = [(stamp, row) for stamp, row in zip(times, entries) if stamp is not None]
        if dated:
            latest = max(stamp for stamp, _ in dated)
            candidates = [row for stamp, row in dated if stamp == latest]
        else:
            candidates = entries
        if len({STATUS_MAP[row["reading_status"]] for row in candidates}) > 1:
            raise ValueError("Reading state conflict at the latest timestamp")
        selected = min(candidates, key=lambda row: row["literature_id"])
        result.append({"user_id": user, "work_id": work,
                       "reading_status": STATUS_MAP[selected["reading_status"]],
                       "started_at": selected["started_at"], "completed_at": selected["completed_at"],
                       "updated_at": selected["updated_at"], "last_opened_at": selected["last_opened_at"],
                       "source_literature_id": selected["literature_id"]})
    return result, unknown


def legacy_rows(conn):
    # Canonical SQLite init uses tuple rows; no row-factory mutation is needed.
    return [dict(zip(LEGACY_FIELDS, row)) for row in conn.execute(
        "SELECT " + ",".join(LEGACY_FIELDS) + " FROM user_literature_progress ORDER BY user_id,literature_id")]


def catalog_mapping_digest(items):
    pairs = sorted((item["id"], item["work_id"]) for item in items)
    return hashlib.sha256(json.dumps(pairs, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def planned_projection(conn, items):
    """Same row projection as backup reconciliation, with no personal values output."""
    planned, unknown = plan_legacy_reading(legacy_rows(conn), items)
    hashes = [hashlib.sha256(json.dumps([row[field] for field in FIELDS],
               ensure_ascii=False, separators=(",", ":")).encode()).digest() for row in planned]
    return {"version": VERSION, "columns": list(FIELDS),
            "projection": {"rows": len(planned), "sha256": hashlib.sha256(b"".join(sorted(hashes))).hexdigest()},
            "catalog_sha256": catalog_mapping_digest(items),
            "unknown_association_rows_preserved": unknown}


def insert_planned_rows(conn, planned):
    for row in planned:
        conn.execute(f"INSERT INTO {TABLE} ({','.join(FIELDS)}) VALUES (?,?,?,?,?,?,?,?)",
                     tuple(row[field] for field in FIELDS))


def populate_imported_reading(conn, items):
    """Only verified current empty targets importing a legacy schema call this."""
    if conn.execute(f"SELECT 1 FROM {TABLE} LIMIT 1").fetchone():
        raise ValueError("Imported reading state requires an empty work table")
    planned, unknown = plan_legacy_reading(legacy_rows(conn), items)
    insert_planned_rows(conn, planned)
    return {"work_rows": len(planned), "unknown_association_rows_preserved": unknown}


def migrate_reading_schema(conn, items):
    """Run only from explicit initialization; marker never replays personal state."""
    begin_write(conn, "schema")
    marker = conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (VERSION,)).fetchone()
    if is_postgres(conn):
        columns = {row[0] for row in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?",
            (TABLE,))}
    else:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    if marker:
        if columns != COLUMNS:
            raise ValueError("Reading work schema is incomplete")
        return {"already_applied": True}
    if columns:
        raise ValueError("Unknown partial reading work schema; refusing adoption")
    rows = legacy_rows(conn)
    # Validate the complete plan before DDL or data writes.
    planned, unknown = plan_legacy_reading(rows, items)
    ddl = SQL_PATH.read_text(encoding="utf-8")
    if is_postgres(conn):
        ddl = ddl.replace("user_id INTEGER", "user_id BIGINT")
    for statement in ddl.split(";"):
        if statement.strip():
            conn.execute(statement)
    insert_planned_rows(conn, planned)
    conn.execute("INSERT INTO schema_migrations(version) VALUES(?)", (VERSION,))
    return {"already_applied": False, "legacy_rows_preserved": len(rows),
            "work_rows": len(planned), "unknown_association_rows_preserved": unknown}
