"""Actual pgvector contract in a disposable CI database, not production."""
from __future__ import annotations

import os

import psycopg
import pytest

from app.private_search import DIMENSIONS, SearchError, rebuild, search, verify_index_content


class SyntheticEmbedding:
    def embed(self, texts):
        for text in texts:
            value = [0.0] * DIMENSIONS
            value[0 if "поддерж" in text else 1] = 1.0
            yield value


def test_private_rebuild_keeps_learning_state_and_replaces_only_index():
    admin_dsn = os.environ["POSTGRES_SEARCH_TEST_ADMIN_DSN"]
    app_dsn = os.environ["POSTGRES_SEARCH_TEST_DSN"]
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        version = admin.execute("SHOW server_version").fetchone()[0]
        assert version.split()[0] == "18.6"
        admin.execute("CREATE ROLE psychology_app LOGIN PASSWORD 'synthetic-search-only'")
        admin.execute("CREATE SCHEMA private_search AUTHORIZATION psychology_app")
        admin.execute("CREATE EXTENSION vector WITH SCHEMA private_search VERSION '0.8.6'")
        admin.execute("CREATE TABLE public.learning_state_probe(actor bigint PRIMARY KEY, progress integer NOT NULL)")
        admin.execute("INSERT INTO public.learning_state_probe VALUES (7, 42)")

    first = [
        ("synthetic-source-a", "2026-09-27T00:00:00Z", "a" * 64, "characters:0:30",
         "поддержка в процессе обучения"),
        ("synthetic-source-b", "2026-09-27T00:00:00Z", "b" * 64, "characters:0:30",
         "структура психологической консультации"),
    ]
    with psycopg.connect(app_dsn) as conn:
        assert rebuild(conn, first, SyntheticEmbedding()) == 2
        conn.commit()
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        verify_index_content(conn, first)
        with psycopg.connect(app_dsn) as writer:
            assert rebuild(writer, first[1:], SyntheticEmbedding()) == 1
        matches = search(conn, "поддержка", SyntheticEmbedding(), limit=2)
        assert matches[0]["source_id"] == "synthetic-source-a"
        assert {item["source_id"] for item in matches} == {"synthetic-source-a", "synthetic-source-b"}
    with psycopg.connect(app_dsn) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        verify_index_content(conn, first[1:])
        with pytest.raises(SearchError, match="private_index_stale_for_review"):
            verify_index_content(conn, first)
        matches = search(conn, "поддержка", SyntheticEmbedding(), limit=2)
        assert [item["source_id"] for item in matches] == ["synthetic-source-b"]
    with psycopg.connect(admin_dsn) as admin:
        assert admin.execute("SELECT actor,progress FROM public.learning_state_probe").fetchall() == [(7, 42)]
        assert admin.execute("SELECT count(*) FROM private_search.chunks").fetchone()[0] == 1
