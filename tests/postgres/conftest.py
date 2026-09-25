"""Isolated real PostgreSQL schemas; the target must be a dedicated test DB."""
from contextlib import closing
import os
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from scripts.postgres_test_support import isolated_postgres_target
from app.auth_schema import migrate_auth_schema
from app.glossary_schema import migrate_glossary_schema
from app.identity_schema import migrate_identity_schema
from app.db import get_connection
from app.miniapp_fastapi import create_app
from app.postgres_import import import_snapshot
from tests.test_attempt_content import bank as sqlite_bank, TOKEN
from tests.test_web_auth import Mailbox, SETTINGS, ORIGIN


def remove_learning_schema(conn):
    """Build an actual v1/v2 SQLite source for upgrade/recovery tests."""
    for table in ("user_review_events", "user_achievements", "user_learning_goals"):
        conn.execute(f"DROP TABLE {table}")
    conn.execute("ALTER TABLE questions DROP COLUMN case_content")
    conn.execute("ALTER TABLE questions DROP COLUMN kind")
    conn.execute("DELETE FROM schema_migrations WHERE version='learning-v1'")


@pytest.fixture
def pg_target():
    target = os.environ.get("POSTGRES_TEST_DSN")
    if not target:
        if os.environ.get("CI"):
            pytest.fail("Required CI PostgreSQL target is missing")
        pytest.skip("POSTGRES_TEST_DSN not set; required PostgreSQL job runs this suite")
    with isolated_postgres_target(target) as isolated:
        yield isolated


@pytest.fixture
def source(sqlite_bank):
    with closing(get_connection(str(sqlite_bank))) as conn, conn:
        migrate_identity_schema(conn)
        migrate_auth_schema(conn)
        migrate_glossary_schema(conn)
    return sqlite_bank


@pytest.fixture
def bank(source, pg_target):
    import_snapshot(source, pg_target)
    return pg_target


@pytest.fixture
def web(bank):
    now, mailbox = [1800000000], Mailbox()
    app = create_app(db_path=bank, bot_token=TOKEN, web_settings=SETTINGS, web_mailer=mailbox, web_clock=lambda: now[0])
    with TestClient(app, base_url=ORIGIN) as client:
        yield SimpleNamespace(db=bank, app=app, client=client, mailbox=mailbox, now=now, auth=app.state.web_auth)
