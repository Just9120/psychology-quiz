"""Telegram learning routes use the linked owner actor while student launch is off."""
from contextlib import closing

from app.db import get_connection
from tests.test_attempt_content import bank, TOKEN
from tests.test_miniapp_api import _make_init_data
from tests.test_web_auth import EMAIL, web


def _headers(user_id=42):
    token = _make_init_data(TOKEN, {"id": user_id, "first_name": "Synthetic"})
    return {"Authorization": f"tma {token}"}


def test_learning_routes_require_verified_link_and_keep_unknown_student_out(web):
    path = "/miniapp/learning/review"
    assert web.client.get(path).status_code == 401
    assert web.client.get(path, headers=_headers()).status_code == 403
    assert web.client.get(path, headers=_headers(777)).status_code == 403
    with closing(get_connection(str(web.db))) as conn:
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    with closing(get_connection(str(web.db))) as conn, conn:
        conn.execute("""INSERT INTO web_accounts(email,password_hash,user_id,verified_at,created_at)
            VALUES(?,?,?,?,?)""", (EMAIL, "synthetic-unused", 1, 1, 1))
    queue = web.client.get(path, headers=_headers())
    assert queue.status_code == 200 and queue.json()["due_count"] == 0 and queue.json()["items"] == []
    assert web.client.get(path, headers=_headers(777)).status_code == 403
    for action in ("overview", "mastery", "goals", "achievements"):
        response = web.client.get(f"/miniapp/learning/{action}", headers=_headers())
        assert response.status_code == 200 and response.json()["ok"] is True
    assert web.client.get("/miniapp/learning/unknown", headers=_headers()).status_code == 404


def test_linked_owner_goals_write_same_actor_as_web_without_exposing_student(web):
    with closing(get_connection(str(web.db))) as conn, conn:
        conn.execute("""INSERT INTO web_accounts(email,password_hash,user_id,verified_at,created_at)
            VALUES(?,?,?,?,?)""", (EMAIL, "synthetic-unused", 1, 1, 1))
    response = web.client.post("/miniapp/learning/goal-set", json={"goal_kind": "study", "weekly_target": 2}, headers=_headers())
    assert response.status_code == 200
    assert response.json()["goals"][0]["weekly_target"] == 2
    assert web.client.get("/web/progress/goals").status_code == 401
    with closing(get_connection(str(web.db))) as conn:
        assert conn.execute("SELECT user_id,weekly_target FROM user_learning_goals").fetchone()[:] == (1, 2)
    assert web.client.post("/miniapp/learning/goal-set", json={"goal_kind": "study", "weekly_target": 9}, headers=_headers(777)).status_code == 403
    assert web.client.post("/miniapp/learning/goal-set", json={"goal_kind": "study", "weekly_target": 0}, headers=_headers()).status_code == 400
    assert web.client.post("/miniapp/learning/goals", json={}, headers=_headers()).status_code == 404
