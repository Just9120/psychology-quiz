import os
import sqlite3
import tempfile
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.db import create_or_load_user, start_quiz_session, store_session_questions
from app.main import (
    CLASSIC_REPLY_NEXT_TEXT,
    CLASSIC_REPLY_STATE_KEY,
    _classic_text_latency_bucket,
    _handle_classic_text_answer_db,
    _load_classic_text_answer_context,
    _load_classic_text_next_state,
    _safe_classic_text_log_fields,
    build_classic_answer_reply_keyboard,
    build_classic_reply_feedback_text,
    build_question_text_with_options,
    build_quiz_finished_text,
    classic_reply_text_answer_handler,
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


    def test_first_question_hint_is_only_rendered_when_requested(self):
        options = [{"option_index": 0, "option_text": "Alpha"}, {"option_index": 1, "option_text": "Beta"}]

        first_text = build_question_text_with_options(
            1,
            2,
            "Question",
            options,
            "normal",
            numeric_labels=True,
            show_answer_keyboard_hint=True,
        )
        next_text = build_question_text_with_options(
            2,
            2,
            "Question",
            options,
            "normal",
            numeric_labels=True,
            show_answer_keyboard_hint=False,
        )

        self.assertIn("1. Alpha", first_text)
        self.assertIn("Ответьте кнопкой с номером варианта внизу 👇", first_text)
        self.assertNotIn("Ответьте кнопкой с номером варианта внизу 👇", next_text)

    def test_classic_text_answer_db_returns_feedback_option_details_for_correct_answer(self):
        result = _handle_classic_text_answer_db(
            self.settings,
            self.tg_user,
            session_id=self.session_id,
            question_id=1,
            selected_option_index=0,
        )

        self.assertEqual("accepted", result["status"])
        self.assertTrue(result["is_correct"])
        self.assertEqual("1", result["selected_option_label"])
        self.assertEqual("A", result["selected_option_text"])
        self.assertEqual("1", result["correct_option_label"])
        self.assertEqual("A", result["correct_option_text"])

        feedback = build_classic_reply_feedback_text(result)
        self.assertIn("Верно ✅", feedback)
        self.assertIn("<b>Ваш ответ:</b> 1 — A", feedback)
        self.assertIn("<b>Пояснение:</b>", feedback)
        self.assertIn("E1", feedback)
        self.assertIn("<b>Прогресс:</b> 1 из 2", feedback)
        self.assertNotIn("Правильный ответ", feedback)

    def test_classic_text_answer_db_returns_feedback_option_details_for_wrong_answer(self):
        result = _handle_classic_text_answer_db(
            self.settings,
            self.tg_user,
            session_id=self.session_id,
            question_id=1,
            selected_option_index=1,
        )

        self.assertEqual("accepted", result["status"])
        self.assertFalse(result["is_correct"])
        self.assertEqual("2", result["selected_option_label"])
        self.assertEqual("B", result["selected_option_text"])
        self.assertEqual("1", result["correct_option_label"])
        self.assertEqual("A", result["correct_option_text"])

        feedback = build_classic_reply_feedback_text(result)
        self.assertIn("Неверно ❌", feedback)
        self.assertIn("<b>Ваш ответ:</b> 2 — B", feedback)
        self.assertIn("<b>Правильный ответ:</b> 1 — A", feedback)
        self.assertIn("<b>Пояснение:</b>", feedback)
        self.assertIn("<b>Прогресс:</b> 1 из 2", feedback)

    def test_last_answer_feedback_details_and_neutral_final_text(self):
        first = _handle_classic_text_answer_db(
            self.settings, self.tg_user, session_id=self.session_id, question_id=1, selected_option_index=0
        )
        self.assertFalse(first["is_last_question"])

        self.state = {"status": "awaiting_answer", "session_id": self.session_id, "question_id": 2}
        result = _handle_classic_text_answer_db(
            self.settings, self.tg_user, session_id=self.session_id, question_id=2, selected_option_index=0
        )
        self.assertTrue(result["is_last_question"])
        feedback = build_classic_reply_feedback_text(result)
        final_text = build_quiz_finished_text(int(result["finalized"]["score"]), int(result["finalized"]["total_questions"]))
        combined = f"{feedback}\n\n{final_text}"

        self.assertIn("<b>Ваш ответ:</b> 1 — C", combined)
        self.assertIn("<b>Правильный ответ:</b> 2 — D", combined)
        self.assertIn("Викторина завершена 🎉", combined)
        self.assertIn("<b>Результат:</b> 1 из 2", combined)
        self.assertIn("🎯 Начать", combined)
        self.assertIn("/quiz", combined)
        for phrase in ("тема требует повторения", "база уже есть", "тема хорошо усвоена"):
            self.assertNotIn(phrase, combined)

    def test_bionic_rendering_applies_to_feedback_option_text_and_explanation(self):
        result = {
            "is_correct": False,
            "selected_option_label": "1",
            "selected_option_text": "Неверный вариант",
            "correct_option_label": "2",
            "correct_option_text": "Правильный ответ",
            "explanation": "Подробное пояснение",
            "answered_questions": 1,
            "total_questions": 2,
            "reading_mode": "bionic",
        }

        feedback = build_classic_reply_feedback_text(result)

        self.assertIn("<b>Не</b>верный", feedback)
        self.assertIn("<b>Пра</b>вильный", feedback)
        self.assertIn("<b>По</b>дробное", feedback)

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


    def test_classic_reply_text_answer_handler_sends_correct_feedback_with_next_keyboard(self):
        context = SimpleNamespace(
            application=SimpleNamespace(bot_data={"settings": self.settings}),
            user_data={CLASSIC_REPLY_STATE_KEY: self.state},
        )
        message = SimpleNamespace(text="1", reply_text=AsyncMock(), chat=SimpleNamespace(type="private"))
        update = SimpleNamespace(message=message, effective_user=self.tg_user)
        context_result = {
            "status": "ok",
            "session_id": self.session_id,
            "question_id": 1,
            "options": [{"option_index": 0, "option_text": "A"}, {"option_index": 1, "option_text": "B"}],
        }
        answer_result = {
            "status": "accepted",
            "is_correct": True,
            "selected_option_label": "1",
            "selected_option_text": "A",
            "correct_option_label": "1",
            "correct_option_text": "A",
            "explanation": "E1",
            "answered_questions": 1,
            "total_questions": 2,
            "reading_mode": "normal",
            "is_last_question": False,
            "finalized": None,
        }

        async def fake_run_db_task(func, *args, **kwargs):
            del func, args, kwargs
            return context_result if fake_run_db_task.calls == 0 else answer_result
        fake_run_db_task.calls = 0

        async def counting_run_db_task(func, *args, **kwargs):
            result = await fake_run_db_task(func, *args, **kwargs)
            fake_run_db_task.calls += 1
            return result

        with patch("app.main._run_db_task", side_effect=counting_run_db_task):
            asyncio.run(classic_reply_text_answer_handler(update, context))

        sent_text = message.reply_text.call_args.args[0]
        sent_markup = message.reply_text.call_args.kwargs["reply_markup"]
        self.assertIn("Верно ✅", sent_text)
        self.assertIn("<b>Ваш ответ:</b> 1 — A", sent_text)
        self.assertIn("<b>Пояснение:</b>", sent_text)
        self.assertIn("<b>Прогресс:</b> 1 из 2", sent_text)
        self.assertNotIn("Правильный ответ", sent_text)
        self.assertEqual(CLASSIC_REPLY_NEXT_TEXT, sent_markup.keyboard[0][0].text)

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
