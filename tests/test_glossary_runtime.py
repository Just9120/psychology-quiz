import json
import random
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from app.glossary import (
    GLOSSARY_TOPICS,
    GLOSSARY_TOPIC_CALLBACK_TOKENS,
    GlossaryEntry,
    build_glossary_answer_keyboard,
    build_glossary_count_keyboard,
    build_glossary_feedback_keyboard,
    build_glossary_quiz_question,
    build_glossary_topics_keyboard,
    callback_token_to_topic_id,
    format_glossary_feedback_text,
    format_glossary_question_text,
    format_glossary_result_text,
    load_glossary_entries,
)
from app.glossary_handlers import (
    glossary_button_handler,
    glossary_callback,
    glossary_command,
    glossary_reply_text_answer_handler,
    glossary_reply_text_next_handler,
    parse_glossary_reply_answer_number,
)
from app.main import GLOSSARY_BUTTON_TEXT, HELP_TEXT, get_main_menu_keyboard


TOPIC_ID = "kachestvennye_metody_issledovaniya"
EXP_TOPIC_ID = "osnovy_eksperimentalnoy_psihologii"
INTERNAL_MARKERS = ("source_refs", "supplied_snippet", "question:m2_exp", "exp_psych_")


def normalize_glossary_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())



def make_glossary_entry(entry_id: str, short_definition: str, confusable_with: tuple[str, ...] = (), topic_id: str = "fixture_topic") -> GlossaryEntry:
    return GlossaryEntry(
        id=entry_id,
        topic_id=topic_id,
        term=f"Term {entry_id}",
        aliases=(),
        short_definition=short_definition,
        definition=f"Definition {entry_id}",
        examples=(f"Example {entry_id}",),
        difficulty="basic",
        source_refs=("supplied_snippet:test",),
        confusable_with=confusable_with,
    )


def question_distractor_entry_ids(question, entries):
    by_definition = {normalize_glossary_text(entry.short_definition): entry.id for entry in entries}
    return {
        by_definition[normalize_glossary_text(option)]
        for index, option in enumerate(question.options)
        if index != question.correct_option_index
    }

def load_active_question_topics():
    topics = json.loads(Path("content/topics.json").read_text(encoding="utf-8"))
    return [
        topic
        for topic in topics
        if topic.get("status") == "active" and "questions" in topic.get("available_contours", [])
    ]


def load_approved_questions_by_id(active_topics):
    questions = {}
    for topic in active_topics:
        for question in json.loads(Path(topic["question_file"]).read_text(encoding="utf-8")):
            if question.get("status") == "approved":
                questions[question["id"]] = {
                    "topic_id": topic["id"],
                    "category": question.get("category"),
                }
    return questions


