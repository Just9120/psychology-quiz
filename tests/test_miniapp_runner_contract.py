import sqlite3
import unittest

from app.db import create_or_load_user, start_quiz_session, store_session_questions
from app.main import _parse_miniapp_answer_payload
from app.miniapp_runner import get_current_miniapp_question_snapshot, submit_miniapp_answer_event


def _setup_schema(conn: sqlite3.Connection) -> None:
    with open("sql/schema.sql", "r", encoding="utf-8") as f:
        conn.executescript(f.read())


class MiniAppRunnerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        _setup_schema(self.conn)

        self.conn.execute("INSERT INTO categories (slug, name) VALUES ('cat-1', 'Category 1')")
        self.conn.execute(
            "INSERT INTO questions (external_id, category_id, source_ref, difficulty, status, question_text, explanation) VALUES ('q1', 1, 'src', 'easy', 'approved', 'Q1?', 'E1')"
        )
        self.conn.execute(
            "INSERT INTO questions (external_id, category_id, source_ref, difficulty, status, question_text, explanation) VALUES ('q2', 1, 'src', 'easy', 'approved', 'Q2?', 'E2')"
        )
        self.conn.execute(
            "INSERT INTO question_options (question_id, option_index, option_text, is_correct) VALUES (1, 0, 'A', 1), (1, 1, 'B', 0), (2, 0, 'A', 0), (2, 1, 'B', 1)"
        )

        user = create_or_load_user(self.conn, 1001, "u1", "U", None)
        self.user_id = int(user["id"])
        self.session_id = start_quiz_session(self.conn, self.user_id, 1)
        store_session_questions(self.conn, self.session_id, [1, 2])

    def tearDown(self) -> None:
        self.conn.close()

    def test_valid_answer_transition(self):
        result = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        self.assertEqual("accepted", result.status)
        self.assertTrue(result.is_correct)

    def test_invalid_option_rejected(self):
        result = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=99,
        )
        self.assertEqual("invalid_option", result.status)

    def test_stale_question_rejected(self):
        accepted = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        self.assertEqual("accepted", accepted.status)
        stale = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        self.assertEqual("stale_question", stale.status)
        self.assertEqual(2, stale.expected_question_id)

    def test_duplicate_submission_handled_safely(self):
        first = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        self.assertEqual("accepted", first.status)
        duplicate = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        self.assertIn(duplicate.status, {"stale_question", "duplicate"})

    def test_wrong_user_rejected(self):
        other = create_or_load_user(self.conn, 2002, "u2", "U2", None)
        result = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=int(other["id"]),
            question_id=1,
            selected_option_index=0,
        )
        self.assertEqual("forbidden", result.status)

    def test_snapshot_for_authorized_user(self):
        result = get_current_miniapp_question_snapshot(
            self.conn,
            actor_user_id=self.user_id,
            session_id=self.session_id,
        )
        self.assertEqual("ok", result.status)
        self.assertEqual(1, result.question_id)
        self.assertEqual(1, result.order_index)
        self.assertEqual(2, result.total_questions)
        self.assertTrue(result.options)
        self.assertNotIn("is_correct", result.options[0])


    def test_parse_valid_miniapp_answer_payload(self):
        parsed = _parse_miniapp_answer_payload({
            "type": "quiz_answer",
            "session_id": self.session_id,
            "question_id": 1,
            "selected_option_index": 0,
        })
        self.assertEqual((self.session_id, 1, 0), parsed)

    def test_parse_malformed_miniapp_answer_payload(self):
        self.assertIsNone(_parse_miniapp_answer_payload({"type": "quiz_answer", "session_id": "1"}))
        self.assertIsNone(_parse_miniapp_answer_payload({"type": "quiz_answer", "session_id": 0, "question_id": 1, "selected_option_index": 0}))

    def test_snapshot_moves_to_next_question_after_accepted_answer(self):
        accepted = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        self.assertEqual("accepted", accepted.status)
        snapshot = get_current_miniapp_question_snapshot(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        self.assertEqual("ok", snapshot.status)
        self.assertEqual(2, snapshot.question_id)

    def test_snapshot_wrong_user_forbidden(self):
        other = create_or_load_user(self.conn, 2002, "u2", "U2", None)
        result = get_current_miniapp_question_snapshot(
            self.conn,
            actor_user_id=int(other["id"]),
            session_id=self.session_id,
        )
        self.assertEqual("forbidden", result.status)

    def test_snapshot_finished_session_safe_status(self):
        submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=2,
            selected_option_index=1,
        )
        self.conn.execute("UPDATE quiz_sessions SET status = 'finished' WHERE id = ?", (self.session_id,))
        result = get_current_miniapp_question_snapshot(
            self.conn,
            actor_user_id=self.user_id,
            session_id=self.session_id,
        )
        self.assertEqual("session_not_in_progress", result.status)


if __name__ == "__main__":
    unittest.main()
