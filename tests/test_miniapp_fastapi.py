import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db import create_or_load_user, start_quiz_session, store_session_questions
from app.miniapp_api import _database_busy_response, build_answer_response, build_setup_options_response, build_setup_response, build_state_response
from app.miniapp_fastapi import create_app
from tests.test_miniapp_api import _make_init_data, _setup_schema


class MiniAppFastApiTests(unittest.TestCase):
    def setUp(self):
        self.bot_token = "123:abc"
        fd, self.db = tempfile.mkstemp(prefix="miniapp-fastapi-", suffix=".sqlite3")
        os.close(fd)
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        _setup_schema(conn)
        conn.execute("INSERT INTO categories (slug,name) VALUES ('c','C')")
        conn.execute("INSERT INTO questions (external_id,category_id,source_ref,difficulty,status,question_text,explanation) VALUES ('q1',1,'s','easy','approved','Q1','E')")
        conn.execute("INSERT INTO questions (external_id,category_id,source_ref,difficulty,status,question_text,explanation) VALUES ('q2',1,'s','easy','approved','Q2','E2')")
        conn.execute("INSERT INTO question_options (question_id,option_index,option_text,is_correct) VALUES (1,0,'A',1),(1,1,'B',0)")
        conn.execute("INSERT INTO question_options (question_id,option_index,option_text,is_correct) VALUES (2,0,'C',1),(2,1,'D',0)")
        user = create_or_load_user(conn, 42, "u", "f", None)
        self.user_id = int(user["id"])
        self.session_id = start_quiz_session(conn, self.user_id, 1)
        store_session_questions(conn, self.session_id, [1, 2])
        conn.commit()
        conn.close()
        self.init_data = _make_init_data(self.bot_token, {"id": 42, "username": "u", "first_name": "f"})
        self.client = TestClient(create_app(db_path=self.db, bot_token=self.bot_token, allowed_origin="https://miniapp.example.com"))

    @staticmethod
    def _decode_json_bytes(body: bytes):
        return json.loads(body.decode("utf-8"))

    def tearDown(self):
        if os.path.exists(self.db):
            os.remove(self.db)

    def test_get_state_with_header_auth(self):
        response = self.client.get("/miniapp/state", headers={"Authorization": f"tma {self.init_data}"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("runner_state", payload)
        self.assertEqual("application/json; charset=utf-8", response.headers.get("content-type"))

    def test_get_state_matches_legacy_builder_contract(self):
        response = self.client.get("/miniapp/state", headers={"Authorization": f"tma {self.init_data}"})
        expected_status, expected_headers, expected_body = build_state_response(self.db, self.bot_token, self.init_data)
        self.assertEqual(expected_status, response.status_code)
        self.assertEqual(self._decode_json_bytes(expected_body), response.json())
        self.assertEqual(expected_headers["Content-Type"], response.headers.get("content-type"))

    def test_get_setup_options_with_x_telegram_header(self):
        response = self.client.get("/miniapp/setup-options", headers={"X-Telegram-Init-Data": self.init_data})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("setup_options", payload)
        self.assertEqual("application/json; charset=utf-8", response.headers.get("content-type"))

    def test_get_setup_options_matches_legacy_builder_contract(self):
        response = self.client.get("/miniapp/setup-options", headers={"X-Telegram-Init-Data": self.init_data})
        expected_status, expected_headers, expected_body = build_setup_options_response(self.db, self.bot_token, self.init_data)
        self.assertEqual(expected_status, response.status_code)
        self.assertEqual(self._decode_json_bytes(expected_body), response.json())
        self.assertEqual(expected_headers["Content-Type"], response.headers.get("content-type"))

    def test_post_setup_simple_body_transport(self):
        request_payload = {
            "init_data": self.init_data,
            "request_id": "req-123",
            "payload": {"quiz_mode": "all", "category_ids": [], "question_count": 5, "difficulty": "any"},
        }
        response = self.client.post(
            "/miniapp/setup",
            json=request_payload,
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("runner_state", payload)
        self.assertEqual("application/json; charset=utf-8", response.headers.get("content-type"))

        expected_status, expected_headers, expected_body = build_setup_response(
            self.db,
            self.bot_token,
            self.init_data,
            json.dumps(request_payload["payload"], separators=(",", ":")).encode("utf-8"),
        )
        self.assertEqual(expected_status, response.status_code)
        self.assertEqual(expected_headers["Content-Type"], response.headers.get("content-type"))
        self.assertEqual(self._decode_json_bytes(expected_body), payload)

    def test_post_answer_simple_body_transport(self):
        request_payload = {
            "init_data": self.init_data,
            "payload": {"session_id": self.session_id, "question_id": 1, "selected_option_index": 0},
        }
        response = self.client.post(
            "/miniapp/answer",
            json=request_payload,
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn(payload["submission_status"], {"accepted", "duplicate"})
        self.assertEqual("application/json; charset=utf-8", response.headers.get("content-type"))
        self.assertIn("feedback", payload)
        self.assertIn("runner_state", payload)

        expected_status, expected_headers, expected_body = build_answer_response(
            self.db,
            self.bot_token,
            self.init_data,
            json.dumps(request_payload["payload"], separators=(",", ":")).encode("utf-8"),
        )
        self.assertEqual(expected_status, response.status_code)
        self.assertEqual(expected_headers["Content-Type"], response.headers.get("content-type"))
        self.assertEqual(self._decode_json_bytes(expected_body), payload)

    def test_post_answer_header_auth_transport(self):
        response = self.client.post(
            "/miniapp/answer",
            headers={"Authorization": f"tma {self.init_data}"},
            json={"session_id": self.session_id, "question_id": 1, "selected_option_index": 0},
        )
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["ok"])

    def test_options_cors(self):
        response = self.client.options(
            "/miniapp/answer",
            headers={
                "Origin": "https://miniapp.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        self.assertEqual(204, response.status_code)
        self.assertEqual("https://miniapp.example.com", response.headers.get("Access-Control-Allow-Origin"))
        self.assertEqual("GET, POST, OPTIONS", response.headers.get("Access-Control-Allow-Methods"))
        self.assertEqual("0", response.headers.get("Content-Length"))
        self.assertEqual("Authorization, Content-Type, X-Telegram-Init-Data, X-Miniapp-Request-Id", response.headers.get("Access-Control-Allow-Headers"))

    def test_get_state_trailing_slash_returns_404(self):
        response = self.client.get("/miniapp/state/", headers={"Authorization": f"tma {self.init_data}"}, follow_redirects=False)
        self.assertEqual(404, response.status_code)
        self.assertNotIn(response.status_code, (301, 307, 308))

    def test_options_state_trailing_slash_returns_404(self):
        response = self.client.options(
            "/miniapp/state/",
            headers={
                "Origin": "https://miniapp.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
            follow_redirects=False,
        )
        self.assertEqual(404, response.status_code)

    def test_get_setup_options_trailing_slash_returns_404(self):
        response = self.client.get("/miniapp/setup-options/", headers={"Authorization": f"tma {self.init_data}"}, follow_redirects=False)
        self.assertEqual(404, response.status_code)
        self.assertNotIn(response.status_code, (301, 307, 308))

    def test_post_answer_trailing_slash_returns_404_without_redirect(self):
        response = self.client.post(
            "/miniapp/answer/",
            headers={"Authorization": f"tma {self.init_data}"},
            json={"session_id": self.session_id, "question_id": 1, "selected_option_index": 0},
            follow_redirects=False,
        )
        self.assertEqual(404, response.status_code)
        self.assertNotIn(response.status_code, (301, 307, 308))

    def test_database_busy_returns_json_503(self):
        with patch("app.miniapp_fastapi.build_state_response", side_effect=lambda *args, **kwargs: _database_busy_response()):
            response = self.client.get("/miniapp/state", headers={"Authorization": f"tma {self.init_data}"})
        self.assertEqual(503, response.status_code)
        self.assertEqual("database_busy_retry", response.json().get("error"))

    def test_missing_init_data_returns_json_error(self):
        response = self.client.get("/miniapp/state")
        self.assertEqual(401, response.status_code)
        self.assertEqual("application/json; charset=utf-8", response.headers.get("content-type"))
        self.assertEqual("missing_init_data", response.json().get("error"))

    def test_invalid_init_data_returns_json_error(self):
        response = self.client.get("/miniapp/state", headers={"Authorization": "tma bad_init_data"})
        self.assertEqual(401, response.status_code)
        self.assertEqual("application/json; charset=utf-8", response.headers.get("content-type"))
        self.assertIn(response.json().get("error"), {"invalid_hash", "missing_hash", "invalid_auth_date"})


if __name__ == "__main__":
    unittest.main()
