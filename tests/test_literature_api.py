import json
import os
import sqlite3
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.db import create_or_load_user
from app.literature import load_literature_items
from app.miniapp_api import (
    build_literature_items_response,
    build_literature_state_response,
    build_literature_topics_response,
)
from app.miniapp_fastapi import create_app
from tests.test_miniapp_api import _make_init_data, _setup_schema


class LiteratureApiTests(unittest.TestCase):
    def setUp(self):
        self.bot_token = "123:abc"
        fd, self.db = tempfile.mkstemp(prefix="literature-api-", suffix=".sqlite3")
        os.close(fd)
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        _setup_schema(conn)
        user = create_or_load_user(conn, 42, "u", "f", None)
        self.user_id = int(user["id"])
        self.first_item = load_literature_items()[0]
        self.second_item = load_literature_items()[1]
        conn.execute(
            """
            INSERT INTO user_literature_progress (
                user_id, literature_id, reading_status, progress_percent,
                started_at, completed_at, updated_at, last_opened_at, private_note, remind_at
            ) VALUES (?, ?, 'in_progress', 40, '2026-01-01T00:00:00Z', NULL,
                      '2026-01-02T00:00:00Z', '2026-01-03T00:00:00Z', 'private text', NULL)
            """,
            (self.user_id, self.first_item["id"]),
        )
        other = create_or_load_user(conn, 777, "other", None, None)
        conn.execute(
            """
            INSERT INTO user_literature_progress (user_id, literature_id, reading_status, progress_percent, updated_at)
            VALUES (?, ?, 'read', 100, '2026-01-04T00:00:00Z')
            """,
            (int(other["id"]), self.second_item["id"]),
        )
        conn.commit()
        conn.close()
        self.init_data = _make_init_data(self.bot_token, {"id": 42, "username": "u", "first_name": "f"})
        self.client = TestClient(create_app(db_path=self.db, bot_token=self.bot_token))

    def tearDown(self):
        if os.path.exists(self.db):
            os.remove(self.db)

    def _payload(self, response_tuple):
        return json.loads(response_tuple[2].decode("utf-8"))

    def test_topics_endpoint_returns_literature_topics_and_counts(self):
        code, _, body = build_literature_topics_response(self.db, self.bot_token, self.init_data)
        self.assertEqual(200, code)
        payload = json.loads(body)
        self.assertTrue(payload["ok"])
        topics = payload["literature_topics"]
        self.assertGreaterEqual(len(topics), 1)
        topic = next(item for item in topics if item["topic_id"] == self.first_item["topic_id"])
        self.assertIn("title", topic)
        self.assertGreater(topic["item_count"], 0)
        self.assertIn("review", topic["status_counts"])
        self.assertEqual({"in_progress": 1}, topic["user_reading_status_counts"])

    def test_items_endpoint_returns_all_items_ordered_by_global_order_without_internal_fields(self):
        payload = self._payload(build_literature_items_response(self.db, self.bot_token, self.init_data))
        items = payload["literature_items"]
        self.assertEqual(sorted(item["global_order"] for item in items), [item["global_order"] for item in items])
        dumped = json.dumps(items, ensure_ascii=False)
        self.assertNotIn("source_refs", dumped)
        self.assertNotIn("notes", dumped)
        self.assertNotIn("private text", dumped)
        first = next(item for item in items if item["id"] == self.first_item["id"])
        self.assertEqual("in_progress", first["user_state"]["reading_status"])
        self.assertNotIn("private_note", first["user_state"])

    def test_items_endpoint_filters_by_topic_and_orders_by_topic_order(self):
        topic_id = self.first_item["topic_id"]
        payload = self._payload(build_literature_items_response(self.db, self.bot_token, self.init_data, topic_id))
        items = payload["literature_items"]
        self.assertTrue(items)
        self.assertTrue(all(item["topic_id"] == topic_id for item in items))
        self.assertEqual(sorted(item["topic_order"] for item in items), [item["topic_order"] for item in items])

    def test_state_endpoint_returns_only_existing_rows_for_authenticated_user_and_does_not_create_rows(self):
        before = self._progress_count()
        payload = self._payload(build_literature_state_response(self.db, self.bot_token, self.init_data))
        after = self._progress_count()
        self.assertEqual(before, after)
        self.assertEqual(1, len(payload["literature_state"]))
        state = payload["literature_state"][0]
        self.assertEqual(self.first_item["id"], state["literature_id"])
        self.assertEqual("in_progress", state["reading_status"])
        self.assertNotIn("private_note", state)
        self.assertNotEqual(self.second_item["id"], state["literature_id"])

    def test_unauthenticated_literature_request_uses_existing_auth_error_style(self):
        response = self.client.get("/miniapp/literature/state")
        self.assertEqual(401, response.status_code)
        self.assertEqual({"ok": False, "error": "missing_init_data"}, response.json())

    def test_fastapi_routes_include_literature_get_options_and_no_progress_post(self):
        routes = {(route.path, method) for route in self.client.app.routes for method in getattr(route, "methods", set())}
        self.assertIn(("/miniapp/literature/topics", "GET"), routes)
        self.assertIn(("/miniapp/literature/items", "GET"), routes)
        self.assertIn(("/miniapp/literature/state", "GET"), routes)
        self.assertIn(("/miniapp/literature/topics", "OPTIONS"), routes)
        self.assertNotIn(("/miniapp/literature/progress", "POST"), routes)
        self.assertNotIn(("/miniapp/literature/next", "POST"), routes)

    def _progress_count(self):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute("SELECT COUNT(*) FROM user_literature_progress").fetchone()[0]
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
