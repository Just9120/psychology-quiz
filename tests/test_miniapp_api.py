import hashlib
import http.client
import hmac
import json
import sqlite3
import threading
import time
import unittest
import tempfile
import os
import urllib.parse
from unittest.mock import patch

from app.db import create_or_load_user, get_connection, init_db_connection, start_quiz_session, store_session_questions
from app.miniapp_api import (
    build_setup_options_response,
    build_setup_response,
    build_answer_response,
    build_state_response,
    start_miniapp_api_server,
    verify_telegram_init_data,
)
from app.miniapp_runner import MiniAppAnswerSubmissionResult


def _setup_schema(conn):
    with open('sql/schema.sql', encoding='utf-8') as f:
        conn.executescript(f.read())


def _make_init_data(bot_token: str, user: dict, auth_date: int | None = None):
    auth_date = auth_date or int(time.time())
    payload = {
        'auth_date': str(auth_date),
        'query_id': 'AAE',
        'user': json.dumps(user, separators=(',', ':')),
    }
    check = '\n'.join(f"{k}={v}" for k, v in sorted(payload.items()))
    secret = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    payload['hash'] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(payload)


class MiniAppApiTests(unittest.TestCase):
    def setUp(self):
        self.bot_token = '123:abc'
        fd, self.db = tempfile.mkstemp(prefix='miniapp-api-', suffix='.sqlite3')
        os.close(fd)
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        _setup_schema(conn)
        conn.execute("INSERT INTO categories (slug,name) VALUES ('c','C')")
        conn.execute("INSERT INTO questions (external_id,category_id,source_ref,difficulty,status,question_text,explanation) VALUES ('q1',1,'s','easy','approved','Q1','E')")
        conn.execute("INSERT INTO questions (external_id,category_id,source_ref,difficulty,status,question_text,explanation) VALUES ('q2',1,'s','easy','approved','Q2','E2')")
        conn.execute("INSERT INTO question_options (question_id,option_index,option_text,is_correct) VALUES (1,0,'A',1),(1,1,'B',0)")
        conn.execute("INSERT INTO question_options (question_id,option_index,option_text,is_correct) VALUES (2,0,'C',1),(2,1,'D',0)")
        user = create_or_load_user(conn, 42, 'u', 'f', None)
        self.user_id = int(user['id'])
        self.session_id = start_quiz_session(conn, self.user_id, 1)
        store_session_questions(conn, self.session_id, [1, 2])
        conn.commit(); conn.close()
        self.init_data = _make_init_data(self.bot_token, {'id': 42, 'username': 'u', 'first_name': 'f'})

    def tearDown(self):
        if os.path.exists(self.db):
            os.remove(self.db)

    def test_verify_valid(self):
        verified = verify_telegram_init_data(self.init_data, self.bot_token)
        self.assertEqual(42, verified.telegram_user_id)

    def test_verify_invalid_hash(self):
        with self.assertRaises(ValueError):
            verify_telegram_init_data(self.init_data + 'x', self.bot_token)

    def test_state_response(self):
        code, _, body = build_state_response(self.db, self.bot_token, self.init_data)
        self.assertEqual(200, code)
        payload = json.loads(body)
        self.assertTrue(payload['ok'])
        self.assertIn(payload['runner_state']['state'], {'in_progress', 'completed', 'setup'})
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn('is_correct', dumped)
        self.assertNotIn('correct_option_index', dumped)
        self.assertNotIn('explanation', dumped)

    def test_answer_response(self):
        code, _, body = build_answer_response(
            self.db,
            self.bot_token,
            self.init_data,
            json.dumps({'session_id': self.session_id, 'question_id': 1, 'selected_option_index': 0}).encode(),
        )
        self.assertEqual(200, code)
        payload = json.loads(body)
        self.assertTrue(payload['ok'])
        self.assertEqual('accepted', payload['submission_status'])
        self.assertIn('runner_state', payload)
        self.assertIn('feedback', payload)
        self.assertIn('is_correct', payload['feedback'])
        self.assertEqual('A', payload['feedback'].get('selected_option_text'))
        self.assertEqual('A', payload['feedback'].get('correct_option_text'))

    def test_ttl_enforced_in_state_response(self):
        old_init_data = _make_init_data(self.bot_token, {'id': 42, 'username': 'u'}, auth_date=int(time.time()) - 10)
        code, _, body = build_state_response(self.db, self.bot_token, old_init_data, max_age_seconds=1)
        self.assertEqual(401, code)
        payload = json.loads(body)
        self.assertEqual('expired_init_data', payload['error'])

    def test_stale_response_contains_runner_state(self):
        first = build_answer_response(
            self.db,
            self.bot_token,
            self.init_data,
            json.dumps({'session_id': self.session_id, 'question_id': 1, 'selected_option_index': 0}).encode(),
        )
        self.assertEqual(200, first[0])
        second_code, _, second_body = build_answer_response(
            self.db,
            self.bot_token,
            self.init_data,
            json.dumps({'session_id': self.session_id, 'question_id': 1, 'selected_option_index': 0}).encode(),
        )
        self.assertEqual(200, second_code)
        payload = json.loads(second_body)
        self.assertIn(payload['submission_status'], {'stale_question', 'duplicate', 'session_not_found'})
        self.assertIn('runner_state', payload)


    def test_duplicate_answer_returns_full_feedback(self):
        with patch(
            'app.miniapp_api.submit_miniapp_answer_event',
            return_value=MiniAppAnswerSubmissionResult(
                status='duplicate',
                session_id=self.session_id,
                selected_option_index=0,
                is_correct=True,
                resolved_question_id=1,
            ),
        ):
            code, _, body = build_answer_response(
                self.db,
                self.bot_token,
                self.init_data,
                json.dumps({'session_id': self.session_id, 'question_id': 1, 'selected_option_index': 0}).encode(),
            )
        self.assertEqual(200, code)
        payload = json.loads(body)
        self.assertTrue(payload['ok'])
        self.assertEqual('duplicate', payload['submission_status'])
        self.assertIn('feedback', payload)
        self.assertEqual(0, payload['feedback'].get('correct_option_index'))
        self.assertEqual('A', payload['feedback'].get('correct_option_text'))
        self.assertEqual('E', payload['feedback'].get('explanation'))

    def test_invalid_option_does_not_expose_feedback(self):
        code, _, body = build_answer_response(
            self.db,
            self.bot_token,
            self.init_data,
            json.dumps({'session_id': self.session_id, 'question_id': 1, 'selected_option_index': 99}).encode(),
        )
        self.assertEqual(200, code)
        payload = json.loads(body)
        self.assertEqual('invalid_option', payload['submission_status'])
        self.assertNotIn('feedback', payload)

    def test_forbidden_does_not_expose_feedback(self):
        other_init = _make_init_data(self.bot_token, {'id': 777, 'username': 'other', 'first_name': 'o'})
        code, _, body = build_answer_response(
            self.db,
            self.bot_token,
            other_init,
            json.dumps({'session_id': self.session_id, 'question_id': 1, 'selected_option_index': 0}).encode(),
        )
        self.assertEqual(200, code)
        payload = json.loads(body)
        self.assertEqual('forbidden', payload['submission_status'])
        self.assertNotIn('feedback', payload)

    def test_options_cors_headers_when_allowed_origin_is_set(self):
        server = start_miniapp_api_server(
            "127.0.0.1",
            0,
            db_path=self.db,
            bot_token=self.bot_token,
            initdata_ttl_seconds=3600,
            allowed_origin="https://miniapp.example.com",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("OPTIONS", "/miniapp/answer", headers={"Origin": "https://miniapp.example.com"})
            response = conn.getresponse()
            self.assertEqual(204, response.status)
            self.assertEqual("https://miniapp.example.com", response.getheader("Access-Control-Allow-Origin"))
            self.assertEqual("GET, POST, OPTIONS", response.getheader("Access-Control-Allow-Methods"))
            self.assertIn("Authorization", response.getheader("Access-Control-Allow-Headers") or "")
            self.assertIn("X-Miniapp-Request-Id", response.getheader("Access-Control-Allow-Headers") or "")
            self.assertEqual("600", response.getheader("Access-Control-Max-Age"))
            conn.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_setup_requires_auth(self):
        code, _, body = build_setup_response(
            self.db, self.bot_token, "", json.dumps({"quiz_mode": "all", "category_ids": [], "question_count": 5, "difficulty": "any"}).encode()
        )
        self.assertEqual(401, code)
        self.assertFalse(json.loads(body)["ok"])

    def test_setup_options_requires_auth(self):
        code, _, body = build_setup_options_response(self.db, self.bot_token, "")
        self.assertEqual(401, code)
        self.assertFalse(json.loads(body)["ok"])

    def test_get_connection_configures_busy_timeout_and_wal(self):
        conn = get_connection(self.db)
        try:
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(10000, busy_timeout)
            self.assertEqual("wal", str(journal_mode).lower())
        finally:
            conn.close()

    def test_init_db_connection_ensures_performance_indexes(self):
        init_db_connection(self.db)
        conn = sqlite3.connect(self.db)
        try:
            rows = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'index'
                  AND name IN (
                    'idx_quiz_sessions_user_status',
                    'idx_quiz_answers_session_question',
                    'idx_quiz_session_questions_session_order',
                    'idx_quiz_session_questions_question'
                  )
                """
            ).fetchall()
            self.assertEqual(
                {
                    "idx_quiz_sessions_user_status",
                    "idx_quiz_answers_session_question",
                    "idx_quiz_session_questions_session_order",
                    "idx_quiz_session_questions_question",
                },
                {name for (name,) in rows},
            )
        finally:
            conn.close()

    def test_connection_context_with_closing_closes_connection(self):
        from contextlib import closing

        with closing(get_connection(self.db)) as conn:
            with conn:
                conn.execute("SELECT 1")
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_setup_options_uses_verified_user_and_returns_safe_payload(self):
        code, _, body = build_setup_options_response(self.db, self.bot_token, self.init_data)
        self.assertEqual(200, code)
        payload = json.loads(body)
        self.assertTrue(payload["ok"])
        self.assertIn("setup_options", payload)
        self.assertIn("categories", payload["setup_options"])
        self.assertEqual([{"id": 1, "name": "C"}], payload["setup_options"]["categories"])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("is_correct", dumped)
        self.assertNotIn("correct_option_index", dumped)
        self.assertNotIn("score", dumped)

    def test_setup_uses_verified_user_not_payload_user(self):
        code, _, body = build_setup_response(
            self.db,
            self.bot_token,
            self.init_data,
            json.dumps({"quiz_mode": "single", "category_ids": [1], "question_count": 5, "difficulty": "any", "user_id": 999999}).encode(),
        )
        self.assertEqual(200, code)
        payload = json.loads(body)
        self.assertTrue(payload["ok"])
        self.assertEqual("in_progress", payload["runner_state"]["state"])

    def test_simple_body_auth_for_answer_and_setup(self):
        server = start_miniapp_api_server("127.0.0.1", 0, db_path=self.db, bot_token=self.bot_token, allowed_origin="https://miniapp.example.com")
        t = threading.Thread(target=server.serve_forever, daemon=True); t.start()
        try:
            port = server.server_address[1]
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            answer_body = json.dumps({"init_data": self.init_data, "request_id": "rq_" + ("x" * 100), "payload": {"session_id": self.session_id, "question_id": 1, "selected_option_index": 0}})
            conn.request("POST", "/miniapp/answer", body=answer_body, headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": "https://miniapp.example.com"})
            answer_resp = conn.getresponse()
            self.assertEqual(200, answer_resp.status)
            answer_payload = json.loads(answer_resp.read())
            self.assertTrue(answer_payload["ok"])
            self.assertIn(answer_payload["submission_status"], {"accepted", "duplicate", "stale_question"})
            setup_body = json.dumps({"init_data": self.init_data, "request_id": "rq_setup", "payload": {"quiz_mode": "single", "category_ids": [1], "question_count": 5, "difficulty": "any", "user_id": 999}})
            conn.request("POST", "/miniapp/setup", body=setup_body, headers={"Content-Type": "text/plain;charset=UTF-8", "Origin": "https://miniapp.example.com"})
            setup_resp = conn.getresponse()
            self.assertEqual(200, setup_resp.status)
            setup_payload = json.loads(setup_resp.read())
            self.assertTrue(setup_payload["ok"])
            conn.close()
        finally:
            server.shutdown(); server.server_close()

    def test_simple_body_rejects_missing_or_invalid_init_data(self):
        server = start_miniapp_api_server("127.0.0.1", 0, db_path=self.db, bot_token=self.bot_token)
        t = threading.Thread(target=server.serve_forever, daemon=True); t.start()
        try:
            port = server.server_address[1]
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            bad_body = json.dumps({"request_id": "rq_bad", "payload": {"session_id": self.session_id, "question_id": 1, "selected_option_index": 0}})
            conn.request("POST", "/miniapp/answer", body=bad_body, headers={"Content-Type": "text/plain;charset=UTF-8"})
            resp = conn.getresponse()
            self.assertEqual(401, resp.status)
            payload = json.loads(resp.read())
            self.assertFalse(payload["ok"])
            conn.close()
        finally:
            server.shutdown(); server.server_close()

if __name__ == '__main__':
    unittest.main()
