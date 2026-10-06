"""Explicit PostgreSQL initialization and drift checks; no request-time DDL."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.database import Connection, begin_write, is_postgres

VERSION = "postgres-v9"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "postgres-v1.sql"
GLOSSARY_PATH = SCHEMA_PATH.with_name("glossary-v1.sql")
LEARNING_PATH = SCHEMA_PATH.with_name("learning-v1.sql")
INVITATION_PATH = SCHEMA_PATH.with_name("invitations-v1.sql")
PROFILE_PATH = SCHEMA_PATH.with_name("profile-v1.sql")
HOMEWORK_PATH = SCHEMA_PATH.with_name("homework-v1.sql")
PRIVACY_PATH = SCHEMA_PATH.with_name("privacy-v1.sql")
READING_PATH = SCHEMA_PATH.with_name("reading-work-v1.sql")
OAUTH_PATH = SCHEMA_PATH.with_name("google-oauth-v1.sql")
BASE_TABLES = (
    "users", "categories", "questions", "question_options", "quiz_sessions",
    "quiz_session_selected_categories", "quiz_session_questions", "quiz_answers",
    "user_literature_progress", "schema_migrations", "web_accounts", "web_sessions",
    "web_mail_tokens", "web_link_tokens", "web_auth_limits",
)
V2_TABLES = BASE_TABLES + ("glossary_sessions",)
V3_TABLES = V2_TABLES + ("user_learning_goals", "user_achievements", "user_review_events", "user_review_sessions")
V4_TABLES = V3_TABLES + ("pwa_invitations",)
V5_TABLES = V4_TABLES + ("web_profile_names",)
V6_TABLES = V5_TABLES + ("homework_attempts",)
V7_TABLES = V6_TABLES + ("user_data_deletion_challenges",)
V8_TABLES = V7_TABLES + ("user_literature_work_progress",)
TABLES = V8_TABLES + ("web_google_identities", "web_oauth_challenges")
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


SCHEMA_VERSIONS = {
    "postgres-v1": BASE_TABLES, "postgres-v2": V2_TABLES, "postgres-v3": V3_TABLES,
    "postgres-v4": V4_TABLES, "postgres-v5": V5_TABLES, "postgres-v6": V6_TABLES,
    "postgres-v7": V7_TABLES, "postgres-v8": V8_TABLES, VERSION: TABLES,
}
SCHEMA_STEPS = (GLOSSARY_PATH, LEARNING_PATH, INVITATION_PATH, PROFILE_PATH,
                HOMEWORK_PATH, PRIVACY_PATH, READING_PATH, OAUTH_PATH)


def _version_number(version):
    if version not in SCHEMA_VERSIONS:
        raise ValueError("Unsupported PostgreSQL schema version")
    return int(version.removeprefix("postgres-v"))


def _step_ddl(path):
    text = path.read_text(encoding="utf-8")
    if path == OAUTH_PATH:
        return text.replace(" INTEGER", " BIGINT")
    return text.replace("user_id INTEGER", "user_id BIGINT") if path in {GLOSSARY_PATH, READING_PATH} else text


def ddl_digest(version):
    number = _version_number(version)
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    text += "".join(_step_ddl(path) for path in SCHEMA_STEPS[:number - 1])
    return hashlib.sha256(text.encode()).hexdigest()


def verify_schema(conn: Connection, *, allow_legacy=False) -> str:
    if not is_postgres(conn):
        raise ValueError("PostgreSQL connection required")
    columns = set(table_columns(conn))
    if "postgres_storage" not in columns:
        raise ValueError("Unknown or incomplete PostgreSQL schema; explicit migration required")
    row = conn.execute("SELECT version,ddl_sha256,catalog_sha256 FROM postgres_storage WHERE singleton=1").fetchone()
    if row is None or row[0] not in (SCHEMA_VERSIONS if allow_legacy else {VERSION}):
        raise ValueError("PostgreSQL schema version/drift check failed")
    if columns != set(SCHEMA_VERSIONS[row[0]]) | {"postgres_storage"}:
        raise ValueError("Unknown or incomplete PostgreSQL schema; explicit migration required")
    if row[1] != ddl_digest(row[0]) or row[2] != catalog_digest(conn):
        raise ValueError("PostgreSQL schema version/drift check failed")
    return row[0]


def initialize_schema(conn: Connection, *, version=VERSION) -> None:
    """Caller owns transaction; unknown/nonempty namespaces are never adopted."""
    if not is_postgres(conn):
        raise ValueError("PostgreSQL connection required")
    begin_write(conn, "schema")
    number = _version_number(version)
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
    for path in SCHEMA_STEPS[:number - 1]:
        conn.execute(_step_ddl(path))
    conn.execute("INSERT INTO postgres_storage VALUES(1,?,?,?,NULL)",
                 (version, ddl_digest(version), catalog_digest(conn)))
    verify_schema(conn, allow_legacy=True)


def upgrade_schema(conn: Connection) -> None:
    """Only canonical init, with writers stopped and a verified backup, calls this."""
    begin_write(conn, "schema")
    previous = verify_schema(conn, allow_legacy=True)
    if previous == VERSION:
        return
    conn.execute("LOCK TABLE " + ",".join(SCHEMA_VERSIONS[previous]) + ",postgres_storage IN ACCESS EXCLUSIVE MODE")
    verify_schema(conn, allow_legacy=True)
    for path in SCHEMA_STEPS[_version_number(previous) - 1:]:
        if path == READING_PATH:
            from app.literature import load_literature_items
            from app.reading_schema import migrate_reading_schema
            migrate_reading_schema(conn, load_literature_items())
        else:
            conn.execute(_step_ddl(path))
    conn.execute("UPDATE postgres_storage SET version=?,ddl_sha256=?,catalog_sha256=? WHERE singleton=1",
                 (VERSION, ddl_digest(VERSION), catalog_digest(conn)))
    verify_schema(conn)
