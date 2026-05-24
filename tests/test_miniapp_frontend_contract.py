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
        self.assertIn('function getSafeSetupUrl()', self.content)
        self.assertIn('new URL(ctx.setup_url, location.origin)', self.content)
        self.assertIn("setupUrl.pathname === '/'", self.content)
        self.assertIn("setSetupStatus('ready_for_submit')", self.content)
        self.assertNotIn("ctx.setup_url.includes('api_base_url=')", self.content)
        self.assertIn('const safeSetupUrl = getSafeSetupUrl();', self.content)
        self.assertIn('if (safeSetupUrl) {', self.content)
        self.assertIn("await apiFetch(`${apiBase}/miniapp/setup-options`", self.content)
        self.assertIn("if (apiBase && tg?.initData) {", self.content)
        self.assertIn("setupOptionsCache.categories = categories;", self.content)
        self.assertIn("ctx.categories = categories;", self.content)
        self.assertIn('Чтобы начать новую викторину, закройте Mini App и отправьте /ui заново.', self.content)

    def test_setup_prefers_api_and_no_close_on_api_path(self):
        self.assertIn("/miniapp/setup", self.content)
        self.assertIn("if (apiBase && tg?.initData) {", self.content)
        self.assertIn("setSetupStatus('api_attempted')", self.content)
        self.assertIn("setSetupStatus('api_success')", self.content)
        self.assertIn('form.hidden = true;', self.content)
        self.assertIn('setupWarning.hidden = true;', self.content)
        self.assertIn("setSetupStatus('api_failed'", self.content)
        self.assertIn("if (go.disabled || setupSubmitInFlight) return;", self.content)
        self.assertIn("setupSubmitInFlight = true;", self.content)
        self.assertIn("setupSubmitInFlight = false;", self.content)
        self.assertIn("return;\n        }\n        if (!tg?.sendData)", self.content)
        self.assertNotIn("tg.close();", self.content)

    def test_ui_mode_helpers_prevent_mixed_dom(self):
        self.assertIn('function showSetupMode(', self.content)
        self.assertIn('function showRunnerMode()', self.content)
        self.assertIn('function showCompletedMode()', self.content)
        self.assertIn('function clearRunnerView()', self.content)
        self.assertIn('showSetupMode();', self.content)
        self.assertIn('showRunnerMode();', self.content)
        self.assertIn('showCompletedMode();', self.content)

    def test_timeout_and_feedback_ui_contract(self):
        self.assertIn("AbortController", self.content)
        self.assertIn("Не удалось отправить ответ через API. Попробуйте снова.", self.content)
        self.assertIn("Не удалось запустить викторину через API. Попробуйте снова.", self.content)
        self.assertIn("feedback-correct", self.content)
        self.assertIn("feedback-wrong", self.content)
        self.assertIn("next.textContent = 'Далее'", self.content)
        self.assertIn("answer-selected", self.content)
        self.assertIn("answer-correct", self.content)
        self.assertIn("answer-selected-wrong", self.content)
        self.assertIn("Ваш ответ:", self.content)
        self.assertIn("Правильный ответ:", self.content)
        self.assertIn("Не удалось обновить интерфейс после ответа. Попробуйте снова.", self.content)

    def test_no_automatic_send_data_after_api_failures(self):
        self.assertIn("apiDiagState.attemptStatus = 'fetch_rejected';", self.content)
        self.assertIn("showAnswerFallbackAction(payload);", self.content)
        self.assertIn("fallbackBtn.textContent = 'Отправить через резервный режим Telegram';", self.content)
        self.assertIn("warning.textContent = 'Резервный режим Telegram может закрыть Mini App.';", self.content)
        self.assertIn("setSetupStatus(e?.name === 'AbortError' ? 'api_timeout' : 'api_failed'", self.content)
        self.assertIn("setSetupStatus('explicit_fallback_sendData');", self.content)
        self.assertIn("if (answerSubmitInFlight) return;", self.content)
        self.assertIn("'X-Miniapp-Request-Id': requestId", self.content)

    def test_debug_diagnostics_include_safe_request_phases(self):
        self.assertIn("function buildMiniappRequestId()", self.content)
        self.assertIn("apiDiagState.answerPhase = 'preparing';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'fetch_started';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'response_headers_received';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'json_parse_started';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'json_parse_failed';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'ui_render_failed';", self.content)
        self.assertNotIn("Authorization: `tma ${initData}` +", self.content)

    def test_setup_mode_hydration_is_guarded(self):
        self.assertIn("const hydrateOnSetup = ctx?.hydrate_on_setup === true;", self.content)
        self.assertIn("if (apiBase && tg?.initData && (!setupMode || hydrateOnSetup)) {", self.content)
        self.assertIn("await apiFetch(`${apiBase}/miniapp/state`", self.content)


if __name__ == '__main__':
    unittest.main()
