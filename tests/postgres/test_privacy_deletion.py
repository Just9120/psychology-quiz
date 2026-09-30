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
        conn.execute("INSERT INTO categories(id,slug,name) VALUES(1,'privacy-test','Privacy test')")
        conn.execute("""INSERT INTO questions(id,external_id,category_id,question_text)
                        VALUES(1,'privacy-question',1,'Shared bank question')""")
        conn.execute("INSERT INTO quiz_sessions(id,user_id) VALUES(11,1),(22,2)")
        conn.execute("""INSERT INTO quiz_answers(session_id,question_id,selected_option_index,is_correct)
                        VALUES(11,1,0,1),(22,1,0,1)""")
        conn.execute("""INSERT INTO quiz_session_questions(session_id,question_id,order_index)
                        VALUES(11,1,0),(22,1,0)""")
        conn.execute("""INSERT INTO quiz_session_selected_categories(session_id,category_id)
                        VALUES(11,1),(22,1)""")
        conn.execute("""INSERT INTO homework_attempts(session_id,assignment_id)
                        VALUES(11,'assignment-1'),(22,'assignment-2')""")
        conn.execute("""INSERT INTO glossary_sessions
                        (id,user_id,topic_id,topic_title,status,snapshot,state,created_at,updated_at)
                        VALUES('glossary-1',1,'term','Term','completed','{}','{}','now','now'),
                              ('glossary-2',2,'term','Term','completed','{}','{}','now','now')""")
        conn.execute("""INSERT INTO user_learning_goals(user_id,goal_kind,weekly_target,updated_at)
                        VALUES(1,'study',2,'now'),(2,'study',3,'now')""")
        conn.execute("""INSERT INTO user_literature_progress(user_id,literature_id,reading_status,updated_at,private_note)
                        VALUES(1,'legacy','read','now','private'),(2,'legacy','read','now','private')""")
        conn.execute("""INSERT INTO user_literature_work_progress(user_id,work_id,reading_status,updated_at,source_literature_id)
                        VALUES(1,'book','read','now','entry'),(2,'book','read','now','entry')""")
        prepared = prepare_learning_data_deletion(conn, 1)
        token = prepared["confirmation_token"]

    with closing(get_connection(pg_target)) as conn, conn:
        with pytest.raises(PrivacyError, match="invalid_confirmation"):
            confirm_learning_data_deletion(conn, 2, token)

    with closing(get_connection(pg_target)) as conn, conn:
        assert confirm_learning_data_deletion(conn, 1, token)["telegram_access_retained"] is True
        assert conn.execute("SELECT user_id FROM quiz_sessions").fetchone()[0] == 2
        assert conn.execute("SELECT user_id FROM user_learning_goals").fetchone()[0] == 2
        for table in ('user_literature_progress', 'user_literature_work_progress'):
            assert conn.execute(f"SELECT user_id FROM {table}").fetchall()[0][0] == 2
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1
        for table in ('quiz_answers', 'quiz_session_questions',
                      'quiz_session_selected_categories', 'homework_attempts'):
            assert [row[0] for row in conn.execute(f"SELECT session_id FROM {table}")] == [22]
        assert [row[0] for row in conn.execute("SELECT user_id FROM glossary_sessions")] == [2]
        assert conn.execute("SELECT count(*) FROM questions").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM categories").fetchone()[0] == 1
        assert [row[0] for row in conn.execute("SELECT telegram_user_id FROM users ORDER BY id")] == [101, 202]
        assert conn.execute("SELECT count(*) FROM user_data_deletion_challenges").fetchone()[0] == 0
        with pytest.raises(PrivacyError, match="invalid_confirmation"):
            confirm_learning_data_deletion(conn, 1, token)
