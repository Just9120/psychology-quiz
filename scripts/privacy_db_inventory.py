"""Read-only schema inventory for privacy review; never reads account rows.

This covers database storage only. Backups, logs, Telegram, SMTP and hosting
need separate owner/legal review before an account deletion procedure is set.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.database import is_postgres_target, resolve_database_target, validate_postgres_target


# Explicit classification is reviewed alongside schema changes. Paths describe
# data relationships, not permission to delete rows or a retention decision.
PERSONAL_TABLES = {
    "users": ("id", {"telegram_user_id", "username", "first_name", "last_name"}),
    "web_accounts": ("user_id/email", {"email", "password_hash", "user_id"}),
    "web_sessions": ("account_id", {"digest", "account_id"}),
    "web_mail_tokens": ("email/account_id", {"digest", "email", "account_id"}),
    "web_link_tokens": ("account_id/proposed_user_id", {"digest", "account_id", "proposed_user_id"}),
    "web_auth_limits": ("bucket; currently global, review before per-user limits", {"bucket"}),
    "quiz_sessions": ("user_id", {"user_id"}),
    "quiz_session_selected_categories": ("session_id", {"session_id"}),
    "quiz_session_questions": ("session_id", {"session_id", "content_snapshot"}),
    "quiz_answers": ("session_id", {"session_id"}),
    "glossary_sessions": ("user_id", {"user_id", "snapshot", "state"}),
    "user_literature_progress": ("user_id", {"user_id", "private_note"}),
    "user_learning_goals": ("user_id", {"user_id"}),
    "user_achievements": ("user_id", {"user_id", "evidence_key"}),
    "user_review_events": ("user_id", {"user_id", "answer_key"}),
    "user_review_sessions": ("user_id", {"user_id", "session_key"}),
}
OTHER_TABLES = {"categories", "questions", "question_options",
                "schema_migrations", "postgres_storage"}


def sqlite_schema(conn) -> tuple[dict[str, set[str]], list[dict[str, str]]]:
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    columns, foreign_keys = {}, []
    for table in sorted(tables):
        quoted = '"' + table.replace('"', '""') + '"'
        columns[table] = {row[1] for row in conn.execute(f"PRAGMA table_info({quoted})")}
        for row in conn.execute(f"PRAGMA foreign_key_list({quoted})"):
            foreign_keys.append({"table": table, "column": row[3],
                                 "references": row[2], "on_delete": row[6]})
    return columns, foreign_keys


def postgres_schema(conn) -> tuple[dict[str, set[str]], list[dict[str, str]]]:
    columns = {}
    for table, column in conn.execute("""SELECT c.table_name,c.column_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema=c.table_schema AND t.table_name=c.table_name
        WHERE c.table_schema=current_schema() AND t.table_type='BASE TABLE'"""):
        columns.setdefault(table, set()).add(column)
    keys = [{"table": table, "column": column, "references": referenced,
             "on_delete": rule} for table, column, referenced, rule in conn.execute("""
        SELECT tc.table_name,kcu.column_name,ccu.table_name,rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_catalog=kcu.constraint_catalog
         AND tc.constraint_schema=kcu.constraint_schema
         AND tc.constraint_name=kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_catalog=ccu.constraint_catalog
         AND tc.constraint_schema=ccu.constraint_schema
         AND tc.constraint_name=ccu.constraint_name
        JOIN information_schema.referential_constraints rc
          ON tc.constraint_catalog=rc.constraint_catalog
         AND tc.constraint_schema=rc.constraint_schema
         AND tc.constraint_name=rc.constraint_name
        WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema=current_schema()
    """)]
    return columns, keys


def inventory(columns: dict[str, set[str]], foreign_keys: list[dict[str, str]]) -> dict:
    present = set(columns)
    personal = {}
    for table, (owner_path, expected) in PERSONAL_TABLES.items():
        personal[table] = {"present": table in present, "owner_path": owner_path,
                           "columns": sorted(columns.get(table, set())),
                           "missing_columns": sorted(expected - columns.get(table, set()))}
    return {"scope": "database_schema_only", "personal_tables": personal,
            "other_tables_to_review": sorted(present & OTHER_TABLES),
            "unclassified_tables": sorted(present - PERSONAL_TABLES.keys() - OTHER_TABLES),
            "foreign_keys": sorted(foreign_keys, key=lambda key: (
                key["table"], key["column"], key["references"], key["on_delete"])),
            "external_flows": "UNSET: backups, logs, Telegram, SMTP, VPS and Cloudflare require separate review"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inventory personal-data schema without reading rows")
    parser.parse_args(argv)
    try:
        target = resolve_database_target(require_sqlite_path=True)
        if is_postgres_target(target):
            import psycopg
            with closing(psycopg.connect(validate_postgres_target(target),
                                         options="-c default_transaction_read_only=on")) as conn:
                columns, keys = postgres_schema(conn)
        else:
            path = Path(target).resolve(strict=True)
            if not path.is_file():
                raise ValueError("SQLite target must be an existing file")
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
                columns, keys = sqlite_schema(conn)
        print(json.dumps(inventory(columns, keys), ensure_ascii=False, sort_keys=True))
    except Exception as error:
        # Driver exceptions can include a DSN or private path; never echo them.
        print("PRIVACY_DB_INVENTORY_STOP: " + type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
