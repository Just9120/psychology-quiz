import unittest

from app.glossary import (
    GLOSSARY_PAGE_SIZE,
    build_glossary_entry_keyboard,
    build_glossary_terms_keyboard,
    find_glossary_entry,
    format_glossary_entry_text,
    format_glossary_terms_text,
    load_glossary_entries,
)
from app.main import GLOSSARY_BUTTON_TEXT, HELP_TEXT, get_main_menu_keyboard


class GlossaryRuntimeTests(unittest.TestCase):
    def test_static_glossary_loads_from_json(self):
        entries = load_glossary_entries("kachestvennye_metody_issledovaniya")

        self.assertIsNotNone(entries)
        self.assertGreaterEqual(len(entries), 14)
        self.assertEqual("kachestvennye_metody_issledovaniya", entries[0].topic_id)
        self.assertTrue(entries[0].term)

    def test_terms_keyboard_paginates_with_compact_callbacks(self):
        entries = load_glossary_entries("kachestvennye_metody_issledovaniya")
        markup = build_glossary_terms_keyboard("kachestvennye_metody_issledovaniya", entries, 0)

        term_rows = markup.inline_keyboard[:GLOSSARY_PAGE_SIZE]
        self.assertEqual(GLOSSARY_PAGE_SIZE, len(term_rows))
        self.assertTrue(all(row[0].callback_data.startswith("gls:term:kmi:") for row in term_rows))
        rendered_callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertIn("gls:topic:kmi:1", rendered_callbacks)
        self.assertIn("gls:topics", rendered_callbacks)
        self.assertTrue(all(len(callback) <= 64 for callback in rendered_callbacks))

    def test_entry_format_escapes_html_content(self):
        entries = load_glossary_entries("kachestvennye_metody_issledovaniya")
        entry = find_glossary_entry(entries, "qual_methods_focus_group")

        text = format_glossary_entry_text(entry)

        self.assertIn("<b>Фокус-группа</b>", text)
        self.assertIn("<b>Кратко:</b>", text)
        self.assertIn("<b>Определение:</b>", text)
        self.assertIn("<b>Примеры:</b>", text)
        self.assertIn("<b>Источники:</b>", text)
        self.assertNotIn("<script", text)

    def test_main_menu_and_help_expose_glossary(self):
        keyboard = get_main_menu_keyboard()
        labels = [button.text for row in keyboard.keyboard for button in row]

        self.assertIn(GLOSSARY_BUTTON_TEXT, labels)
        self.assertIn("/glossary — открыть глоссарий", HELP_TEXT)

    def test_entry_keyboard_has_back_buttons(self):
        callbacks = [button.callback_data for row in build_glossary_entry_keyboard("kachestvennye_metody_issledovaniya", 1).inline_keyboard for button in row]

        self.assertEqual(
            ["gls:topic:kmi:1", "gls:topics", "gls:main"],
            callbacks,
        )

    def test_terms_text_reports_page(self):
        text = format_glossary_terms_text("Качественные методы исследования", 0, 14)

        self.assertIn("Страница 1 из 3", text)


if __name__ == "__main__":
    unittest.main()
