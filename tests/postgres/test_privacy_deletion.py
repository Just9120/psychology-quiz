"""The destructive Telegram flow must respect PostgreSQL actor boundaries."""
from contextlib import closing

import pytest

from app.db import get_connection
from app.postgres_schema import initialize_schema
from app.privacy_data import PrivacyError, confirm_learning_data_deletion, prepare_learning_data_deletion


def test_confirm_deletes_only_requesting_actors_learning_rows(pg_target):
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn)
        conn.execute("INSERT INTO users(id,telegram_user_id) VALUES(1,101),(2,202)")
        conn.execute("INSERT INTO quiz_sessions(id,user_id) VALUES(11,1),(22,2)")
        conn.execute("""INSERT INTO user_learning_goals(user_id,goal_kind,weekly_target,updated_at)
                        VALUES(1,'study',2,'now'),(2,'study',3,'now')""")
        prepared = prepare_learning_data_deletion(conn, 1)
        token = prepared["confirmation_token"]

    with closing(get_connection(pg_target)) as conn, conn:
        with pytest.raises(PrivacyError, match="invalid_confirmation"):
            confirm_learning_data_deletion(conn, 2, token)

    with closing(get_connection(pg_target)) as conn, conn:
        assert confirm_learning_data_deletion(conn, 1, token)["telegram_access_retained"] is True
        assert conn.execute("SELECT user_id FROM quiz_sessions").fetchone()[0] == 2
        assert conn.execute("SELECT user_id FROM user_learning_goals").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 2
        with pytest.raises(PrivacyError, match="invalid_confirmation"):
            confirm_learning_data_deletion(conn, 1, token)
