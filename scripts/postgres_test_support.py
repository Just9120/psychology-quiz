"""Owned disposable PostgreSQL schemas for pytest and browser fixtures only."""
from contextlib import contextmanager
import os
from urllib.parse import urlencode, urlsplit, urlunsplit
import uuid

import psycopg
from psycopg import sql


def test_target(value: str):
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.path.removeprefix("/").startswith("psychology_test") or parsed.query:
        raise ValueError("Test DSN must name a dedicated psychology_test database without options")
    return parsed


@contextmanager
def isolated_postgres_target(target: str):
    parsed = test_target(target)
    schema = "test_" + uuid.uuid4().hex
    with psycopg.connect(target, autocommit=True) as admin:
        if admin.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user").fetchone()[0]:
            raise ValueError("Run PostgreSQL behavioral tests as a non-superuser")
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield urlunsplit(parsed._replace(query=urlencode({"options": "-csearch_path=" + schema})))
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def prepare_ci_role():
    """Ephemeral CI service only; credentials are public synthetic test values."""
    target = os.environ["POSTGRES_TEST_ADMIN_DSN"]
    parsed = test_target(target)
    if parsed.hostname not in {"localhost", "127.0.0.1"} or parsed.path != "/psychology_test":
        raise ValueError("CI fixture provisioning requires loopback psychology_test")
    with psycopg.connect(target, autocommit=True) as conn:
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='psychology_test_app'").fetchone():
            raise ValueError("CI fixture role already exists; refusing to modify it")
        conn.execute("CREATE ROLE psychology_test_app LOGIN PASSWORD 'synthetic-test-only' NOSUPERUSER NOCREATEDB NOCREATEROLE")
        conn.execute("GRANT CONNECT,CREATE ON DATABASE psychology_test TO psychology_test_app")


if __name__ == "__main__":
    prepare_ci_role()
    print("POSTGRES_TEST_ROLE_READY")
