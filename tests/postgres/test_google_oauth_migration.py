from contextlib import closing
from app.db import get_connection
from app.postgres_schema import initialize_schema, upgrade_schema, verify_schema
from app.postgres_recovery import manifest, verify_user_state


def test_oauth_upgrade_preserves_v8_accounts_and_sessions(pg_target):
    with closing(get_connection(pg_target)) as conn, conn:
        initialize_schema(conn, version='postgres-v8')
        conn.execute("INSERT INTO web_accounts VALUES(1,'owner@example.test','synthetic-hash',NULL,1,1,1)")
        conn.execute("INSERT INTO web_sessions VALUES('synthetic-digest',1,1,100,1)")
        before = manifest(conn)
        upgrade_schema(conn)
        assert verify_schema(conn) == 'postgres-v9'
        verify_user_state(before, manifest(conn))
        conn.execute("INSERT INTO web_google_identities VALUES('synthetic-subject',1,1)")
        conn.execute("""INSERT INTO web_oauth_challenges VALUES
            ('state','browser','nonce','verifier','link',1,'synthetic-digest',100)""")
        upgraded = manifest(conn)
        upgrade_schema(conn)
        assert manifest(conn) == upgraded
        conn.execute("DELETE FROM web_sessions WHERE digest='synthetic-digest'")
        assert conn.execute('SELECT COUNT(*) FROM web_oauth_challenges').fetchone()[0] == 0
        assert conn.execute('SELECT COUNT(*) FROM web_google_identities').fetchone()[0] == 1
