"""Anonymous demo is fixed, reviewed and never writes learner state."""
from contextlib import closing

from app import demo
from app.db import get_connection
from tests.test_attempt_content import bank
from tests.test_web_auth import ORIGIN, post, web


def test_three_reviewed_demo_items_need_no_account_and_save_no_history(web):
    with closing(get_connection(str(web.db))) as conn:
        before = {name: conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                  for name in ("quiz_sessions", "quiz_answers", "glossary_sessions", "user_review_events", "web_accounts")}
    response = web.client.get("/web/demo/items")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    items = response.json()["items"]
    assert [(item["id"], item["kind"]) for item in items] == [
        ("theory", "theory"), ("term", "glossary"), ("case", "case")]
    assert all(len(item["options"]) == 4 for item in items)
    assert "drive:" not in response.text and "source_ref" not in response.text
    for item in items:
        result = post(web, "demo/answer", {"item_id": item["id"], "option_index": 0})
        assert result.status_code == 200
        assert "explanation" in result.json()
        assert "drive:" not in result.text and "source_ref" not in result.text
    with closing(get_connection(str(web.db))) as conn:
        assert before == {name: conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in before}


def test_demo_rejects_invalid_and_cross_origin_submissions(web):
    assert post(web, "demo/answer", {"item_id": "case", "option_index": True}).status_code == 400
    assert post(web, "demo/answer", {"item_id": "other", "option_index": 0}).status_code == 400
    assert post(web, "demo/answer", {"item_id": "case", "option_index": 4}).status_code == 400
    assert web.client.post("/web/demo/answer", json={"item_id": "case", "option_index": 0},
                           headers={"Origin": "https://elsewhere.example.test"}).status_code == 403
    assert web.client.get("/web/progress/overview").status_code == 401


def test_demo_fails_closed_when_selected_derivative_is_not_approved(web, monkeypatch):
    original = demo._approved
    def only_other_content(path, kind, item_id):
        if item_id == "case_first_consultation_001":
            raise demo.DemoUnavailable("demo_unavailable")
        return original(path, kind, item_id)
    monkeypatch.setattr(demo, "_approved", only_other_content)
    assert web.client.get("/web/demo/items").status_code == 503
    assert post(web, "demo/answer", {"item_id": "theory", "option_index": 0}).status_code == 503
