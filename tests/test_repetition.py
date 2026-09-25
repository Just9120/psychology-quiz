from contextlib import closing
from datetime import date
import json

from app.db import create_or_load_user, get_connection, start_quiz_session, store_session_questions, upsert_approved_questions
from app.quiz_service import answer_quiz
from app.repetition import adaptive_questions, queue, schedule
from app.miniapp_api import build_setup_response
from app.progress_service import review_today, review_glossary_today, ProgressError
from app import glossary_service
from app import learning_reset
from app.glossary import GLOSSARY_TOPICS
import pytest
from tests.test_attempt_content import bank, NEW, OLD, TOKEN
from tests.test_miniapp_api import _make_init_data
from tests.test_web_auth import web, post, register, login


EDITION = "a" * 64


def test_review_intervals_error_reset_and_changed_edition():
    today = date(2026, 9, 20)
    event = lambda day, correct: (f"2026-09-{day:02d}T10:00:00Z", correct, EDITION, "captured")
    assert schedule([event(1, False)], EDITION, today=date(2026, 9, 2))["due_on"] == "2026-09-02"
    assert schedule([event(1, True)], EDITION, today=today)["due_on"] == "2026-09-04"
    assert schedule([event(1, True), event(4, True)], EDITION, today=today)["due_on"] == "2026-09-11"
    assert schedule([event(1, True), event(4, True), event(11, True)], EDITION, today=today)["due_on"] == "2026-09-25"
    assert schedule([event(1, True), event(4, True), event(11, False)], EDITION, today=today)["due_on"] == "2026-09-12"
    assert schedule([event(1, True)], "b" * 64, today=today)["reason"] == "new_edition"
    assert schedule([(event(1, True)[0], True, EDITION, "legacy_backfill_current")], EDITION, today=today)["is_due"]


def test_due_queue_is_personal_and_resets_after_question_edit(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        other = create_or_load_user(conn, 991, None, None, None)["id"]
        sid = start_quiz_session(conn, 1, None)
        store_session_questions(conn, sid, [1])
        answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=1, selected_option_index=0)
        conn.execute("UPDATE quiz_answers SET answered_at='2026-09-01T10:00:00Z' WHERE session_id=?", (sid,))
        waiting = queue(conn, 1, today=date(2026, 9, 2))
        assert waiting["due_count"] == 0
        assert waiting["items"][0]["due_on"] == "2026-09-04"
        assert queue(conn, other, today=date(2026, 9, 2))["items"] == []
        upsert_approved_questions(conn, [NEW])
        revised = queue(conn, 1, today=date(2026, 9, 2))
        assert revised["due_count"] == 1
        assert revised["items"][0]["reason"] == "new_edition"


def test_adaptive_keeps_random_candidate_scope_and_reserves_new_material(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = start_quiz_session(conn, 1, None)
        store_session_questions(conn, sid, [1])
        answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=1, selected_option_index=1)
        conn.execute("UPDATE quiz_answers SET answered_at='2026-09-01T10:00:00Z' WHERE session_id=?", (sid,))
        assert adaptive_questions(conn, 1, [2, 1], 1, today=date(2026, 9, 3)) == [1]
        assert adaptive_questions(conn, 1, [2, 1], 2, today=date(2026, 9, 3)) == [1, 2]
        assert adaptive_questions(conn, 1, [2], 5, today=date(2026, 9, 3)) == [2]
        assert adaptive_questions(conn, None, [2, 1], 1, today=date(2026, 9, 3)) == [2]


def test_adaptive_setup_uses_verified_actor_in_web_and_telegram(web):
    payload = {"quiz_mode": "adaptive", "question_count": 5, "difficulty": "any", "category_ids": []}
    register(web)
    csrf = login(web)
    assert post(web, "identity/new", csrf=csrf).status_code == 200
    own = post(web, "quiz/setup", payload, csrf=csrf)
    assert own.status_code == 200 and own.json()["runner_state"]["state"] == "in_progress"
    signed = _make_init_data(TOKEN, {"id": 42, "first_name": "Original user"})
    status, _, body = build_setup_response(str(web.db), TOKEN, signed, json.dumps(payload).encode())
    assert status == 200 and json.loads(body)["runner_state"]["state"] == "in_progress"
    with closing(get_connection(str(web.db))) as conn:
        owners = [row[0] for row in conn.execute("SELECT DISTINCT user_id FROM quiz_sessions WHERE status='in_progress'")]
        assert len(owners) == 2


