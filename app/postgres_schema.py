"""Explicit PostgreSQL initialization and drift checks; no request-time DDL."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.database import Connection, begin_write, is_postgres

VERSION = "postgres-v1"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "postgres-v1.sql"
TABLES = (
    "users", "categories", "questions", "question_options", "quiz_sessions",
    "quiz_session_selected_categories", "quiz_session_questions", "quiz_answers",
    "user_literature_progress", "schema_migrations", "web_accounts", "web_sessions",
    "web_mail_tokens", "web_link_tokens", "web_auth_limits",
)
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


def verify_schema(conn: Connection) -> None:
    if not is_postgres(conn):
        raise ValueError("PostgreSQL connection required")
    if set(table_columns(conn)) != set(TABLES) | {"postgres_storage"}:
        raise ValueError("Unknown or incomplete PostgreSQL schema; explicit migration required")
    row = conn.execute("SELECT version,ddl_sha256,catalog_sha256 FROM postgres_storage WHERE singleton=1").fetchone()
    expected = hashlib.sha256(SCHEMA_PATH.read_text(encoding="utf-8").encode()).hexdigest()
    if row is None or row[0] != VERSION or row[1] != expected or row[2] != catalog_digest(conn):
        raise ValueError("PostgreSQL schema version/drift check failed")


def initialize_schema(conn: Connection) -> None:
    """Caller owns transaction; unknown/nonempty namespaces are never adopted."""
    if not is_postgres(conn):
        raise ValueError("PostgreSQL connection required")
    begin_write(conn, "schema")
    if table_columns(conn):
        verify_schema(conn)
        return
    if conn.execute("""SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() LIMIT 1""").fetchone() or conn.execute("""
            SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname=current_schema() LIMIT 1""").fetchone():
        raise ValueError("PostgreSQL target namespace is not empty")
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO postgres_storage VALUES(1,?,?,?,NULL)",
                 (VERSION, hashlib.sha256(SCHEMA_PATH.read_text(encoding="utf-8").encode()).hexdigest(), catalog_digest(conn)))
    verify_schema(conn)
