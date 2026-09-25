"""The additive learning migration must preserve legacy attempts and user state."""
from contextlib import closing
from pathlib import Path

import pytest

from app.db import get_connection
from app.identity_schema import migrate_identity_schema
from app.learning_schema import migrate_learning_schema
from scripts.deployment_db import user_state


def test_learning_migration_preserves_history_and_rejects_partial_schema(tmp_path):
    path = tmp_path / "quiz.sqlite3"
    with closing(get_connection(str(path))) as conn, conn:
        conn.executescript(Path("sql/schema.sql").read_text(encoding="utf-8"))
        migrate_identity_schema(conn)
        conn.execute("INSERT INTO users(telegram_user_id) VALUES(42)")
        conn.execute("INSERT INTO categories(slug,name) VALUES('old','Old')")
        conn.execute("INSERT INTO questions(external_id,category_id,question_text) VALUES('old-q',1,'Old question')")
        conn.execute("INSERT INTO question_options(question_id,option_index,option_text,is_correct) VALUES(1,0,'A',1),(1,1,'B',0)")
        conn.execute("INSERT INTO quiz_sessions(user_id,status,score,total_questions) VALUES(1,'finished',1,1)")
        conn.execute("INSERT INTO quiz_session_questions(session_id,question_id,order_index) VALUES(1,1,1)")
        conn.execute("INSERT INTO quiz_answers(session_id,question_id,selected_option_index,is_correct) VALUES(1,1,0,1)")
        before = user_state(conn)
        migrate_learning_schema(conn)
        assert user_state(conn, before) == before
        assert tuple(conn.execute("SELECT kind,case_content FROM questions WHERE id=1").fetchone()) == ("theory", None)
        migrate_learning_schema(conn)
        assert conn.execute("SELECT count(*) FROM schema_migrations WHERE version='learning-v1'").fetchone()[0] == 1
        conn.execute("DROP TABLE user_achievements")
        with pytest.raises(ValueError, match="incomplete"):
            migrate_learning_schema(conn)
