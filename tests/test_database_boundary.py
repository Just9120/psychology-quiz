import pytest

from app.database import postgres_parameters, resolve_database_target


def test_qmark_adapter_keeps_literals_identifiers_comments_and_percent_values():
    query = "SELECT ?, '? 100%', \"?\", $$? %$$, $tag$?$tag$ -- ?\n/* ? /* nested */ */ WHERE x LIKE ?"
    assert postgres_parameters(query) == "SELECT %s, '? 100%%', \"?\", $$? %%$$, $tag$?$tag$ -- ?\n/* ? /* nested */ */ WHERE x LIKE %s"


@pytest.mark.parametrize("value", ["sqlite:///other", "postgresql://localhost", "postgresql://user@host/db#fragment", "postgresql://user@host:99999/db"])
def test_invalid_explicit_database_url_never_falls_back_to_sqlite(monkeypatch, value):
    monkeypatch.setenv("DATABASE_URL", value)
    monkeypatch.setenv("DB_PATH", "unrelated.sqlite3")
    with pytest.raises(ValueError, match="DATABASE_URL"):
        resolve_database_target()


def test_explicit_database_url_precedes_sqlite_path(monkeypatch):
    target = "postgresql://synthetic:private@localhost/psychology_test"
    monkeypatch.setenv("DATABASE_URL", target)
    monkeypatch.setenv("DB_PATH", "unused.sqlite3")
    assert resolve_database_target() == target
