from contextlib import closing
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.attempt_content import ensure_attempt_snapshots, get_attempt_content
from app.identity_schema import migrate_identity_schema
from app.glossary_schema import migrate_glossary_schema
from app.learning_schema import migrate_learning_schema
from app.classic_quiz_handlers import _handle_classic_text_answer_db
from app.db import (
    create_or_load_user, finalize_quiz_session, get_active_categories, get_connection,
    get_current_unanswered_question, get_question_options, save_quiz_answer,
    select_random_approved_question_ids_by_category,
    select_random_approved_question_ids_by_categories,
    select_random_approved_question_ids_across_active_categories,
    start_quiz_session, store_session_questions, upsert_approved_questions,
)
from app.miniapp_fastapi import create_app
from app.miniapp_runner import build_miniapp_runner_state
from scripts.deployment_db import backup_and_rehearse, check_business, verify_preserved, user_state
from scripts import init_db
from tests.test_miniapp_api import _make_init_data


OLD = {"id": "stable-question", "category": "Original category", "source_ref": "source-v1",
       "difficulty": "easy", "status": "approved", "question": "Original question?",
       "explanation": "Original explanation", "options": ["Original correct", "Old distractor", "Third", "Fourth"],
       "correct_option_index": 0}
OTHER = {**OLD, "id": "other", "category": "Other category"}
NEW = {**OLD, "question": "Edited question?", "explanation": "Edited explanation",
       "source_ref": "source-v2", "options": ["New wrong", "New correct"], "correct_option_index": 1}
TOKEN = "123:synthetic-history"


def make_attempt(conn, *, questions=(1, 2)):
    sid = start_quiz_session(conn, 1, 1)
    store_session_questions(conn, sid, list(questions))
    return sid


@pytest.fixture
def bank(tmp_path):
    path = tmp_path / "quiz.sqlite3"
    with closing(get_connection(str(path))) as conn, conn:
        conn.executescript(Path("sql/schema.sql").read_text(encoding="utf-8"))
        migrate_identity_schema(conn)
        migrate_glossary_schema(conn)
        migrate_learning_schema(conn)
        upsert_approved_questions(conn, [OLD, OTHER], authoritative=True)
        create_or_load_user(conn, 42, None, "Original user", None)
        conn.execute("INSERT INTO user_literature_progress (user_id,literature_id,reading_status,updated_at,private_note) VALUES (1,'lit','read','today','Private note')")
    return path


@pytest.mark.parametrize("change", ["edit", "draft", "review", "retired", "removed"])
def test_content_publication_preserves_attempts_and_excludes_inactive_from_all_selectors(bank, change):
    with closing(get_connection(str(bank))) as conn, conn:
        completed = make_attempt(conn, questions=(1,))
        save_quiz_answer(conn, completed, 1, 0)
        finalize_quiz_session(conn, completed)
        active = make_attempt(conn)
        original = get_attempt_content(conn, active, 1)
        before = user_state(conn)
        published = [OTHER] if change == "removed" else [{**NEW, "status": "approved" if change == "edit" else change}, OTHER]
        upsert_approved_questions(conn, published, authoritative=True)
        upsert_approved_questions(conn, published, authoritative=True)
        assert user_state(conn) == before
        assert get_attempt_content(conn, active, 1) == original
        assert get_attempt_content(conn, completed, 1) == original
        assert get_current_unanswered_question(conn, active)["question_text"] == OLD["question"]
        options = get_question_options(conn, 1, session_id=active)
        assert [opt["option_text"] for opt in options] == OLD["options"]
        assert save_quiz_answer(conn, active, 1, 0)["is_correct"] == 1
        assert save_quiz_answer(conn, active, 1, 0)["already_answered"] == 1
        assert conn.execute("SELECT count(*) FROM quiz_answers WHERE session_id=?", (active,)).fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        category = conn.execute("SELECT category_id FROM questions WHERE id=1").fetchone()[0]
        for ids in (select_random_approved_question_ids_by_category(conn, category, None),
                    select_random_approved_question_ids_by_categories(conn, [category], None),
                    select_random_approved_question_ids_across_active_categories(conn, None)):
            assert (1 in ids) == (change == "edit")
        assert (category in [row["id"] for row in get_active_categories(conn)]) == (change == "edit")
        if change == "edit":
            new_attempt = make_attempt(conn)
            state = build_miniapp_runner_state(conn, actor_user_id=1, session_id=new_attempt)
            assert state["current_question"]["question_text"] == NEW["question"]
            assert get_attempt_content(conn, new_attempt, 1)["content_sha256"] != original["content_sha256"]
            assert save_quiz_answer(conn, new_attempt, 1, 1)["is_correct"] == 1
        else:
            assert conn.execute("SELECT count(*) FROM questions WHERE id=1").fetchone()[0] == 1
            with pytest.raises(ValueError, match="Only approved"):
                store_session_questions(conn, start_quiz_session(conn, 1, category), [1])


