from contextlib import closing
from datetime import date
import json

from app.db import create_or_load_user, get_connection, start_quiz_session, store_session_questions, upsert_approved_questions
from app.quiz_service import answer_quiz
from app.repetition import adaptive_questions, queue, schedule
from app.miniapp_api import build_setup_response
from tests.test_attempt_content import bank, NEW, TOKEN
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