def test_review_attempt_counts_only_accepted_queue_answers_once(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = start_quiz_session(conn, 1, None)
        store_session_questions(conn, sid, [1, 2])
        answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=1, selected_option_index=1)
        conn.execute("UPDATE quiz_answers SET answered_at='2026-09-01T10:00:00Z' WHERE session_id=?", (sid,))
        with pytest.raises(ProgressError, match="active_attempt"):
            review_today(conn, 1, {"expected_session_id": sid, "replace_active": False})
        review = review_today(conn, 1, {"expected_session_id": sid, "replace_active": True})
        review_sid = review["runner_state"]["session"]["session_id"]
        assert review["runner_state"]["current_question"]["question_id"] == 1
        with pytest.raises(ProgressError, match="practice_changed"):
            review_today(conn, 1, {"expected_session_id": sid, "replace_active": True})
        assert answer_quiz(conn, actor_user_id=1, session_id=review_sid, question_id=1,
                           selected_option_index=0)["submission_status"] == "accepted"
        assert answer_quiz(conn, actor_user_id=1, session_id=review_sid, question_id=1,
                           selected_option_index=0)["submission_status"] == "duplicate"
        assert conn.execute("SELECT count(*) FROM user_review_events WHERE user_id=1").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM user_review_events WHERE user_id=2").fetchone()[0] == 0
        preview = learning_reset.preview(conn, 1, {"scope": "all"})
        learning_reset.confirm(conn, 1, {"scope": "all", "confirm": True,
                                        "expected_revision": preview["revision"]})
        assert conn.execute("SELECT count(*) FROM user_review_events WHERE user_id=1").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM user_review_sessions WHERE user_id=1").fetchone()[0] == 0


def test_glossary_due_review_counts_one_answer_and_keeps_other_actors_private(bank):
    topic = GLOSSARY_TOPICS[0][0]
    with closing(get_connection(str(bank))) as conn, conn:
        first = glossary_service.start(conn, 1, topic, 5)
        first_sid = first["session_id"]
        snapshot = json.loads(conn.execute("SELECT snapshot FROM glossary_sessions WHERE id=?", (first_sid,)).fetchone()[0])
        correct = snapshot["questions"][0]["correct_option_index"]
        glossary_service.answer(conn, 1, first_sid, correct, 1)
        state = json.loads(conn.execute("SELECT state FROM glossary_sessions WHERE id=?", (first_sid,)).fetchone()[0])
        state["answers"]["1"]["answered_at"] = "2026-09-01T10:00:00Z"
        conn.execute("UPDATE glossary_sessions SET state=? WHERE id=?", (json.dumps(state), first_sid))
        due = [item for item in queue(conn, 1, today=date(2026, 9, 25))["items"] if item["kind"] == "glossary"]
        assert len(due) == 1 and due[0]["is_due"]
        assert not [item for item in queue(conn, 2, today=date(2026, 9, 25))["items"] if item["kind"] == "glossary"]
        review = review_glossary_today(conn, 1, {"topic_id": topic, "question_count": 5,
            "expected_session_id": first_sid, "replace_active": True})
        sid = review["glossary_state"]["session_id"]
        selected = json.loads(conn.execute("SELECT snapshot FROM glossary_sessions WHERE id=?", (sid,)).fetchone()[0])
        choice = selected["questions"][0]["correct_option_index"]
        glossary_service.answer(conn, 1, sid, choice, 1)
        glossary_service.answer(conn, 1, sid, choice, 1)
        assert conn.execute("SELECT count(*) FROM user_review_events WHERE user_id=1 AND answer_kind='glossary'").fetchone()[0] == 1


def test_topic_reset_removes_only_review_events_for_deleted_answers(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = start_quiz_session(conn, 1, None)
        store_session_questions(conn, sid, [1, 2])
        for question_id, choice in ((1, 0), (2, 0)):
            answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=question_id,
                        selected_option_index=choice)
        rows = conn.execute("SELECT id,question_id,answered_at FROM quiz_answers WHERE session_id=?", (sid,)).fetchall()
        conn.execute("INSERT INTO user_review_sessions VALUES(1,'quiz',?,'2026-09-25')", (str(sid),))
        for row in rows:
            conn.execute("INSERT INTO user_review_events VALUES(1,'quiz',?,?)",
                         (str(row["id"]), row["answered_at"]))
        preview = learning_reset.preview(conn, 1, {"scope": "topic", "topic": OLD["category"]})
        learning_reset.confirm(conn, 1, {"scope": "topic", "topic": OLD["category"],
                                        "confirm": True, "expected_revision": preview["revision"]})
        assert [row[0] for row in conn.execute("SELECT answer_key FROM user_review_events WHERE user_id=1")] == [
            str(next(row["id"] for row in rows if row["question_id"] == 2))]
        assert conn.execute("SELECT count(*) FROM user_review_sessions WHERE user_id=1").fetchone()[0] == 0
