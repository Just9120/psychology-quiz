"""Verified Telegram users keep independent learning state and owner linking."""
from contextlib import closing
from types import SimpleNamespace

from app.classic_quiz_handlers import _handle_classic_text_answer_db
from app.db import get_connection
from tests.test_attempt_content import bank, TOKEN
from tests.test_miniapp_api import _make_init_data
from tests.test_web_auth import EMAIL, post, web
from tests.test_web_literature import linked


def _headers(user_id=42):
    token = _make_init_data(TOKEN, {"id": user_id, "first_name": "Synthetic"})
    return {"Authorization": f"tma {token}"}


def test_learning_routes_accept_verified_telegram_users(web):
    path = "/miniapp/learning/review"
    assert web.client.get(path).status_code == 401
    queue = web.client.get(path, headers=_headers())
    assert queue.status_code == 200 and queue.json()["due_count"] == 0 and queue.json()["items"] == []
    assert web.client.get(path, headers=_headers(777)).status_code == 200
    for action in ("overview", "mastery", "goals", "achievements"):
        response = web.client.get(f"/miniapp/learning/{action}", headers=_headers())
        assert response.status_code == 200 and response.json()["ok"] is True
    assert web.client.get("/miniapp/learning/unknown", headers=_headers()).status_code == 404
    with closing(get_connection(str(web.db))) as conn:
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 2


def test_linked_owner_goals_share_actor_while_other_telegram_user_is_isolated(web):
    with closing(get_connection(str(web.db))) as conn, conn:
        conn.execute("""INSERT INTO web_accounts(email,password_hash,user_id,verified_at,created_at)
            VALUES(?,?,?,?,?)""", (EMAIL, "synthetic-unused", 1, 1, 1))
    response = web.client.post("/miniapp/learning/goal-set", json={"goal_kind": "study", "weekly_target": 2}, headers=_headers())
    assert response.status_code == 200
    assert response.json()["goals"][0]["weekly_target"] == 2
    assert web.client.get("/web/progress/goals").status_code == 401
    with closing(get_connection(str(web.db))) as conn:
        assert conn.execute("SELECT user_id,weekly_target FROM user_learning_goals").fetchone()[:] == (1, 2)
    other = web.client.post("/miniapp/learning/goal-set", json={"goal_kind": "study", "weekly_target": 9}, headers=_headers(777))
    assert other.status_code == 200
    with closing(get_connection(str(web.db))) as conn:
        rows = [tuple(row) for row in conn.execute("SELECT user_id,weekly_target FROM user_learning_goals ORDER BY user_id")]
    assert rows == [(1, 2), (2, 9)]
    assert web.client.post("/miniapp/learning/goal-set", json={"goal_kind": "study", "weekly_target": 0}, headers=_headers()).status_code == 400
    assert web.client.post("/miniapp/learning/goals", json={}, headers=_headers()).status_code == 404


