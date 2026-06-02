import os
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace

from app.db import create_or_load_user, start_quiz_session, store_session_questions
from app.main import (
    CLASSIC_REPLY_NEXT_TEXT,
    _classic_text_latency_bucket,
    _handle_classic_text_answer_db,
    _load_classic_text_answer_context,
    _load_classic_text_next_state,
    _safe_classic_text_log_fields,
    build_classic_answer_reply_keyboard,
    build_question_text_with_options,
    parse_classic_reply_answer_number,
)


def _setup_schema(conn: sqlite3.Connection) -> None:
    with open("sql/schema.sql", "r", encoding="utf-8") as f:
        conn.executescript(f.read())


class ClassicReplyKeyboardModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.tmp.close()
        self.db_path = self.tmp.name
        self.settings = SimpleNamespace(db_path=self.db_path, classic_quiz_reply_keyboard_mode=True)
        self.disabled_settings = SimpleNamespace(db_path=self.db_path, classic_quiz_reply_keyboard_mode=False)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            _setup_schema(conn)
            conn.execute("INSERT INTO categories (slug, name) VALUES ('cat-1', 'Category 1')")
            conn.execute(
                "INSERT INTO questions (external_id, category_id, source_ref, difficulty, status, question_text, explanation) "
                "VALUES ('q1', 1, 'src', 'easy', 'approved', 'Q1?', 'E1')"
            )
            conn.execute(
                "INSERT INTO questions (external_id, category_id, source_ref, difficulty, status, question_text, explanation) "
                "VALUES ('q2', 1, 'src', 'easy', 'approved', 'Q2?', 'E2')"
            )
            conn.execute(
                "INSERT INTO question_options (question_id, option_index, option_text, is_correct) "
                "VALUES (1, 0, 'A', 1), (1, 1, 'B', 0), (2, 0, 'C', 0), (2, 1, 'D', 1)"
            )
            user = create_or_load_user(conn, 1001, "u1", "U", None)
            self.user_id = int(user["id"])
            self.session_id = start_quiz_session(conn, self.user_id, 1)
            store_session_questions(conn, self.session_id, [1, 2])

        self.tg_user = SimpleNamespace(id=1001, username="u1", first_name="U", last_name=None)
        self.state = {"status": "awaiting_answer", "session_id": self.session_id, "question_id": 1}

    def tearDown(self) -> None:
        os.unlink(self.db_path)

    def test_default_callback_mode_can_still_render_inline_style_labels(self):
        text = build_question_text_with_options(1, 1, "Question", [{"option_index": 0, "option_text": "Alpha"}], "normal")
        self.assertIn("A. Alpha", text)
        self.assertNotIn("1. Alpha", text)

    def test_reply_keyboard_mode_renders_numeric_options_and_buttons(self):
        options = [{"option_index": 0, "option_text": "Alpha"}, {"option_index": 1, "option_text": "Beta"}]
        text = build_question_text_with_options(1, 1, "Question", options, "normal", numeric_labels=True)
        markup = build_classic_answer_reply_keyboard(options)

        self.assertIn("1. Alpha", text)
        self.assertIn("2. Beta", text)
        self.assertEqual(("1", "2"), tuple(button.text for button in markup.keyboard[0]))

    def test_text_answer_context_requires_enabled_active_awaiting_session(self):
        enabled = _load_classic_text_answer_context(self.settings, self.tg_user, self.state)
        self.assertEqual("ok", enabled["status"])
        self.assertEqual(self.session_id, enabled["session_id"])

        disabled = _load_classic_text_answer_context(self.disabled_settings, self.tg_user, self.state)
        self.assertEqual("disabled", disabled["status"])

        no_state = _load_classic_text_answer_context(self.settings, self.tg_user, {})
        self.assertEqual("not_awaiting_answer", no_state["status"])

    def test_safe_classic_text_latency_fields_include_deterministic_bucket(self):
        fields = _safe_classic_text_log_fields(
            telegram_user_id=1001,
            session_id=self.session_id,
            question_id=1,
            elapsed_ms=499,
            status="accepted",
        )

        self.assertIn("telegram_user_id=1001", fields)
        self.assertIn(f"session_id={self.session_id}", fields)
        self.assertIn("question_id=1", fields)
        self.assertIn("elapsed_ms=499", fields)
        self.assertIn("latency_bucket=lt_500ms", fields)
        self.assertIn("status=accepted", fields)
        self.assertNotIn("Q1?", fields)
        self.assertNotIn("A", fields)
        self.assertNotIn("initData", fields)

    def test_classic_text_latency_bucket_boundaries_are_stable(self):
        self.assertEqual("lt_100ms", _classic_text_latency_bucket(0))
        self.assertEqual("lt_100ms", _classic_text_latency_bucket(99))
        self.assertEqual("lt_500ms", _classic_text_latency_bucket(100))
        self.assertEqual("lt_500ms", _classic_text_latency_bucket(499))
        self.assertEqual("lt_1000ms", _classic_text_latency_bucket(500))
        self.assertEqual("lt_1000ms", _classic_text_latency_bucket(999))
        self.assertEqual("gte_1000ms", _classic_text_latency_bucket(1000))

    def test_valid_answer_number_handling_records_answer(self):
        context = _load_classic_text_answer_context(self.settings, self.tg_user, self.state)
        selected_position = parse_classic_reply_answer_number("1", len(context["options"]))
        self.assertEqual(0, selected_position)

        selected_option_index = int(context["options"][selected_position]["option_index"])
        result = _handle_classic_text_answer_db(
            self.settings,
            self.tg_user,
            session_id=self.session_id,
            question_id=1,
            selected_option_index=selected_option_index,
        )
        self.assertEqual("accepted", result["status"])
        self.assertTrue(result["is_correct"])
        self.assertFalse(result["is_last_question"])

    def test_invalid_answer_number_is_rejected_before_db_submission(self):
        self.assertIsNone(parse_classic_reply_answer_number("5", 2))
        self.assertIsNone(parse_classic_reply_answer_number("not a number", 2))

    def test_next_text_handling_requires_awaiting_next_state(self):
        next_state = _load_classic_text_next_state(
            self.settings,
            self.tg_user,
            {"status": "awaiting_next", "session_id": self.session_id},
        )
        self.assertEqual("ok", next_state["status"])
        self.assertEqual(CLASSIC_REPLY_NEXT_TEXT, "Далее")

        answer_state = _load_classic_text_next_state(self.settings, self.tg_user, self.state)
        self.assertEqual("not_awaiting_next", answer_state["status"])


if __name__ == "__main__":
    unittest.main()
