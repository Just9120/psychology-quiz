import random
import unittest
from unittest.mock import patch

from app.glossary import (
    build_glossary_answer_keyboard,
    build_glossary_count_keyboard,
    build_glossary_quiz_question,
    callback_token_to_topic_id,
    format_glossary_feedback_text,
    format_glossary_question_text,
    format_glossary_result_text,
    load_glossary_entries,
)
from app.main import GLOSSARY_BUTTON_TEXT, HELP_TEXT, get_main_menu_keyboard


TOPIC_ID = "kachestvennye_metody_issledovaniya"


class GlossaryRuntimeTests(unittest.TestCase):
    def test_static_glossary_loads_from_json(self):
        entries = load_glossary_entries(TOPIC_ID)

        self.assertIsNotNone(entries)
        self.assertGreaterEqual(len(entries), 14)
        self.assertEqual(TOPIC_ID, entries[0].topic_id)
        self.assertTrue(entries[0].term)

    def test_main_menu_and_help_expose_glossary_quiz(self):
        keyboard = get_main_menu_keyboard()
        labels = [button.text for row in keyboard.keyboard for button in row]

        self.assertIn(GLOSSARY_BUTTON_TEXT, labels)
        self.assertIn("/glossary — открыть глоссарий-тест", HELP_TEXT)
        self.assertIn("пройти тест по терминам", HELP_TEXT)

    def test_quiz_question_builds_four_options_with_correct_and_distractors(self):
        entries = load_glossary_entries(TOPIC_ID)
        question = build_glossary_quiz_question(entries, entries[2], rng=random.Random(1))

        self.assertIsNotNone(question)
        self.assertEqual(4, len(question.options))
        self.assertIn(entries[2].short_definition, question.options)
        self.assertEqual(entries[2].short_definition, question.options[question.correct_option_index])
        distractors = [option for index, option in enumerate(question.options) if index != question.correct_option_index]
        other_definitions = {entry.short_definition for entry in entries if entry.id != entries[2].id}
        self.assertTrue(all(distractor in other_definitions for distractor in distractors))

    def test_callback_data_stays_compact(self):
        entries = load_glossary_entries(TOPIC_ID)
        question = build_glossary_quiz_question(entries, entries[0], rng=random.Random(2))
        callbacks = [button.callback_data for row in build_glossary_answer_keyboard(question).inline_keyboard for button in row]
        callbacks += [button.callback_data for row in build_glossary_count_keyboard(TOPIC_ID, len(entries)).inline_keyboard for button in row]

        self.assertIn("glsq:count:kmi:5", callbacks)
        self.assertIn("glsq:count:kmi:10", callbacks)
        self.assertIn("glsq:count:kmi:all", callbacks)
        self.assertIn("gls:topics", callbacks)
        self.assertTrue(all(len(callback) <= 64 for callback in callbacks))

    def test_rendered_question_and_feedback_hide_internal_provenance(self):
        entries = load_glossary_entries(TOPIC_ID)
        entry = entries[2]
        self.assertTrue(any("supplied_snippet" in ref for ref in entry.source_refs))
        question = build_glossary_quiz_question(entries, entry, rng=random.Random(3))

        question_text = format_glossary_question_text(question, 1, 5)
        feedback_text = format_glossary_feedback_text(question, question.correct_option_index, 1, 5)
        rendered = f"{question_text}\n{feedback_text}"

        self.assertIn("Вопрос 1 из 5", rendered)
        self.assertIn("Верно ✅", rendered)
        self.assertIn("Краткое объяснение", rendered)
        self.assertNotIn("source_refs", rendered)
        self.assertNotIn("supplied_snippet", rendered)
        self.assertNotIn(entry.id, rendered)

    def test_final_result_text_includes_score(self):
        text = format_glossary_result_text(3, 5)

        self.assertIn("Тест завершён", text)
        self.assertIn("Результат:</b> 3 из 5", text)

    def test_loader_handles_missing_or_malformed_without_db_access(self):
        with patch("app.glossary.get_connection", side_effect=AssertionError("DB should not be used"), create=True):
            entries = load_glossary_entries(TOPIC_ID)

        self.assertIsNotNone(entries)
        self.assertEqual(TOPIC_ID, callback_token_to_topic_id("kmi"))


if __name__ == "__main__":
    unittest.main()
