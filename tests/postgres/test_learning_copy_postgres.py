"""Read-only learning copy must use the same PostgreSQL actor boundaries."""
from contextlib import closing
from io import StringIO
import json

from app.db import get_connection
from app.postgres_schema import initialize_schema
from app.privacy_export import write_learning_copy


def test_learning_copy_postgres_consistent_scope(pg_target):
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn)
        conn.execute("INSERT INTO users(id,telegram_user_id) VALUES(1,101),(2,202)")
        conn.execute("INSERT INTO quiz_sessions(id,user_id) VALUES(11,1),(22,2)")
    with closing(get_connection(pg_target)) as conn:
        output = StringIO()
        counts = write_learning_copy(conn, 1, output)
        result = json.loads(output.getvalue())
        assert result["complete"] is True
        assert counts["quiz_sessions"] == 1
        assert [row["id"] for row in result["tables"]["quiz_sessions"]] == [11]
        assert result["tables"]["quiz_answers"] == []
        assert not conn.in_transaction
        assert conn.execute("SELECT count(*) FROM quiz_sessions").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 2
