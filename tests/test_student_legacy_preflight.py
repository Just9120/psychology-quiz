import sqlite3

import pytest

from scripts.student_legacy_preflight import inspect, main


def test_inventory_counts_existing_links_without_exposing_or_changing_rows():
    with sqlite3.connect(":memory:") as conn:
        conn.executescript("""CREATE TABLE web_accounts(email TEXT, user_id INTEGER);
            INSERT INTO web_accounts VALUES('owner@example.test',42),('other@example.test',91);
            CREATE TABLE pwa_invitations(token_digest TEXT,expires_at INTEGER,consumed_at INTEGER,account_id INTEGER);
            INSERT INTO pwa_invitations VALUES('private-token',200,NULL,NULL),('expired-secret',50,NULL,NULL),(NULL,NULL,90,7);
        """)
        before = conn.total_changes
        conn.execute("PRAGMA query_only=ON")
        result = inspect(conn, owner_email="OWNER@example.test", now=100)
        assert result["web_accounts"] == 2
        assert result["non_owner_accounts"] == result["non_owner_linked_accounts"] == 1
        assert result["invitation_rows"] == 3
        assert result["pending_tokens"] == result["expired_tokens"] == result["consumed_invitations"] == result["invitation_linked_accounts"] == 1
        assert result["review_required"] is True
        assert conn.total_changes == before
        assert 'private-token' not in str(result) and '@' not in str(result)


def test_unknown_owner_and_missing_tables_are_not_reported_as_empty():
    with sqlite3.connect(":memory:") as conn:
        result = inspect(conn, now=100)
        assert result["owner_configured"] is False
        assert result["web_accounts"] is None and result["invitation_rows"] is None
        assert result["non_owner_accounts"] is None
        assert result["review_required"] is True


def test_missing_database_is_not_created(tmp_path, monkeypatch):
    path = tmp_path / "missing.sqlite"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_PATH", str(path))
    with pytest.raises(sqlite3.OperationalError):
        main()
    assert not path.exists()
