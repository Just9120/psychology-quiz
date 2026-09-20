"""Atomic, reconciled import of an offline SQLite snapshot into an empty target.

The operator stops all writers and creates the snapshot before calling this code.
Neither the source nor an already populated target is repaired or overwritten.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

from app.database import Connection, begin_write, connect_database, is_postgres_target
from app.postgres_schema import BASE_TABLES, IDENTITY_TABLES, TABLES, initialize_schema, table_columns, verify_schema


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def projection(conn, columns: dict[str, tuple[str, ...]]) -> dict:
    result = {}
    for table in columns:
        fields = ",".join(map(quote_identifier, columns[table]))
        hashes = []
        for row in conn.execute(f"SELECT {fields} FROM {quote_identifier(table)}"):
            # Only TEXT / INTEGER / NULL are part of the canonical source contract.
            if any(type(value) not in (str, int, type(None)) for value in row):
                raise ValueError("Unsupported source data type")
            encoded = json.dumps(list(row), ensure_ascii=False, separators=(",", ":")).encode()
            hashes.append(hashlib.sha256(encoded).digest())
        result[table] = {"rows": len(hashes), "sha256": hashlib.sha256(b"".join(sorted(hashes))).hexdigest()}
    return result


def source_sequences(source) -> dict[str, int]:
    sequences = dict(source.execute("SELECT name,seq FROM sqlite_sequence"))
    if set(sequences) - set(IDENTITY_TABLES):
        raise ValueError("Unknown source identity sequence")
    return {table: max(int(sequences.get(table, 0)), int(source.execute(
        f"SELECT coalesce(max(id),0) FROM {quote_identifier(table)}").fetchone()[0])) for table in IDENTITY_TABLES}


def validate_source(source, columns: dict[str, tuple[str, ...]]) -> None:
    if list(source.execute("PRAGMA integrity_check")) != [("ok",)] or source.execute("PRAGMA foreign_key_check").fetchone():
        raise ValueError("SQLite integrity/foreign key check failed")
    tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if tables != set(columns) | {"sqlite_sequence"}:
        raise ValueError("Unknown or incomplete SQLite source schema")
    for table in columns:
        info = list(source.execute(f"PRAGMA table_info({quote_identifier(table)})"))
        if set(row[1] for row in info) != set(columns[table]) or any(row[2].upper() not in {"INTEGER", "TEXT"} for row in info):
            raise ValueError("Unsupported SQLite columns/types")
    versions = {row[0] for row in source.execute("SELECT version FROM schema_migrations")}
    required = {"identity-v1", "auth-v1"} | ({"glossary-v1"} if "glossary_sessions" in columns else set())
    if versions != required:
        raise ValueError("SQLite schema must be upgraded before creating the cutover snapshot")
    for encoded, digest, provenance in source.execute(
        "SELECT content_snapshot,content_sha256,snapshot_provenance FROM quiz_session_questions"
    ):
        if not encoded or hashlib.sha256(encoded.encode()).hexdigest() != digest or provenance not in {"captured", "legacy_backfill_current"}:
            raise ValueError("Source attempt content is missing or corrupt")
        content = json.loads(encoded)
        if content.get("version") != 1:
            raise ValueError("Unsupported attempt content version")


def target_sequences(conn: Connection) -> dict[str, int]:
    result = {}
    for table in IDENTITY_TABLES:
        sequence = conn.execute("SELECT pg_get_serial_sequence(?, 'id')", (table,)).fetchone()[0]
        # Server-generated sequence name, quoted as schema + relation.
        parts = conn.execute("SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=?::regclass", (sequence,)).fetchone()
        name = ".".join(map(quote_identifier, parts))
        row = conn.execute(f"SELECT last_value,is_called FROM {name}").fetchone()
        result[table] = row[0] if row[1] else 0
    return result


def import_snapshot(source_path: Path, target: str) -> dict:
    if not is_postgres_target(target):
        raise ValueError("Import target must be PostgreSQL")
    if not source_path.is_file():
        raise ValueError("SQLite snapshot does not exist")
    # mode=ro preserves the source. A read transaction fixes the view for all checks.
    with closing(sqlite3.connect(source_path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        source.execute("BEGIN")
        source_tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        tables = TABLES if "glossary_sessions" in source_tables else BASE_TABLES
        version = "postgres-v2" if "glossary_sessions" in source_tables else "postgres-v1"
        with closing(connect_database(target)) as conn, conn:
            begin_write(conn, "schema")
            initialize_schema(conn, version=version)
            # An accidentally running target writer must not interleave with the
            # empty-target check, reconciliation or sequence reset.
            conn.execute("LOCK TABLE " + ",".join(tables) + " IN ACCESS EXCLUSIVE MODE")
            columns = {table: fields for table, fields in table_columns(conn).items() if table in tables}
            validate_source(source, columns)
            manifest = {"version": 1, "tables": projection(source, columns), "sequences": source_sequences(source)}
            encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
            prior = conn.execute("SELECT import_manifest FROM postgres_storage WHERE singleton=1").fetchone()[0]
            if prior is not None:
                if prior != encoded or projection(conn, columns) != manifest["tables"] or target_sequences(conn) != manifest["sequences"]:
                    raise ValueError("Import was already performed and source/target has changed; refusing overwrite")
                return {"result": "already_verified", **manifest}
            if any(conn.execute(f"SELECT 1 FROM {quote_identifier(table)} LIMIT 1").fetchone() for table in tables):
                raise ValueError("Import requires an empty target")
            for table in tables:
                fields = ",".join(map(quote_identifier, columns[table]))
                query = f"INSERT INTO {quote_identifier(table)} ({fields}) VALUES ({','.join('?' for _ in columns[table])})"
                cursor = source.execute(f"SELECT {fields} FROM {quote_identifier(table)}")
                while batch := cursor.fetchmany(500):
                    conn.executemany(query, batch)
            if projection(conn, columns) != manifest["tables"]:
                raise ValueError("Import row reconciliation failed")
            for table, high_water in manifest["sequences"].items():
                conn.execute("SELECT setval(pg_get_serial_sequence(?, 'id'), ?, ?)",
                             (table, max(1, high_water), high_water > 0))
            if target_sequences(conn) != manifest["sequences"]:
                raise ValueError("Import sequence reconciliation failed")
            conn.execute("UPDATE postgres_storage SET import_manifest=? WHERE singleton=1", (encoded,))
            verify_schema(conn, allow_legacy=True)
            return {"result": "imported", **manifest}
