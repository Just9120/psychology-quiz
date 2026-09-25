"""Verified Telegram users keep independent learning state and owner linking."""
from contextlib import closing

from app.db import get_connection
from tests.test_attempt_content import bank, TOKEN
from tests.test_miniapp_api import _make_init_data
from tests.test_web_auth import EMAIL, web


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