class GlossaryRuntimeTests(unittest.TestCase):
    def test_static_glossary_topics_load_from_json(self):
        entries = load_glossary_entries(TOPIC_ID)
        exp_entries = load_glossary_entries(EXP_TOPIC_ID)

        self.assertIsNotNone(entries)
        self.assertGreaterEqual(len(entries), 14)
        self.assertEqual(TOPIC_ID, entries[0].topic_id)
        self.assertTrue(entries[0].term)
        self.assertIsNotNone(exp_entries)
        self.assertEqual(10, len(exp_entries))
        self.assertTrue(all(entry.id.startswith("exp_psych_") for entry in exp_entries))
        self.assertTrue(all(entry.source_refs for entry in exp_entries))
        self.assertTrue(all(isinstance(entry.confusable_with, tuple) for entry in exp_entries))
        self.assertTrue(any(entry.confusable_with for entry in exp_entries))

    def test_both_topics_appear_and_new_token_maps(self):
        topic_ids = [topic_id for topic_id, _title in GLOSSARY_TOPICS]
        topic_titles = [title for _topic_id, title in GLOSSARY_TOPICS]
        callbacks = [button.callback_data for row in build_glossary_topics_keyboard().inline_keyboard for button in row]

        self.assertIn(TOPIC_ID, topic_ids)
        self.assertIn(EXP_TOPIC_ID, topic_ids)
        self.assertIn("Качественные методы исследования", topic_titles)
        self.assertIn("Основы экспериментальной психологии", topic_titles)
        self.assertIn("gls:topic:kmi", callbacks)
        self.assertIn("gls:topic:oep", callbacks)
        self.assertEqual(EXP_TOPIC_ID, callback_token_to_topic_id("oep"))
        self.assertTrue(all(len(callback) <= 64 for callback in callbacks))

    def test_main_menu_and_help_expose_glossary_quiz(self):
        keyboard = get_main_menu_keyboard()
        labels = [button.text for row in keyboard.keyboard for button in row]

        self.assertIn(GLOSSARY_BUTTON_TEXT, labels)
        self.assertIn("/glossary — открыть глоссарий-тест", HELP_TEXT)
        self.assertIn("пройти тест по терминам", HELP_TEXT)

    def test_quiz_question_builds_four_options_with_correct_and_distractors(self):
        entries = load_glossary_entries(EXP_TOPIC_ID)
        question = build_glossary_quiz_question(entries, entries[2], rng=random.Random(1))

        self.assertIsNotNone(question)
        self.assertEqual(4, len(question.options))
        self.assertIn(entries[2].short_definition, question.options)
        self.assertEqual(entries[2].short_definition, question.options[question.correct_option_index])
        distractors = [option for index, option in enumerate(question.options) if index != question.correct_option_index]
        other_definitions = {entry.short_definition for entry in entries if entry.id != entries[2].id}
        self.assertTrue(all(distractor in other_definitions for distractor in distractors))

    def test_callback_data_stays_compact(self):
        entries = load_glossary_entries(EXP_TOPIC_ID)
        callbacks = [button.callback_data for row in build_glossary_count_keyboard(EXP_TOPIC_ID, len(entries)).inline_keyboard for button in row]

        self.assertIn("glsq:count:oep:5", callbacks)
        self.assertIn("glsq:count:oep:10", callbacks)
        self.assertIn("glsq:count:oep:all", callbacks)
        self.assertIn("gls:topics", callbacks)
        self.assertTrue(all(len(callback) <= 64 for callback in callbacks))

    def test_question_uses_numbered_message_and_reply_keyboard(self):
        entries = load_glossary_entries(EXP_TOPIC_ID)
        question = build_glossary_quiz_question(entries, entries[0], rng=random.Random(2))

        question_text = format_glossary_question_text(question, 1, 5)
        keyboard = build_glossary_answer_keyboard(question)
        labels = [button.text for row in keyboard.keyboard for button in row]

        self.assertIn("Вопрос 1 из 5", question_text)
        self.assertIn("Ответьте кнопкой с номером варианта внизу", question_text)
        for number in range(1, 5):
            self.assertIn(f"{number}. ", question_text)
        self.assertEqual(["1", "2", "3", "4"], labels)
        self.assertFalse(hasattr(keyboard, "inline_keyboard"))

    def test_feedback_numbers_next_keyboard_and_result(self):
        entries = load_glossary_entries(EXP_TOPIC_ID)
        question = build_glossary_quiz_question(entries, entries[1], rng=random.Random(3))
        selected = 0 if question.correct_option_index != 0 else 1

        feedback_text = format_glossary_feedback_text(question, selected, 1, 5)
        next_keyboard = build_glossary_feedback_keyboard(has_next=True)
        result_text = format_glossary_result_text(3, 5)
        next_labels = [button.text for row in next_keyboard.keyboard for button in row]

        self.assertIn(f"Ваш ответ:</b> {selected + 1} —", feedback_text)
        self.assertIn(f"Правильный ответ:</b> {question.correct_option_index + 1} —", feedback_text)
        self.assertEqual(["Далее"], next_labels)
        self.assertIn("Тест завершён", result_text)
        self.assertIn("Результат:</b> 3 из 5", result_text)

    def test_rendered_question_feedback_result_hide_internal_provenance(self):
        entries = load_glossary_entries(EXP_TOPIC_ID)
        entry = entries[8]
        self.assertIn("question:m2_exp_022", entry.source_refs)
        question = build_glossary_quiz_question(entries, entry, rng=random.Random(4))

        rendered = "\n".join(
            [
                format_glossary_question_text(question, 1, 5),
                format_glossary_feedback_text(question, question.correct_option_index, 1, 5),
                format_glossary_result_text(1, 5),
            ]
        )

        for marker in INTERNAL_MARKERS:
            self.assertNotIn(marker, rendered)


    def test_glossary_handlers_are_importable_from_extracted_module(self):
        self.assertTrue(callable(glossary_command))
        self.assertTrue(callable(glossary_button_handler))
        self.assertTrue(callable(glossary_callback))
        self.assertTrue(callable(glossary_reply_text_answer_handler))
        self.assertTrue(callable(glossary_reply_text_next_handler))

    def test_main_registers_imported_glossary_handlers_with_same_patterns(self):
        import inspect
        import app.main as main

        source = inspect.getsource(main.main)

        self.assertIn('CommandHandler("glossary", glossary_command)', source)
        self.assertIn('filters.Regex(build_menu_button_regex(*GLOSSARY_BUTTON_ALIASES))', source)
        self.assertIn('glossary_button_handler', source)
        self.assertIn('glossary_reply_text_answer_handler,', source)
        self.assertIn('glossary_reply_text_next_handler,', source)
        self.assertGreaterEqual(source.count('group=1'), 2)
        self.assertIn("CallbackQueryHandler(\n            glossary_callback,", source)
        self.assertIn(r'pattern=r"^(gls:(topics|main|topic:[a-z0-9_]+)|glsq:(count:[a-z0-9_]+:(5|10|all)|retry))$"', source)

    def test_invalid_glossary_reply_numbers_are_rejected(self):
        self.assertIsNone(parse_glossary_reply_answer_number("", 4))
        self.assertIsNone(parse_glossary_reply_answer_number("abc", 4))
        self.assertIsNone(parse_glossary_reply_answer_number("0", 4))
        self.assertIsNone(parse_glossary_reply_answer_number("5", 4))
        self.assertEqual(0, parse_glossary_reply_answer_number("1", 4))
        self.assertEqual(3, parse_glossary_reply_answer_number(" 4 ", 4))

    def test_loader_handles_missing_or_malformed_without_db_access(self):
        with patch("app.glossary.get_connection", side_effect=AssertionError("DB should not be used"), create=True):
            entries = load_glossary_entries(EXP_TOPIC_ID)

        self.assertIsNotNone(entries)
        self.assertEqual(TOPIC_ID, callback_token_to_topic_id("kmi"))

    def test_loader_rejects_malformed_confusable_metadata(self):
        raw_entries = json.loads(Path(f"content/glossary/{EXP_TOPIC_ID}.json").read_text(encoding="utf-8"))
        raw_entries[0]["confusable_with"] = "not-a-list"

        with patch("app.glossary.Path.read_text", return_value=json.dumps(raw_entries, ensure_ascii=False)):
            self.assertIsNone(load_glossary_entries(EXP_TOPIC_ID))

    def test_direct_confusables_fill_all_distractor_slots(self):
        entries = [
            make_glossary_entry("target", "correct", ("a", "b", "c")),
            make_glossary_entry("a", "direct a"),
            make_glossary_entry("b", "direct b"),
            make_glossary_entry("c", "direct c"),
            make_glossary_entry("d", "fallback d"),
        ]

        question = build_glossary_quiz_question(entries, entries[0], rng=random.Random(10))

        self.assertEqual({"a", "b", "c"}, question_distractor_entry_ids(question, entries))

    def test_partial_direct_confusables_use_ranked_fallback(self):
        entries = [
            make_glossary_entry("target", "correct", ("a",)),
            make_glossary_entry("a", "direct a"),
            make_glossary_entry("b", "reciprocal b", ("target",)),
            make_glossary_entry("c", "fallback c"),
            make_glossary_entry("d", "fallback d"),
        ]

        question = build_glossary_quiz_question(entries, entries[0], rng=random.Random(11))
        distractor_ids = question_distractor_entry_ids(question, entries)

        self.assertIn("a", distractor_ids)
        self.assertIn("b", distractor_ids)
        self.assertEqual(3, len(distractor_ids))

    def test_reciprocal_confusables_are_preferred_over_unrelated_fallback(self):
        entries = [
            make_glossary_entry("target", "correct"),
            make_glossary_entry("a", "reciprocal a", ("target",)),
            make_glossary_entry("b", "reciprocal b", ("target",)),
            make_glossary_entry("c", "reciprocal c", ("target",)),
            make_glossary_entry("d", "fallback d"),
        ]

        question = build_glossary_quiz_question(entries, entries[0], rng=random.Random(12))

        self.assertEqual({"a", "b", "c"}, question_distractor_entry_ids(question, entries))

    def test_no_confusables_falls_back_to_same_topic_options(self):
        entries = [
            make_glossary_entry("target", "correct"),
            make_glossary_entry("a", "fallback a"),
            make_glossary_entry("b", "fallback b"),
            make_glossary_entry("c", "fallback c"),
        ]

        question = build_glossary_quiz_question(entries, entries[0], rng=random.Random(13))

        self.assertIsNotNone(question)
        self.assertEqual(4, len(question.options))
        self.assertEqual({"a", "b", "c"}, question_distractor_entry_ids(question, entries))

    def test_duplicate_or_empty_option_texts_return_none_instead_of_short_question(self):
        entries = [
            make_glossary_entry("target", "correct", ("a", "b", "c")),
            make_glossary_entry("a", "duplicate"),
            make_glossary_entry("b", " Duplicate "),
            make_glossary_entry("c", ""),
            make_glossary_entry("d", "fallback d"),
        ]

        self.assertIsNone(build_glossary_quiz_question(entries, entries[0], rng=random.Random(14)))

    def test_glossary_registry_matches_active_question_topics_contract(self):
        active_topics = load_active_question_topics()
        active_question_topics = [(topic["id"], topic["title"]) for topic in active_topics]
        active_topic_ids = {topic_id for topic_id, _title in active_question_topics}

        self.assertEqual(active_question_topics, list(GLOSSARY_TOPICS))
        self.assertTrue(active_question_topics)
        self.assertTrue(all("glossary" in topic.get("available_contours", []) for topic in active_topics))
        callback_topic_ids = list(GLOSSARY_TOPIC_CALLBACK_TOKENS.values())
        self.assertEqual(len(GLOSSARY_TOPIC_CALLBACK_TOKENS), len(set(GLOSSARY_TOPIC_CALLBACK_TOKENS)))
        self.assertEqual(len(callback_topic_ids), len(set(callback_topic_ids)))
        self.assertEqual(active_topic_ids, set(callback_topic_ids))

    def test_all_active_glossary_topics_load_have_valid_entries_and_questions(self):
        for topic_id, _title in GLOSSARY_TOPICS:
            entries = load_glossary_entries(topic_id)
            self.assertIsNotNone(entries, topic_id)
            self.assertGreaterEqual(len(entries), 10, topic_id)
            for entry in entries:
                self.assertTrue(entry.id)
                self.assertEqual(topic_id, entry.topic_id)
                self.assertTrue(entry.term)
                self.assertTrue(entry.short_definition)
                self.assertTrue(entry.definition)
                self.assertTrue(entry.examples)
                self.assertTrue(entry.source_refs)
                self.assertTrue(entry.difficulty)
                question = build_glossary_quiz_question(entries, entry, rng=random.Random(5))
                self.assertIsNotNone(question, entry.id)
                self.assertEqual(4, len(question.options))

    def test_glossary_source_refs_use_supported_formats_and_question_refs_resolve(self):
        active_topics = load_active_question_topics()
        topic_titles = {topic["id"]: topic["title"] for topic in active_topics}
        approved_questions = load_approved_questions_by_id(active_topics)

        for topic_id, _title in GLOSSARY_TOPICS:
            raw_entries = json.loads(Path(f"content/glossary/{topic_id}.json").read_text(encoding="utf-8"))
            valid_ids = {entry["id"] for entry in raw_entries}
            self.assertEqual(len(valid_ids), len(raw_entries), topic_id)
            normalized_terms = [normalize_glossary_text(item["term"]) for item in raw_entries]
            normalized_short_definitions = [normalize_glossary_text(item["short_definition"]) for item in raw_entries]
            self.assertEqual(len(normalized_terms), len(set(normalized_terms)), topic_id)
            self.assertEqual(len(normalized_short_definitions), len(set(normalized_short_definitions)), topic_id)

            for item in raw_entries:
                for field in ("id", "topic_id", "term", "short_definition", "definition", "difficulty", "status"):
                    self.assertTrue(item.get(field), (topic_id, item.get("id"), field))
                for field in ("aliases", "examples", "confusable_with", "source_refs"):
                    self.assertIsInstance(item.get(field), list, (topic_id, item.get("id"), field))
                self.assertTrue(item["examples"], (topic_id, item["id"]))
                self.assertEqual("approved", item["status"])
                for source_ref in item["source_refs"]:
                    self.assertTrue(source_ref.startswith(("question:", "supplied_snippet:")), source_ref)
                    if source_ref.startswith("question:"):
                        question_id = source_ref.removeprefix("question:")
                        self.assertIn(question_id, approved_questions)
                        self.assertEqual(topic_id, approved_questions[question_id]["topic_id"], (topic_id, item["id"], question_id))
                        self.assertEqual(topic_titles[topic_id], approved_questions[question_id]["category"], (topic_id, item["id"], question_id))
                self.assertNotIn(item["id"], item["confusable_with"], (topic_id, item["id"]))
                self.assertTrue(set(item["confusable_with"]).issubset(valid_ids), (topic_id, item["id"]))

    def test_miniapp_glossary_payload_exposes_all_active_topics(self):
        from app.miniapp_glossary import list_glossary_topics_payload

        payload = list_glossary_topics_payload()
        self.assertEqual([5, 10, "all"], payload["question_count_choices"])
        self.assertEqual(len(GLOSSARY_TOPICS), len(payload["topics"]))
        self.assertEqual([topic_id for topic_id, _title in GLOSSARY_TOPICS], [topic["topic_id"] for topic in payload["topics"]])
        self.assertTrue(all(topic["available_count"] >= 10 for topic in payload["topics"]))
        for topic in payload["topics"]:
            self.assertEqual({"topic_id", "title", "available_count"}, set(topic))

    def test_every_glossary_topic_generates_ranked_same_topic_unique_questions(self):
        for topic_id, _title in GLOSSARY_TOPICS:
            entries = load_glossary_entries(topic_id)
            entries_by_id = {entry.id: entry for entry in entries}
            entry_id_by_definition = {normalize_glossary_text(entry.short_definition): entry.id for entry in entries}
            for index, entry in enumerate(entries):
                question = build_glossary_quiz_question(entries, entry, rng=random.Random(index))
                self.assertIsNotNone(question, (topic_id, entry.id))
                self.assertEqual(4, len(question.options), (topic_id, entry.id))
                normalized_options = [normalize_glossary_text(option) for option in question.options]
                self.assertTrue(all(normalized_options), (topic_id, entry.id))
                self.assertEqual(4, len(set(normalized_options)), (topic_id, entry.id))
                self.assertEqual(1, normalized_options.count(normalize_glossary_text(entry.short_definition)), (topic_id, entry.id))

                distractor_ids = {
                    entry_id_by_definition[normalized_option]
                    for option_index, normalized_option in enumerate(normalized_options)
                    if option_index != question.correct_option_index
                }
                self.assertEqual(3, len(distractor_ids), (topic_id, entry.id))
                self.assertNotIn(entry.id, distractor_ids, (topic_id, entry.id))
                self.assertTrue(all(entries_by_id[distractor_id].topic_id == topic_id for distractor_id in distractor_ids), (topic_id, entry.id))

                direct_confusables = [
                    entries_by_id[confusable_id].id
                    for confusable_id in entry.confusable_with
                    if confusable_id in entries_by_id
                    and confusable_id != entry.id
                    and normalize_glossary_text(entries_by_id[confusable_id].short_definition) not in {normalize_glossary_text(entry.short_definition)}
                ]
                if len(set(direct_confusables)) <= 3:
                    self.assertTrue(set(direct_confusables).issubset(distractor_ids), (topic_id, entry.id, direct_confusables, distractor_ids))


if __name__ == "__main__":
    unittest.main()
