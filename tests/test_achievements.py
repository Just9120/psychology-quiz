from contextlib import closing

import json

from app import achievements, curriculum, glossary_service, learning_reset
from app.db import create_or_load_user, get_connection
from app.glossary import GLOSSARY_TOPICS
from app.progress_service import review_glossary_today
from tests.test_attempt_content import OLD, bank
from tests.test_progress import record, reset_payload
from tests.test_web_auth import web, post, register, login


def test_private_achievements_from_completed_editions_and_review_events(bank, monkeypatch):
    with closing(get_connection(str(bank))) as conn, conn:
        first = record(conn, choices=(1,))
        digest = conn.execute("SELECT content_sha256 FROM quiz_session_questions WHERE session_id=?", (first,)).fetchone()
        catalog = {"disciplines": {"fixture": {"title": OLD["category"]}},
                   "topics": {"t_0123456789ab": {"title": "Fixture", "discipline_id": "fixture"}},
                   "editions": {digest[0]: {"topic_id": "t_0123456789ab"}}}
        monkeypatch.setattr(curriculum, "load_catalog", lambda: catalog)
        conn.execute("UPDATE quiz_sessions SET finished_at='2026-09-07 12:00:00' WHERE id=?", (first,))
        conn.execute("UPDATE quiz_answers SET answered_at='2026-09-07 12:00:00' WHERE session_id=?", (first,))
        second = record(conn, choices=(0,))
        conn.execute("UPDATE quiz_sessions SET finished_at='2026-09-14 12:00:00' WHERE id=?", (second,))
        conn.execute("UPDATE quiz_answers SET answered_at='2026-09-14 12:00:00' WHERE session_id=?", (second,))
        answer_id = conn.execute("SELECT id FROM quiz_answers WHERE session_id=?", (second,)).fetchone()[0]
        conn.execute("""INSERT INTO user_review_events(user_id,answer_kind,answer_key,answered_at)
            VALUES(1,'quiz',?,'2026-09-14 12:00:00')""", (str(answer_id),))
        other = create_or_load_user(conn, 991, None, None, None)["id"]
        result = achievements.refresh(conn, 1)
        assert {item["kind"] for item in result["achievements"]} == {
            "new_topic", "regularity", "corrected_error"}
        assert achievements.refresh(conn, 1) == result
        assert achievements.refresh(conn, other)["achievements"] == []
        after_gap = record(conn, choices=(0,))
        conn.execute("UPDATE quiz_sessions SET finished_at='2026-10-19 12:00:00' WHERE id=?", (after_gap,))
        assert achievements.refresh(conn, 1) == result

        preview = learning_reset.preview(conn, 1, {"scope": "all"})
        learning_reset.confirm(conn, 1, reset_payload(preview))
        assert achievements.refresh(conn, 1)["achievements"] == []


def test_corrected_glossary_error_requires_answer_from_due_queue(bank):
    topic = GLOSSARY_TOPICS[0][0]
    with closing(get_connection(str(bank))) as conn, conn:
        first = glossary_service.start(conn, 1, topic, 5)
        sid = first["session_id"]
        snapshot = json.loads(conn.execute("SELECT snapshot FROM glossary_sessions WHERE id=?", (sid,)).fetchone()[0])
        wrong = (snapshot["questions"][0]["correct_option_index"] + 1) % len(snapshot["questions"][0]["options"])
        glossary_service.answer(conn, 1, sid, wrong, 1)
        state = json.loads(conn.execute("SELECT state FROM glossary_sessions WHERE id=?", (sid,)).fetchone()[0])
        state["answers"]["1"]["answered_at"] = "2026-09-01T10:00:00Z"
        conn.execute("UPDATE glossary_sessions SET state=? WHERE id=?", (json.dumps(state), sid))
        assert achievements.refresh(conn, 1)["achievements"] == []
        review = review_glossary_today(conn, 1, {"topic_id": topic, "question_count": 5,
            "expected_session_id": sid, "replace_active": True})
        review_sid = review["glossary_state"]["session_id"]
        reviewed = json.loads(conn.execute("SELECT snapshot FROM glossary_sessions WHERE id=?", (review_sid,)).fetchone()[0])
        glossary_service.answer(conn, 1, review_sid, reviewed["questions"][0]["correct_option_index"], 1)
        assert [item["kind"] for item in achievements.refresh(conn, 1)["achievements"]] == ["corrected_error"]


def test_achievements_api_requires_personal_identity(web):
    assert web.client.get("/web/progress/achievements").status_code == 401
    register(web)
    csrf = login(web)
    assert web.client.get("/web/progress/achievements").status_code == 409
    assert post(web, "identity/new", csrf=csrf).status_code == 200
    response = web.client.get("/web/progress/achievements")
    assert response.status_code == 200 and response.json() == {"ok": True, "achievements": []}
    assert response.headers["cache-control"] == "no-store"
    assert web.client.get("/web/progress/achievements?user_id=1").status_code == 400
