import json
import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch


from fastapi.testclient import TestClient

from app.db import create_or_load_user, start_quiz_session, store_session_questions
from app.miniapp_api import _database_busy_response, build_answer_response, build_setup_options_response, build_setup_response, build_state_response
from app.miniapp_fastapi import create_app, create_app_from_env
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


    def test_all_miniapp_api_routes_keep_methods_and_paths(self):
        app = create_app(db_path=self.db, bot_token=self.bot_token)
        routes = {(route.path, method) for route in app.routes for method in getattr(route, "methods", set())}
        expected = {
            ("/healthz", "GET"),
            ("/miniapp/state", "OPTIONS"),
            ("/miniapp/setup-options", "OPTIONS"),
            ("/miniapp/setup", "OPTIONS"),
            ("/miniapp/answer", "OPTIONS"),
            ("/miniapp/glossary/topics", "OPTIONS"),
            ("/miniapp/glossary/start", "OPTIONS"),
            ("/miniapp/glossary/answer", "OPTIONS"),
            ("/miniapp/glossary/next", "OPTIONS"),
            ("/miniapp/glossary/restart", "OPTIONS"),
            ("/miniapp/state", "GET"),
            ("/miniapp/setup-options", "GET"),
            ("/miniapp/setup", "POST"),
            ("/miniapp/answer", "POST"),
            ("/miniapp/glossary/topics", "GET"),
            ("/miniapp/glossary/start", "POST"),
            ("/miniapp/glossary/answer", "POST"),
            ("/miniapp/glossary/next", "POST"),
            ("/miniapp/glossary/restart", "POST"),
        }
        self.assertTrue(expected.issubset(routes))

    def test_options_preflight_contract_for_allowed_and_disallowed_origins(self):
        for origin, expected_origin in (("https://miniapp.example.com", "https://miniapp.example.com"), ("https://evil.example.com", None)):
            with self.subTest(origin=origin):
                response = self.client.options(
                    "/miniapp/setup",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "Authorization, Content-Type",
                    },
                )
                self.assertEqual(204, response.status_code)
                self.assertEqual(expected_origin, response.headers.get("Access-Control-Allow-Origin"))
                self.assertEqual("GET, POST, OPTIONS", response.headers.get("Access-Control-Allow-Methods"))
                self.assertEqual("Authorization, Content-Type, X-Telegram-Init-Data, X-Miniapp-Request-Id", response.headers.get("Access-Control-Allow-Headers"))
                self.assertEqual("600", response.headers.get("Access-Control-Max-Age"))
                self.assertEqual("0", response.headers.get("Content-Length"))

    def test_get_endpoint_builder_status_headers_and_body_pass_through(self):
        with patch("app.miniapp_fastapi.build_state_response", return_value=(202, {"Content-Type": "application/custom", "X-Builder": "yes"}, b"custom-body")) as builder:
            response = self.client.get(
                "/miniapp/state",
                headers={"Authorization": "tma header-init", "X-Miniapp-Request-Id": "rid"},
            )

        self.assertEqual(202, response.status_code)
        self.assertEqual("application/custom", response.headers.get("Content-Type"))
        self.assertEqual("yes", response.headers.get("X-Builder"))
        self.assertEqual("no-store", response.headers.get("Cache-Control"))
        self.assertEqual(b"custom-body", response.content)
        builder.assert_called_once_with(self.db, self.bot_token, "header-init", max_age_seconds=3600)

    def test_post_endpoints_extract_same_transport_payloads(self):
        endpoints = (
            ("/miniapp/setup", "build_setup_response", (self.db, self.bot_token)),
            ("/miniapp/answer", "build_answer_response", (self.db, self.bot_token)),
            ("/miniapp/glossary/start", "build_glossary_start_response", (self.bot_token,)),
            ("/miniapp/glossary/answer", "build_glossary_answer_response", (self.bot_token,)),
            ("/miniapp/glossary/next", "build_glossary_next_response", (self.bot_token,)),
            ("/miniapp/glossary/restart", "build_glossary_restart_response", (self.bot_token,)),
        )
        for path, builder_name, leading_args in endpoints:
            with self.subTest(path=path):
                request_payload = {"init_data": "simple-init", "request_id": "body-rid", "payload": {"value": path}}
                with patch(f"app.miniapp_fastapi.{builder_name}", return_value=(207, {"Content-Type": "application/json; charset=utf-8", "X-Builder": path}, b'{"ok":true}')) as builder:
                    response = self.client.post(path, json=request_payload)

                self.assertEqual(207, response.status_code)
                self.assertEqual(path, response.headers.get("X-Builder"))
                self.assertEqual({"ok": True}, response.json())
                expected_body = json.dumps(request_payload["payload"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                builder.assert_called_once_with(*leading_args, "simple-init", expected_body, max_age_seconds=3600)

    def test_post_endpoint_header_auth_uses_raw_body_and_header_request_id(self):
        with patch("app.miniapp_fastapi.build_answer_response", return_value=(208, {"Content-Type": "text/plain"}, b"raw-ok")) as builder:
            response = self.client.post(
                "/miniapp/answer",
                headers={"X-Telegram-Init-Data": "header-init", "X-Miniapp-Request-Id": "header-rid"},
                content=b'{"raw":true}',
            )

        self.assertEqual(208, response.status_code)
        self.assertEqual(b"raw-ok", response.content)
        builder.assert_called_once_with(self.db, self.bot_token, "header-init", b'{"raw":true}', max_age_seconds=3600)

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

        shadow_db = f"{self.db}.expected"
        shutil.copyfile(self.db, shadow_db)
        with patch("app.miniapp_api.select_random_approved_question_ids_across_active_categories", return_value=[1, 2]):
            expected_status, expected_headers, expected_body = build_setup_response(
                shadow_db,
                self.bot_token,
                self.init_data,
                json.dumps(request_payload["payload"], separators=(",", ":")).encode("utf-8"),
            )

            response = self.client.post(
                "/miniapp/setup",
                json=request_payload,
            )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIn("runner_state", payload)
        self.assertEqual("application/json; charset=utf-8", response.headers.get("content-type"))

        self.assertEqual(expected_status, response.status_code)
        self.assertEqual(expected_headers["Content-Type"], response.headers.get("content-type"))
        self.assertEqual(self._decode_json_bytes(expected_body), payload)
        os.remove(shadow_db)

    def test_post_answer_simple_body_transport(self):
        request_payload = {
            "init_data": self.init_data,
            "payload": {"session_id": self.session_id, "question_id": 1, "selected_option_index": 0},
        }

        shadow_db = f"{self.db}.expected"
        shutil.copyfile(self.db, shadow_db)
        expected_status, expected_headers, expected_body = build_answer_response(
            shadow_db,
            self.bot_token,
            self.init_data,
            json.dumps(request_payload["payload"], separators=(",", ":")).encode("utf-8"),
        )

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

        self.assertEqual(expected_status, response.status_code)
        self.assertEqual(expected_headers["Content-Type"], response.headers.get("content-type"))
        self.assertEqual(self._decode_json_bytes(expected_body), payload)
        os.remove(shadow_db)

    def test_post_answer_header_auth_transport(self):
        response = self.client.post(
            "/miniapp/answer",
            headers={"Authorization": f"tma {self.init_data}"},
            json={"session_id": self.session_id, "question_id": 1, "selected_option_index": 0},
        )
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()["ok"])



    def test_structured_request_logging_includes_duration(self):
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            response = self.client.get("/miniapp/state", headers={"Authorization": f"tma {self.init_data}", "X-Miniapp-Request-Id": "rid-1"})
        self.assertEqual(200, response.status_code)
        joined = "\n".join(logs.output)
        self.assertIn("miniapp_api endpoint=/miniapp/state", joined)
        self.assertIn("request_id=rid-1", joined)
        self.assertIn("duration_ms=", joined)

    def test_slow_request_logging_warning(self):
        app = create_app(db_path=self.db, bot_token=self.bot_token, slow_request_ms=1, allowed_origin="https://miniapp.example.com")
        client = TestClient(app)
        with patch("app.miniapp_fastapi.verify_telegram_init_data") as verify_mock:
            verify_mock.return_value.telegram_user_id = 42
            with patch("app.miniapp_fastapi._duration_ms", return_value=10):
                with self.assertLogs("uvicorn.error", level="WARNING") as logs:
                    response = client.get("/miniapp/state", headers={"Authorization": f"tma {self.init_data}"})
        self.assertEqual(200, response.status_code)
        self.assertTrue(any("miniapp_api_slow endpoint=/miniapp/state" in line for line in logs.output))

    def test_logs_do_not_contain_init_data_or_authorization(self):
        secret_token = "super-secret-init-data"
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            self.client.get("/miniapp/state", headers={"Authorization": f"tma {secret_token}"})
        joined = "\n".join(logs.output)
        self.assertNotIn(secret_token, joined)
        self.assertNotIn("Authorization", joined)

    def test_options_preflight_emits_structured_log(self):
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            response = self.client.options(
                "/miniapp/answer",
                headers={
                    "Origin": "https://miniapp.example.com",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Authorization, Content-Type",
                },
            )
        self.assertEqual(204, response.status_code)
        self.assertTrue(any("miniapp_api endpoint=/miniapp/answer" in line and "method=OPTIONS" in line for line in logs.output))

    def test_healthz_returns_expected_payload(self):
        response = self.client.get("/healthz")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"ok": True, "service": "miniapp_api"}, response.json())
        self.assertEqual("application/json", response.headers.get("content-type"))

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

    def test_missing_init_data_logs_structured_duration(self):
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            response = self.client.get("/miniapp/state")
        self.assertEqual(401, response.status_code)
        joined = "\n".join(logs.output)
        self.assertIn("miniapp_api endpoint=/miniapp/state", joined)
        self.assertIn("status=401", joined)
        self.assertIn("duration_ms=", joined)

    def test_fastapi_routes_use_to_thread_for_builders(self):
        to_thread_calls = []

        async def fake_to_thread(func, *args, **kwargs):
            to_thread_calls.append(func.__name__)
            return func(*args, **kwargs)

        with patch("app.miniapp_fastapi.asyncio.to_thread", side_effect=fake_to_thread):
            self.client.get("/miniapp/state", headers={"Authorization": f"tma {self.init_data}"})
            self.client.get("/miniapp/setup-options", headers={"Authorization": f"tma {self.init_data}"})
            self.client.post("/miniapp/setup", json={"init_data": self.init_data, "payload": {"quiz_mode": "all", "category_ids": [], "question_count": 1, "difficulty": "any"}})
            self.client.post("/miniapp/answer", json={"init_data": self.init_data, "payload": {"session_id": self.session_id, "question_id": 1, "selected_option_index": 0}})

        self.assertEqual(
            ["build_state_response", "build_setup_options_response", "build_setup_response", "build_answer_response"],
            to_thread_calls,
        )

    def test_slow_builder_does_not_block_healthz(self):
        app = create_app(db_path=self.db, bot_token=self.bot_token, allowed_origin="https://miniapp.example.com")
        with patch("app.miniapp_fastapi.build_state_response", side_effect=lambda *args, **kwargs: (time.sleep(0.25) or (200, {"Content-Type": "application/json; charset=utf-8"}, b'{"ok":true}'))):
            import threading

            state_client = TestClient(app)
            health_client = TestClient(app)
            state_status = {}

            def call_state():
                state_status["code"] = state_client.get("/miniapp/state", headers={"Authorization": f"tma {self.init_data}"}).status_code

            t = threading.Thread(target=call_state)
            t.start()
            time.sleep(0.05)
            started = time.perf_counter()
            health_response = health_client.get("/healthz")
            elapsed = time.perf_counter() - started
            t.join()

        self.assertEqual(200, state_status["code"])
        self.assertEqual(200, health_response.status_code)
        self.assertLess(elapsed, 0.2)

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


class MiniAppFastApiRuntimeEnvTests(unittest.TestCase):
    def test_create_app_from_env_success(self):
        with patch.dict(os.environ, {"BOT_TOKEN": "123:abc", "DB_PATH": "/tmp/dev.sqlite3", "MINIAPP_API_INITDATA_TTL_SECONDS": "120", "MINIAPP_API_SLOW_REQUEST_MS": "250", "MINIAPP_API_ALLOWED_ORIGIN": "https://miniapp.example.com"}, clear=True):
            app = create_app_from_env()
        client = TestClient(app)
        response = client.get("/healthz")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"ok": True, "service": "miniapp_api"}, response.json())

    def test_create_app_from_env_missing_required_var_fails_fast(self):
        with patch.dict(os.environ, {"DB_PATH": "/tmp/dev.sqlite3"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "BOT_TOKEN"):
                create_app_from_env()




if __name__ == "__main__":
    unittest.main()
