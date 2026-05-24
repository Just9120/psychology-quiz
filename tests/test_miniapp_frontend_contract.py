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
        self.assertIn("Сеть подвисла, пробую отправить ещё раз...", self.content)
        self.assertIn("Запуск не удался, повторная попытка...", self.content)
        self.assertIn("Не удалось запустить викторину через API. Попробуйте снова.", self.content)
        self.assertIn("feedback-correct", self.content)
        self.assertIn("feedback-wrong", self.content)
        self.assertIn("next.textContent = 'Далее'", self.content)
        self.assertIn("answer-selected", self.content)
        self.assertIn("answer-correct", self.content)
        self.assertIn("answer-selected-wrong", self.content)
        self.assertIn("Ваш ответ:", self.content)
        self.assertIn("Правильный ответ:", self.content)
        self.assertNotIn("Правильный ответ: ?.", self.content)
        self.assertIn("Отправляю ответ...", self.content)
        self.assertIn("Проверяю, был ли ответ принят...", self.content)
        self.assertIn("Повторная отправка ответа...", self.content)
        self.assertIn("Ответ принят.", self.content)
        self.assertIn("Ответ принят, состояние обновлено.", self.content)
        self.assertIn("Ответ уже был принят, состояние обновлено.", self.content)
        self.assertIn("Не удалось обновить интерфейс после ответа. Попробуйте снова.", self.content)


    def test_incomplete_feedback_resync_guard(self):
        self.assertIn('function hasCompleteFeedback(feedback)', self.content)
        self.assertIn("if (hasCompleteFeedback(answerJson.feedback))", self.content)
        self.assertIn("answerJson.submission_status === 'duplicate'", self.content)
        self.assertIn("answerJson.submission_status === 'stale_question'", self.content)
        self.assertIn("renderRunnerState(answerJson.runner_state, { preferLaunchCompact: false });", self.content)

    def test_no_automatic_send_data_after_api_failures(self):
        self.assertIn("apiDiagState.answerPhase = 'retry_exhausted';", self.content)
        self.assertNotIn("setSetupStatus('explicit_fallback_sendData');", self.content)
        self.assertIn("if (answerSubmitInFlight) return;", self.content)
        self.assertNotIn("'X-Miniapp-Request-Id': requestId", self.content)
        self.assertIn("if (!tg?.sendData)", self.content)

    def test_simple_body_transport_contract(self):
        self.assertIn("headers: { 'Content-Type': 'text/plain;charset=UTF-8' }", self.content)
        self.assertIn("init_data: initData", self.content)
        self.assertIn("request_id: attemptRequestId", self.content)
        self.assertIn("apiDiagState.answerTransport = 'simple_body';", self.content)
        self.assertIn("apiDiagState.setupTransport = 'simple_body';", self.content)
        self.assertNotIn("'X-Miniapp-Request-Id': requestId", self.content)

    def test_debug_diagnostics_include_safe_request_phases(self):
        self.assertIn("function buildMiniappRequestId()", self.content)
        self.assertIn("function apiFetchWithRetry(", self.content)
        self.assertIn("apiDiagState.answerPhase = 'preparing';", self.content)
        self.assertIn("const ANSWER_API_TIMEOUT_MS = 4000;", self.content)
        self.assertIn("apiDiagState.answerPhase = 'retry_scheduled';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'pre_retry_state_resync_attempted';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'pre_retry_state_resync_success';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'pre_retry_state_resync_no_change';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'pre_retry_state_resync_failed';", self.content)
        self.assertIn("'retry_started'", self.content)
        self.assertIn("runnerState.textContent = 'Повторная отправка ответа...';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'retry_exhausted';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'state_resync_attempted';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'state_resync_success';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'state_resync_failed';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'ui_render_failed';", self.content)
        self.assertNotIn("Authorization: `tma ${initData}` +", self.content)

    def test_state_advance_helper_contract(self):
        self.assertIn('function didRunnerStateAdvanceForAnswer(submittedSessionId, submittedQuestionId, runnerState)', self.content)
        self.assertIn("stateName === 'completed'", self.content)
        self.assertIn("statusName === 'no_current_question'", self.content)
        self.assertIn('currentQuestionId !== Number(submittedQuestionId);', self.content)

    def test_setup_mode_hydration_is_guarded(self):
        self.assertIn("const hydrateOnSetup = ctx?.hydrate_on_setup === true;", self.content)
        self.assertIn("if (apiBase && tg?.initData && (!setupMode || hydrateOnSetup)) {", self.content)
        self.assertIn("await apiFetch(`${apiBase}/miniapp/state`", self.content)


if __name__ == '__main__':
    unittest.main()
