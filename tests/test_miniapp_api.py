import hashlib
import hmac
import json
import sqlite3
import time
import unittest
import tempfile
import os
import urllib.parse

from app.db import create_or_load_user, start_quiz_session, store_session_questions
from app.miniapp_api import build_answer_response, build_state_response, verify_telegram_init_data


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
        conn.execute("INSERT INTO question_options (question_id,option_index,option_text,is_correct) VALUES (1,0,'A',1),(1,1,'B',0)")
        user = create_or_load_user(conn, 42, 'u', 'f', None)
        self.user_id = int(user['id'])
        self.session_id = start_quiz_session(conn, self.user_id, 1)
        store_session_questions(conn, self.session_id, [1])
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
        self.assertIn(payload['submission_status'], {'accepted', 'duplicate', 'stale_question'})

if __name__ == '__main__':
    unittest.main()
