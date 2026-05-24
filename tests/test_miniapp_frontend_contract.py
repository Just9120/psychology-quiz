import unittest
from pathlib import Path


class MiniAppFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Path('miniapp/index.html').read_text(encoding='utf-8')

    def test_diagnostics_hidden_by_default(self):
        self.assertIn('id="api_diag" class="note" hidden', self.content)
        self.assertIn('if (!debugMode) {', self.content)

    def test_debug_mode_query_flag_supported(self):
        self.assertIn("getQueryParam('debug') === '1'", self.content)

    def test_completed_view_has_next_actions(self):
        self.assertIn("restart.textContent = 'Новая викторина'", self.content)
        self.assertIn("closeBtn.textContent = 'Закрыть Mini App'", self.content)
        self.assertNotIn('location.reload();', self.content)
        self.assertIn('Чтобы начать новую викторину, закройте Mini App и отправьте /ui заново.', self.content)

    def test_setup_prefers_api_and_no_close_on_api_path(self):
        self.assertIn("/miniapp/setup", self.content)
        self.assertNotIn("tg.close();", self.content)

    def test_timeout_and_feedback_ui_contract(self):
        self.assertIn("AbortController", self.content)
        self.assertIn("Таймаут API. Используется резервный режим.", self.content)
        self.assertIn("feedback-correct", self.content)
        self.assertIn("feedback-wrong", self.content)
        self.assertIn("next.textContent = 'Далее'", self.content)


if __name__ == '__main__':
    unittest.main()
