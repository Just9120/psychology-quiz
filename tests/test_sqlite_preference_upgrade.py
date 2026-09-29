"""Legacy preference upgrades preserve existing rows and selected values."""
import sqlite3

import pytest

from scripts.init_db import ensure_quiz_sessions_difficulty_mode_column, ensure_users_reading_mode_column


@pytest.mark.parametrize("row_factory", [None, sqlite3.Row])
def test_legacy_upgrade_replay_preserves_user_preferences_and_sessions(row_factory):
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = row_factory
        conn.executescript("""
            CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT);
            CREATE TABLE quiz_sessions(id INTEGER PRIMARY KEY, user_id INTEGER);
            INSERT INTO users VALUES(7,'existing');
            INSERT INTO quiz_sessions VALUES(19,7);
        """)
        ensure_users_reading_mode_column(conn)
        ensure_quiz_sessions_difficulty_mode_column(conn)
        assert tuple(conn.execute("SELECT id,username,reading_mode FROM users").fetchone()) == (7, "existing", "normal")
        assert tuple(conn.execute("SELECT id,user_id,difficulty_mode FROM quiz_sessions").fetchone()) == (19, 7, None)
        conn.execute("UPDATE users SET reading_mode='bionic'")
        conn.execute("UPDATE quiz_sessions SET difficulty_mode='hard'")
        ensure_users_reading_mode_column(conn)
        ensure_quiz_sessions_difficulty_mode_column(conn)
        assert tuple(conn.execute("SELECT id,username,reading_mode FROM users").fetchone()) == (7, "existing", "bionic")
        assert tuple(conn.execute("SELECT id,user_id,difficulty_mode FROM quiz_sessions").fetchone()) == (19, 7, "hard")