def test_linked_owner_quiz_review_goals_and_literature_are_private_across_clients(web):
    csrf = linked(web)
    owner, other = _headers(), _headers(777)
    published = web.client.get("/miniapp/setup-options", headers=owner).json()["setup_options"]["categories"]
    assert published
    assert web.client.get("/miniapp/setup-options", headers=other).json()["setup_options"]["categories"] == published
    setup = {"quiz_mode": "all", "category_ids": [], "question_count": None, "difficulty": "any"}
    own = web.client.post("/miniapp/setup", json=setup, headers=owner)
    assert own.status_code == 200
    question = own.json()["runner_state"]["current_question"]
    foreign_answer = web.client.post("/miniapp/answer", json={
        "session_id": question["session_id"], "question_id": question["question_id"],
        "selected_option_index": 0,
    }, headers=other)
    assert foreign_answer.json()["submission_status"] == "forbidden"
    assert web.client.get("/miniapp/state", headers=other).json()["runner_state"]["state"] == "setup"

    answer = web.client.post("/miniapp/answer", json={
        "session_id": question["session_id"], "question_id": question["question_id"],
        "selected_option_index": 1,
    }, headers=owner)
    assert answer.status_code == 200 and answer.json()["feedback"]["is_correct"] is False
    own_overview = web.client.get("/web/progress/overview").json()
    assert own_overview["summary"]["answered"] == 1
    assert web.client.get("/miniapp/learning/overview", headers=owner).json() == own_overview
    own_review = web.client.get("/web/progress/review").json()["items"]
    assert len(own_review) == 1 and own_review[0]["question_id"] == question["question_id"]
    assert web.client.get("/miniapp/learning/review", headers=owner).json()["items"] == own_review
    assert web.client.get("/miniapp/learning/review", headers=other).json()["items"] == []
    assert post(web, "progress/errors", csrf=csrf).json()["total"] == 1
    assert web.client.get("/miniapp/learning/overview", headers=other).json()["summary"]["answered"] == 0
    assert web.client.get("/miniapp/learning/mastery", headers=other).json()["questions"]["assessed_count"] == 0
    assert web.client.get("/miniapp/learning/mastery", headers=owner).json() == web.client.get("/web/progress/mastery").json()

    goal = web.client.post("/miniapp/learning/goal-set", json={
        "goal_kind": "study", "weekly_target": 2,
    }, headers=owner)
    assert goal.status_code == 200
    assert web.client.get("/web/progress/goals").json()["goals"][0]["weekly_target"] == 2
    assert web.client.get("/miniapp/learning/goals", headers=other).json()["goals"][0]["weekly_target"] is None
    assert web.client.get("/miniapp/literature/state", headers=owner).json()["literature_state"]
    assert web.client.get("/miniapp/literature/state", headers=other).json()["literature_state"] == []
    # Materialized awards are private too; award eligibility is tested separately.
    with closing(get_connection(str(web.db))) as conn, conn:
        conn.execute("""INSERT INTO user_achievements(user_id,achievement_kind,evidence_key,earned_at)
            VALUES(1,'regularity','synthetic-owner-evidence','2026-09-26T00:00:00Z')""")
    own_awards = web.client.get("/web/progress/achievements").json()["achievements"]
    assert len(own_awards) == 1 and own_awards[0]["evidence_key"] == "synthetic-owner-evidence"
    assert web.client.get("/miniapp/learning/achievements", headers=owner).json()["achievements"] == own_awards
    assert web.client.get("/miniapp/learning/achievements", headers=other).json()["achievements"] == []
    assert web.client.post("/miniapp/learning/goal-set", json={
        "goal_kind": "study", "weekly_target": 9, "user_id": 1,
    }, headers=other).status_code == 200
    assert web.client.get("/web/progress/goals").json()["goals"][0]["weekly_target"] == 2


def test_chat_answer_on_linked_attempt_recovers_in_pwa_and_miniapp_once(web):
    csrf = linked(web)
    started = post(web, "quiz/setup", {
        "quiz_mode": "all", "category_ids": [], "question_count": None, "difficulty": "any",
    }, csrf=csrf)
    assert started.status_code == 200
    question = started.json()["runner_state"]["current_question"]
    owner = SimpleNamespace(id=42, username=None, first_name="Owner", last_name=None)
    foreign = SimpleNamespace(id=777, username=None, first_name="Other", last_name=None)
    settings = SimpleNamespace(db_path=str(web.db))
    args = {"session_id": question["session_id"], "question_id": question["question_id"],
            "selected_option_index": 0}
    assert _handle_classic_text_answer_db(settings, foreign, **args)["status"] == "forbidden"
    saved = _handle_classic_text_answer_db(settings, owner, **args)
    assert saved["status"] == "accepted"
    web_state = web.client.get("/web/quiz/state").json()
    mini_state = web.client.get("/miniapp/state", headers=_headers()).json()
    assert mini_state["runner_state"] == web_state["runner_state"]
    assert mini_state["recent_answer_feedback"] == web_state["recent_answer_feedback"]
    retry = post(web, "quiz/answer", {**args, "selected_option_index": 1}, csrf=csrf)
    assert retry.status_code == 200 and retry.json()["submission_status"] == "duplicate"
    assert retry.json()["feedback"]["selected_option_index"] == 0
    with closing(get_connection(str(web.db))) as conn:
        assert conn.execute("SELECT count(*) FROM quiz_answers WHERE session_id=?",
                            (question["session_id"],)).fetchone()[0] == 1
