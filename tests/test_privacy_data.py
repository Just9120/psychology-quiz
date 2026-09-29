"""Deletion cannot cross actor boundaries, touch the bank or replay a token."""
import sqlite3

import pytest

from app.privacy_data import PrivacyError, confirm_learning_data_deletion, prepare_learning_data_deletion
from app.privacy_schema import migrate_privacy_schema


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
        CREATE TABLE users(id INTEGER PRIMARY KEY,telegram_user_id INTEGER UNIQUE);
        CREATE TABLE web_accounts(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id));
        CREATE TABLE schema_migrations(version TEXT PRIMARY KEY);
        CREATE TABLE questions(id INTEGER PRIMARY KEY);
        CREATE TABLE quiz_sessions(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id));
        CREATE TABLE quiz_answers(id INTEGER PRIMARY KEY,session_id INTEGER REFERENCES quiz_sessions(id) ON DELETE CASCADE);
        CREATE TABLE glossary_sessions(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id));
        CREATE TABLE user_literature_progress(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id));
        CREATE TABLE user_learning_goals(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id));
        CREATE TABLE user_achievements(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id));
        CREATE TABLE user_review_events(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id));
        CREATE TABLE user_review_sessions(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id));
        INSERT INTO users VALUES(1,101),(2,202);
        INSERT INTO questions VALUES(9);
        INSERT INTO quiz_sessions VALUES(11,1),(22,2);
        INSERT INTO quiz_answers VALUES(11,11),(22,22);
        INSERT INTO glossary_sessions VALUES(11,1),(22,2);
        INSERT INTO user_literature_progress VALUES(11,1),(22,2);
        INSERT INTO user_learning_goals VALUES(11,1),(22,2);
        INSERT INTO user_achievements VALUES(11,1),(22,2);
        INSERT INTO user_review_events VALUES(11,1),(22,2);
        INSERT INTO user_review_sessions VALUES(11,1),(22,2);
    """)
    migrate_privacy_schema(db)
    db.commit()
    try:
        yield db
    finally:
        db.close()


def test_deletion_is_scoped_and_one_use(conn):
    prepared = prepare_learning_data_deletion(conn, 1)
    token = prepared["confirmation_token"]
    with pytest.raises(PrivacyError, match="invalid_confirmation"):
        confirm_learning_data_deletion(conn, 1, "x" * 40)
    assert conn.execute("SELECT count(*) FROM quiz_sessions WHERE user_id=1").fetchone()[0] == 1
    conn.commit()
    result = confirm_learning_data_deletion(conn, 1, token)
    assert result["telegram_access_retained"] is True
    for table in ("quiz_sessions", "glossary_sessions", "user_literature_progress",
                  "user_learning_goals", "user_achievements", "user_review_events", "user_review_sessions"):
        assert conn.execute(f"SELECT count(*) FROM {table} WHERE user_id=1").fetchone()[0] == 0
        assert conn.execute(f"SELECT count(*) FROM {table} WHERE user_id=2").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM quiz_answers").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM questions").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 2
    with pytest.raises(PrivacyError, match="invalid_confirmation"):
        confirm_learning_data_deletion(conn, 1, token)


def test_linked_owner_and_expired_challenge_never_delete(conn):
    conn.execute("INSERT INTO web_accounts VALUES(1,1)")
    with pytest.raises(PrivacyError, match="linked_owner_requires_separate_flow"):
        prepare_learning_data_deletion(conn, 1)
    assert conn.execute("SELECT count(*) FROM quiz_sessions WHERE user_id=1").fetchone()[0] == 1
    prepared = prepare_learning_data_deletion(conn, 2)
    conn.execute("UPDATE user_data_deletion_challenges SET expires_at='2000-01-01T00:00:00+00:00' WHERE user_id=2")
    with pytest.raises(PrivacyError, match="confirmation_expired"):
        confirm_learning_data_deletion(conn, 2, prepared["confirmation_token"])
    assert conn.execute("SELECT count(*) FROM quiz_sessions WHERE user_id=2").fetchone()[0] == 1


def test_link_during_confirmation_blocks_deletion(conn):
    prepared = prepare_learning_data_deletion(conn, 1)
    conn.execute("INSERT INTO web_accounts VALUES(1,1)")
    with pytest.raises(PrivacyError, match="linked_owner_requires_separate_flow"):
        confirm_learning_data_deletion(conn, 1, prepared["confirmation_token"])
    assert conn.execute("SELECT count(*) FROM quiz_sessions WHERE user_id=1").fetchone()[0] == 1
