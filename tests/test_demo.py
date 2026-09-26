"""The owner-only PWA has no anonymous content or answer routes."""
from contextlib import closing

from app.db import get_connection
from tests.test_web_auth import post, web


def test_anonymous_demo_routes_are_closed_without_creating_learning_state(web):
    with closing(get_connection(str(web.db))) as conn:
        before = {name: conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                  for name in ("quiz_sessions", "quiz_answers", "glossary_sessions", "web_accounts")}
    assert web.client.get("/web/demo/items").status_code == 404
    assert post(web, "demo/answer", {"item_id": "theory", "option_index": 0}).status_code == 404
    assert web.client.get("/web/progress/overview").status_code == 401
    with closing(get_connection(str(web.db))) as conn:
        assert before == {name: conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in before}
