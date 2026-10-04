"""Actual pgvector contract in a disposable CI database, not production."""
from __future__ import annotations

import os
from contextlib import closing

import psycopg
import pytest

from app.database import connect_database
from app.private_search import DIMENSIONS, SearchError, rebuild, search, verify_index_content
from app.postgres_schema import initialize_schema


class SyntheticEmbedding:
    def embed(self, texts):
        for text in texts:
            value = [0.0] * DIMENSIONS
            value[0 if "поддерж" in text else 1] = 1.0
            yield value


class FailingAfterFirstBatch(SyntheticEmbedding):
    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        if self.calls == 2:
            yield [0.0]
            return
        yield from super().embed(texts)


def learning_state(dsn):
    """Read the actual application rows, not only the CI restore probe."""
    with psycopg.connect(dsn) as conn:
        return tuple(tuple(conn.execute(query).fetchall()) for query in (
            "SELECT id,telegram_user_id,reading_mode FROM users ORDER BY id",
            "SELECT id,user_id,category_id,status,score FROM quiz_sessions ORDER BY id",
            "SELECT id,session_id,question_id,is_correct FROM quiz_answers ORDER BY id",
            "SELECT user_id,goal_kind,weekly_target FROM user_learning_goals ORDER BY user_id,goal_kind",
            "SELECT user_id,literature_id,reading_status,progress_percent FROM user_literature_progress ORDER BY user_id,literature_id",
        ))


def test_private_rebuild_keeps_learning_state_and_replaces_only_index():
    admin_dsn = os.environ["POSTGRES_SEARCH_TEST_ADMIN_DSN"]
    app_dsn = os.environ["POSTGRES_SEARCH_TEST_DSN"]
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        version = admin.execute("SHOW server_version").fetchone()[0]
        assert version.split()[0] == "18.6"
        admin.execute("CREATE ROLE psychology_app LOGIN PASSWORD 'synthetic-search-only'")
        admin.execute("GRANT CREATE ON SCHEMA public TO psychology_app")
        admin.execute("CREATE SCHEMA private_search AUTHORIZATION psychology_app")
        admin.execute("CREATE EXTENSION vector WITH SCHEMA private_search VERSION '0.8.6'")

    with closing(connect_database(app_dsn)) as app, app:
        initialize_schema(app)
        app.execute("INSERT INTO users(id,telegram_user_id,reading_mode) VALUES(7,7007,'large')")
        app.execute("INSERT INTO categories(id,slug,name) VALUES(11,'synthetic','Synthetic')")
        app.execute("""INSERT INTO questions(id,external_id,category_id,question_text,explanation)
            VALUES(19,'synthetic-q',11,'Synthetic question','Synthetic answer')""")
        app.execute("""INSERT INTO quiz_sessions(id,user_id,category_id,status,score,total_questions)
            VALUES(23,7,11,'completed',1,1)""")
        app.execute("""INSERT INTO quiz_answers(id,session_id,question_id,is_correct)
            VALUES(29,23,19,1)""")
        app.execute("""INSERT INTO user_learning_goals(user_id,goal_kind,weekly_target,updated_at)
            VALUES(7,'study',3,'2026-09-28 00:00:00')""")
        app.execute("""INSERT INTO user_literature_progress(
            user_id,literature_id,reading_status,progress_percent,updated_at)
            VALUES(7,'synthetic-book','in_progress',40,'2026-09-28 00:00:00')""")

    before = learning_state(admin_dsn)
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute("CREATE TABLE public.learning_state_probe(actor bigint PRIMARY KEY, progress integer NOT NULL)")
        admin.execute("INSERT INTO public.learning_state_probe VALUES (7, 42)")

    first = [
        ("synthetic-source-a", "2026-09-27T00:00:00Z", "a" * 64, "characters:0:30",
         "поддержка в процессе обучения"),
        ("synthetic-source-b", "2026-09-27T00:00:00Z", "b" * 64, "characters:0:30",
         "структура психологической консультации"),
    ]
    with psycopg.connect(app_dsn) as conn:
        cases = [{"query": "поддержка", "source_id": first[0][0],
                  "snapshot_sha256": first[0][2], "locator": first[0][3], "mode": "lexical"}]
        assert rebuild(conn, first, SyntheticEmbedding(), qa_cases=cases) == 2
        conn.commit()
        # A valid replacement that fails retrieval QA must not replace the
        # previously committed index, even after all its rows were inserted.
        with pytest.raises(SearchError, match="private_retrieval_qa_failed"):
            rebuild(conn, first[1:], SyntheticEmbedding(), qa_cases=cases)
        conn.rollback()
        verify_index_content(conn, first)
        conn.commit()
        interrupted = [
            ("synthetic-source-c", "2026-09-27T00:00:00Z", "c" * 64,
             f"characters:{index}:{index + 1}", f"поддержка {index}")
            for index in range(33)
        ]
        with pytest.raises(SearchError, match="invalid_embedding_dimensions"):
            rebuild(conn, interrupted, FailingAfterFirstBatch())
        # verify_private_schema starts an outer transaction before rebuild's
        # savepoint; close it before selecting a read-only snapshot.
        conn.rollback()
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
    assert learning_state(admin_dsn) == before
