from app.mastery import evaluate
from contextlib import closing

from app.db import get_connection, create_or_load_user, start_quiz_session, store_session_questions, upsert_approved_questions
from app.quiz_service import answer_quiz
from app.mastery import quiz_states
from tests.test_attempt_content import bank, NEW


def test_mastery_requires_spaced_confirmed_answers():
    answers = [("2026-09-01 10:00:00", True),
               ("2026-09-02 10:00:00", True),
               ("2026-09-08 10:00:00", True)]
    assert evaluate(answers) == {"status": "mastered", "correct_streak": 3}
    assert evaluate(answers[:2])["status"] == "insufficient_data"
    assert evaluate([(answers[0][0], True), ("2026-09-01 23:59:00", True), answers[2]])["status"] == "insufficient_data"
    assert evaluate([(answers[0][0], True), answers[1], ("2026-09-04 10:00:00", True)])["status"] == "insufficient_data"
    assert evaluate(answers, edition_confirmed=False)["status"] == "insufficient_data"


def test_error_resets_mastery_and_later_spaced_triple_recovers():
    answers = [("2026-09-01T10:00:00Z", True),
               ("2026-09-02T10:00:00Z", True),
               ("2026-09-08T10:00:00Z", True)]
    assert evaluate(answers + [("2026-09-09T10:00:00Z", True)])["status"] == "mastered"
    assert evaluate(answers + [("2026-09-10T10:00:00Z", False)])["status"] == "insufficient_data"
    later = [("2026-09-11T10:00:00Z", True), ("2026-09-12T10:00:00Z", True),
             ("2026-09-18T10:00:00Z", True)]
    assert evaluate(answers + [("2026-09-10T10:00:00Z", False)] + later)["status"] == "mastered"


def test_extra_close_answers_do_not_prevent_a_later_valid_triple():
    answers = [("2026-09-01T10:00:00Z", True),
               ("2026-09-01T11:00:00Z", True),
               ("2026-09-02T10:00:00Z", True),
               ("2026-09-08T10:00:00Z", True)]
    assert evaluate(answers)["status"] == "mastered"


def test_quiz_mastery_is_actor_and_edition_scoped(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        actor = 1
        other = create_or_load_user(conn, 991, None, None, None)["id"]
        for date in ("2026-09-01", "2026-09-02", "2026-09-08"):
            sid = start_quiz_session(conn, actor, None)
            store_session_questions(conn, sid, [1])
            answer_quiz(conn, actor_user_id=actor, session_id=sid, question_id=1, selected_option_index=0)
            conn.execute("UPDATE quiz_answers SET answered_at=? WHERE session_id=?", (date + " 10:00:00", sid))
        assert quiz_states(conn, actor)["items"][0]["status"] == "mastered"
        assert quiz_states(conn, other)["items"] == []
        upsert_approved_questions(conn, [NEW])
        assert quiz_states(conn, actor)["items"][0]["status"] == "insufficient_data"
