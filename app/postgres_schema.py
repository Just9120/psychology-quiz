"""Explicit PostgreSQL initialization and drift checks; no request-time DDL."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.database import Connection, begin_write, is_postgres

VERSION = "postgres-v3"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "postgres-v1.sql"
GLOSSARY_PATH = SCHEMA_PATH.with_name("glossary-v1.sql")
LEARNING_PATH = SCHEMA_PATH.with_name("learning-v1.sql")
BASE_TABLES = (
    "users", "categories", "questions", "question_options", "quiz_sessions",
    "quiz_session_selected_categories", "quiz_session_questions", "quiz_answers",
    "user_literature_progress", "schema_migrations", "web_accounts", "web_sessions",
    "web_mail_tokens", "web_link_tokens", "web_auth_limits",
)
V2_TABLES = BASE_TABLES + ("glossary_sessions",)
TABLES = V2_TABLES + ("user_learning_goals", "user_achievements", "user_review_events")
IDENTITY_TABLES = (
    "users", "categories", "questions", "question_options", "quiz_sessions",
    "quiz_session_questions", "quiz_answers", "user_literature_progress", "web_accounts",
)


def table_columns(conn: Connection) -> dict[str, tuple[str, ...]]:
    result = {}
    for row in conn.execute("""SELECT table_name,column_name FROM information_schema.columns
            WHERE table_schema=current_schema() ORDER BY table_name,ordinal_position"""):
        result.setdefault(row[0], []).append(row[1])
    return {name: tuple(columns) for name, columns in result.items()}


def catalog_digest(conn: Connection) -> str:
    """Exclude data/owners/OIDs; include columns, constraints, indexes and guards."""
    queries = (
        """SELECT table_name,column_name,data_type,is_nullable,column_default,is_identity,identity_generation
           FROM information_schema.columns WHERE table_schema=current_schema()
           ORDER BY table_name,ordinal_position""",
        """SELECT c.relname,k.conname,pg_get_constraintdef(k.oid) FROM pg_constraint k
           JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname=current_schema() ORDER BY c.relname,k.conname""",
        """SELECT tablename,indexname,indexdef FROM pg_indexes
           WHERE schemaname=current_schema() ORDER BY tablename,indexname""",
        """SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled FROM pg_trigger t
           JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname=current_schema() AND NOT t.tgisinternal ORDER BY c.relname,t.tgname""",
        """SELECT p.proname,pg_get_functiondef(p.oid) FROM pg_proc p
           JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname=current_schema() ORDER BY p.proname,p.oid""",
        """SELECT sequencename,data_type::text,start_value,min_value,max_value,increment_by,cycle,cache_size
           FROM pg_sequences WHERE schemaname=current_schema() ORDER BY sequencename""",
    )
    value = [[list(row) for row in conn.execute(query)] for query in queries]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def ddl_digest(version):
    if version not in {"postgres-v1", "postgres-v2", VERSION}:
        raise ValueError("Unsupported PostgreSQL schema version")
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    if version in {"postgres-v2", VERSION}:
        text += GLOSSARY_PATH.read_text(encoding="utf-8").replace("user_id INTEGER", "user_id BIGINT")
    if version == VERSION:
        text += LEARNING_PATH.read_text(encoding="utf-8")
    return hashlib.sha256(text.encode()).hexdigest()


def verify_schema(conn: Connection, *, allow_legacy=False) -> str:
    if not is_postgres(conn):
        raise ValueError("PostgreSQL connection required")
    columns = set(table_columns(conn))
    if "postgres_storage" not in columns:
        raise ValueError("Unknown or incomplete PostgreSQL schema; explicit migration required")
    row = conn.execute("SELECT version,ddl_sha256,catalog_sha256 FROM postgres_storage WHERE singleton=1").fetchone()
    if row is None or row[0] not in ({VERSION, "postgres-v1", "postgres-v2"} if allow_legacy else {VERSION}):
        raise ValueError("PostgreSQL schema version/drift check failed")
    tables = BASE_TABLES if row[0] == "postgres-v1" else V2_TABLES if row[0] == "postgres-v2" else TABLES
    if columns != set(tables) | {"postgres_storage"}:
        raise ValueError("Unknown or incomplete PostgreSQL schema; explicit migration required")
    if row[1] != ddl_digest(row[0]) or row[2] != catalog_digest(conn):
        raise ValueError("PostgreSQL schema version/drift check failed")
    return row[0]


def initialize_schema(conn: Connection, *, version=VERSION) -> None:
    """Caller owns transaction; unknown/nonempty namespaces are never adopted."""
    if not is_postgres(conn):
        raise ValueError("PostgreSQL connection required")
    begin_write(conn, "schema")
    ddl_digest(version)
    if table_columns(conn):
        if verify_schema(conn, allow_legacy=True) != version:
            raise ValueError("Explicit PostgreSQL upgrade required")
        return
    if conn.execute("""SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() LIMIT 1""").fetchone() or conn.execute("""
            SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname=current_schema() LIMIT 1""").fetchone():
        raise ValueError("PostgreSQL target namespace is not empty")
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    if version in {"postgres-v2", VERSION}:
        conn.execute(GLOSSARY_PATH.read_text(encoding="utf-8").replace("user_id INTEGER", "user_id BIGINT"))
    if version == VERSION:
        conn.execute(LEARNING_PATH.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO postgres_storage VALUES(1,?,?,?,NULL)",
                 (version, ddl_digest(version), catalog_digest(conn)))
    verify_schema(conn, allow_legacy=True)


def upgrade_schema(conn: Connection) -> None:
    """Only canonical init, with writers stopped and a verified backup, calls this."""
    begin_write(conn, "schema")
    previous = verify_schema(conn, allow_legacy=True)
    if previous == VERSION:
        return
    existing_tables = BASE_TABLES if previous == "postgres-v1" else V2_TABLES
    conn.execute("LOCK TABLE " + ",".join(existing_tables) + ",postgres_storage IN ACCESS EXCLUSIVE MODE")
    verify_schema(conn, allow_legacy=True)
    if previous == "postgres-v1":
        conn.execute(GLOSSARY_PATH.read_text(encoding="utf-8").replace("user_id INTEGER", "user_id BIGINT"))
    conn.execute(LEARNING_PATH.read_text(encoding="utf-8"))
    conn.execute("UPDATE postgres_storage SET version=?,ddl_sha256=?,catalog_sha256=? WHERE singleton=1",
                 (VERSION, ddl_digest(VERSION), catalog_digest(conn)))
    verify_schema(conn)
