import sqlite3

from scripts.privacy_db_inventory import inventory, sqlite_schema


def test_inventory_reads_schema_only_and_flags_unclassified_tables():
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY, telegram_user_id INTEGER,
                                username TEXT, first_name TEXT, last_name TEXT);
            CREATE TABLE quiz_sessions (id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id));
            CREATE TABLE unexpected_personal_notes (id INTEGER PRIMARY KEY, note TEXT);
            INSERT INTO users VALUES (1, 123456, 'private-name', 'private', 'person');
        """)
        # A schema inventory must not inspect any user's row values.
        def deny_user_rows(action, arg1, _arg2, _db, _trigger):
            if action == sqlite3.SQLITE_READ and arg1 == "users":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        conn.set_authorizer(deny_user_rows)
        columns, keys = sqlite_schema(conn)
        report = inventory(columns, keys)
        assert report["personal_tables"]["users"]["present"] is True
        assert "username" in report["personal_tables"]["users"]["columns"]
        assert report["personal_tables"]["web_accounts"]["present"] is False
        assert report["unclassified_tables"] == ["unexpected_personal_notes"]
        assert {"table": "quiz_sessions", "column": "user_id",
                "references": "users", "on_delete": "NO ACTION"} in report["foreign_keys"]
        assert "private-name" not in str(report)
    finally:
        conn.close()
