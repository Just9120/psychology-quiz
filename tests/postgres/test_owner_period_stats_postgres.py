"""Rolling owner aggregates respect mixed UTC formats on the native schema."""
from contextlib import closing
from datetime import datetime, timezone

from app.db import get_connection, get_owner_period_stats
from app.postgres_schema import initialize_schema


def test_period_counts_and_identity_projection_on_postgres(pg_target):
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn)
        conn.execute("INSERT INTO users(id,telegram_user_id) VALUES(10,101),(20,202),(30,303)")
        conn.execute("INSERT INTO categories(id,slug,name) VALUES(1,'stats-test','Stats test')")
        conn.execute("""INSERT INTO questions(id,external_id,category_id,question_text)
                        VALUES(1,'stats-question',1,'Shared bank question')""")
        conn.execute("""INSERT INTO quiz_sessions(id,user_id,started_at,finished_at,status) VALUES
                        (1,10,'2026-09-29 10:00:00','2026-09-29 11:00:00','finished'),
                        (2,10,'2026-09-28T11:59:59+00:00','2026-09-28T11:59:59+00:00','finished'),
                        (3,20,'2026-09-10 10:00:00','2026-09-10 11:00:00','finished')""")
        conn.execute("""INSERT INTO quiz_answers(session_id,question_id,selected_option_index,is_correct,answered_at)
                        VALUES(1,1,0,1,'2026-09-29 10:30:00'),
                              (2,1,0,1,'2026-09-28T11:59:59+00:00')""")
        conn.execute("""INSERT INTO glossary_sessions
                        (id,user_id,topic_id,topic_title,status,snapshot,state,created_at,updated_at)
                        VALUES('stats-glossary',20,'term','Term','completed','{}','{}',
                               '2026-09-26T10:00:00+00:00','2026-09-26T11:00:00+00:00')""")
        conn.execute("""INSERT INTO user_literature_work_progress
                        (user_id,work_id,reading_status,updated_at,source_literature_id)
                        VALUES(30,'book','reading','2026-09-29T09:00:00+00:00','entry')""")
        now = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
        results = [get_owner_period_stats(conn, period, now=now) for period in ('24h', '7d', '30d')]
        assert [row['active_users'] for row in results] == [2, 3, 3]
        assert [row['quiz_started'] for row in results] == [1, 2, 3]
        assert [row['quiz_completed'] for row in results] == [1, 2, 3]
        assert [row['quiz_answers'] for row in results] == [1, 2, 2]
        assert [row['glossary_completed'] for row in results] == [0, 1, 1]
        assert [row['reading_items_updated'] for row in results] == [1, 1, 1]
        assert not any(field in str(results).lower() for field in ('email', 'username', 'telegram', 'user_id'))
        conn.execute("UPDATE quiz_sessions SET started_at=?,finished_at=? WHERE id=2",
                     ('2026-09-28T12:00:00+00:00', '2026-09-28T12:00:00+00:00'))
        conn.execute("UPDATE quiz_answers SET answered_at=? WHERE session_id=2", ('2026-09-28T12:00:00+00:00',))
        cutoff = get_owner_period_stats(conn, '24h', now=now)
        assert (cutoff['quiz_started'], cutoff['quiz_completed'], cutoff['quiz_answers']) == (2, 2, 2)