def test_api_current_question_answer_and_recent_feedback_use_same_edition(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = make_attempt(conn)
        upsert_approved_questions(conn, [NEW])
    client = TestClient(create_app(db_path=str(bank), bot_token=TOKEN))
    headers = {"Authorization": "tma " + _make_init_data(TOKEN, {"id": 42, "first_name": "Original user"})}
    state = client.get("/miniapp/state", headers=headers).json()["runner_state"]
    assert state["current_question"]["question_text"] == OLD["question"]
    assert state["current_question"]["options"][0]["option_text"] == OLD["options"][0]
    assert "is_correct" not in state["current_question"]["options"][0]
    payload = {"session_id": sid, "question_id": 1, "selected_option_index": 0}
    forbidden = client.post("/miniapp/answer", json=payload, headers={"Authorization": "tma " + _make_init_data(TOKEN, {"id": 99})})
    assert forbidden.json()["submission_status"] == "forbidden"
    answer = client.post("/miniapp/answer", json=payload, headers=headers)
    assert answer.status_code == 200
    feedback = answer.json()["feedback"]
    assert feedback["is_correct"] is True
    assert feedback["correct_option_index"] == 0
    assert feedback["selected_option_text"] == feedback["correct_option_text"] == OLD["options"][0]
    assert feedback["explanation"] == OLD["explanation"]
    assert feedback["snapshot_provenance"] == "captured"
    with closing(get_connection(str(bank))) as conn, conn:
        upsert_approved_questions(conn, [OTHER], authoritative=True)
    recent = client.get("/miniapp/state", headers=headers).json()["recent_answer_feedback"]
    assert {k: v for k, v in recent.items() if k != "question_id"} == feedback


def test_classic_answer_uses_original_content_after_option_reorder(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = make_attempt(conn)
        upsert_approved_questions(conn, [NEW])
    result = _handle_classic_text_answer_db(
        SimpleNamespace(db_path=str(bank)),
        SimpleNamespace(id=42, username=None, first_name="Original user", last_name=None),
        session_id=sid, question_id=1, selected_option_index=0,
    )
    assert result["status"] == "accepted" and result["is_correct"] is True
    assert result["correct_option_text"] == result["selected_option_text"] == OLD["options"][0]
    assert result["explanation"] == OLD["explanation"]


def test_partial_sync_does_not_retire_unspecified_ids_and_duplicate_input_is_atomic(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        upsert_approved_questions(conn, [{**OLD, "status": "draft"}])
        assert conn.execute("SELECT status FROM questions WHERE external_id='other'").fetchone()[0] == "approved"
        before = list(conn.iterdump())
        with pytest.raises(ValueError, match="unique"):
            upsert_approved_questions(conn, [OLD, NEW], authoritative=True)
        assert list(conn.iterdump()) == before


def test_snapshot_cannot_be_replaced_or_read_as_current_live_content(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = make_attempt(conn)
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE quiz_session_questions SET content_snapshot='{}' WHERE session_id=?", (sid,))
        assert get_attempt_content(conn, sid, 999) is None
        assert get_question_options(conn, 999, session_id=sid) == []
        conn.execute("DROP TRIGGER immutable_attempt_content")  # Synthetic corruption fixture only.
        conn.execute("UPDATE quiz_session_questions SET content_snapshot='{}' WHERE session_id=?", (sid,))
        with pytest.raises(ValueError, match="corrupt"):
            check_business(conn)


def test_legacy_migration_is_idempotent_preserves_users_answers_and_marks_uncertain_provenance(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite3"
    schema = Path("sql/schema.sql").read_text(encoding="utf-8")
    for name in ("content_snapshot", "content_sha256", "snapshot_provenance"):
        schema = schema.replace(f"    {name} TEXT,\n", "")
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(schema)
        conn.execute("INSERT INTO users (telegram_user_id) VALUES (42)")
        conn.execute("INSERT INTO categories (slug,name) VALUES ('old','Old')")
        conn.execute("INSERT INTO questions (external_id,category_id,question_text,explanation) VALUES ('stable-question',1,'Legacy available','Legacy explanation')")
        conn.execute("INSERT INTO question_options (question_id,option_index,option_text,is_correct) VALUES (1,0,'Available',1),(1,1,'Other',0)")
        conn.execute("INSERT INTO quiz_sessions (user_id,score,status,total_questions) VALUES (1,0,'finished',1)")
        conn.execute("INSERT INTO quiz_session_questions (session_id,question_id,order_index) VALUES (1,1,1)")
        # The saved assessment may disagree with today's edition; never recalculate it.
        conn.execute("INSERT INTO quiz_answers (session_id,question_id,selected_option_index,is_correct) VALUES (1,1,0,0)")
        conn.execute("INSERT INTO user_literature_progress (user_id,literature_id,reading_status,updated_at,private_note) VALUES (1,'lit','read','today','Keep private note')")
    backup = backup_and_rehearse(path, tmp_path / "backups")
    monkeypatch.setenv("DB_PATH", str(path))
    assert init_db.main() == 0
    verify_preserved(path, backup)
    with closing(get_connection(str(path))) as conn:
        first_dump = list(conn.iterdump())
        snapshot = get_attempt_content(conn, 1, 1)
        assert snapshot["snapshot_provenance"] == "legacy_backfill_current"
        assert snapshot["question_text"] == "Legacy available"
    assert init_db.main() == 0
    with closing(get_connection(str(path))) as conn, conn:
        assert list(conn.iterdump()) == first_dump
        upsert_approved_questions(conn, [NEW], authoritative=True)
        assert get_attempt_content(conn, 1, 1) == snapshot
        assert conn.execute("SELECT is_correct FROM quiz_answers").fetchone()[0] == 0
        assert conn.execute("SELECT score FROM quiz_sessions").fetchone()[0] == 0
        check_business(conn)
    verify_preserved(path, backup)
