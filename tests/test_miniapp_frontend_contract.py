import unittest
from pathlib import Path
import re


class MiniAppFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Path('miniapp/index.html').read_text(encoding='utf-8')


    def test_user_facing_copy_is_product_style(self):
        self.assertIn('<title>Мини-викторина</title>', self.content)
        self.assertIn('/> Лёгкие</label>', self.content)
        self.assertIn('/> Средние</label>', self.content)
        self.assertIn('/> Сложные</label>', self.content)
        self.assertNotIn('Экспериментальный режим /ui', self.content)
        self.assertNotIn('Mini App API недоступен', self.content)
        self.assertNotIn('URL-транспорта', self.content)
        self.assertNotIn('opt-in /ui', self.content)
        self.assertNotIn('sendData недоступен', self.content)
        self.assertNotIn('server state', self.content)

    def test_diagnostics_hidden_by_default(self):
        self.assertIn('id="api_diag" class="note" hidden', self.content)
        self.assertIn('if (!debugMode) {', self.content)

    def test_debug_mode_query_flag_supported(self):
        self.assertIn("getQueryParam('debug') === '1'", self.content)

    def test_setup_visual_structure_preserves_native_controls(self):
        self.assertIn('id="setup_intro" class="setup-intro"', self.content)
        self.assertIn('Выберите формат, темы и сложность — всё пройдёт внутри Telegram.', self.content)
        self.assertIn('<form id="f" class="setup-form" hidden>', self.content)
        self.assertGreaterEqual(self.content.count('class="setup-section"'), 3)
        self.assertIn('<fieldset id="cats_fieldset" class="setup-section">', self.content)
        self.assertIn('border-radius: 16px;', self.content)
        self.assertIn('background: #fff;', self.content)
        self.assertIn('label input {', self.content)
        self.assertIn('<input type="radio" name="quiz_mode" value="single" checked /> Конкретная тема', self.content)
        self.assertIn('<input type="radio" name="quiz_mode" value="selected_mix" /> Микс из выбранных тем', self.content)
        self.assertIn('<input type="radio" name="quiz_mode" value="all" /> Все темы', self.content)
        self.assertIn('<input type="radio" name="question_count" value="5" checked /> 5', self.content)
        self.assertIn('<input type="radio" name="question_count" value="10" /> 10', self.content)
        self.assertIn('<input type="radio" name="question_count" value="15" /> 15', self.content)
        self.assertIn('<input type="radio" name="question_count" value="all" /> Все доступные', self.content)
        self.assertIn('<input type="radio" name="difficulty" value="any" checked /> Любая', self.content)
        self.assertIn('<input type="radio" name="difficulty" value="easy" /> Лёгкие', self.content)
        self.assertIn('<input type="radio" name="difficulty" value="medium" /> Средние', self.content)
        self.assertIn('<input type="radio" name="difficulty" value="hard" /> Сложные', self.content)
        self.assertIn("input.name = inputType === 'radio' ? 'category_id' : 'category_ids';", self.content)
        self.assertIn("label.className = 'setup-option';", self.content)

    def test_progress_is_single_clear_question_presentation(self):
        self.assertIn("function renderProgress(progress)", self.content)
        self.assertIn("runnerState.textContent = 'Выберите вариант ответа.';", self.content)
        self.assertNotIn("Идёт викторина: ${parts.join(' · ')}.", self.content)
        self.assertNotIn("отвечено: ${answered}", self.content)
        self.assertNotIn("осталось: ${remaining}", self.content)
        self.assertNotIn("className = 'progress-chip'", self.content)
        self.assertNotIn("Math.round((order / total) * 100)", self.content)
        self.assertIn("progress.className = 'question-progress';", self.content)
        self.assertIn("? `Вопрос ${order} из ${total}` : 'Прогресс';", self.content)
        self.assertIn("header.className = 'question-title';", self.content)
        self.assertIn("q.className = 'question-text';", self.content)

    def test_completed_view_has_product_facing_copy_and_next_actions(self):
        self.assertIn("card.className = 'result-card';", self.content)
        self.assertIn("title.className = 'result-title';", self.content)
        self.assertIn("actions.className = 'completion-actions';", self.content)
        self.assertIn("title.textContent = 'Последняя викторина завершена 🎉'", self.content)
        self.assertIn('Результат: ${Number.isInteger(score) ? score : 0} из ${Number.isInteger(total) ? total : 0}', self.content)
        self.assertIn("hint.textContent = 'Можно начать новую викторину или закрыть окно.'", self.content)
        self.assertIn("runnerState.textContent = 'Последняя викторина завершена.'", self.content)
        self.assertIn("restart.textContent = 'Новая викторина'", self.content)
        self.assertIn("closeBtn.textContent = 'Закрыть Mini App'", self.content)
        self.assertNotIn('Вы просматриваете завершённый результат из серверного состояния', self.content)
        self.assertNotIn('тема требует повторения', self.content)
        self.assertNotIn('база уже есть', self.content)
        self.assertNotIn('тема хорошо усвоена', self.content)
        self.assertNotIn('location.reload();', self.content)
        self.assertIn('function getSafeSetupUrl()', self.content)
        self.assertIn('new URL(ctx.setup_url, location.origin)', self.content)
        self.assertIn("setupUrl.pathname === '/'", self.content)
        self.assertIn("setSetupStatus('ready_for_submit')", self.content)
        self.assertNotIn("ctx.setup_url.includes('api_base_url=')", self.content)
        self.assertIn('const safeSetupUrl = getSafeSetupUrl();', self.content)
        self.assertIn('if (safeSetupUrl) {', self.content)
        self.assertIn("await fetchJsonWithTelemetry(`${apiBase}/miniapp/setup-options`", self.content)
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

    def test_setup_warning_is_limited_to_mode_selection(self):
        self.assertIn('function showSetupWarningIfNeeded()', self.content)
        self.assertIn('function hideSetupWarning()', self.content)
        mode_start = self.content.index('function showModeSelection()')
        mode_body = self.content[mode_start:self.content.index('      }', mode_start) + 7]
        self.assertIn('showSetupWarningIfNeeded();', mode_body)
        for function_name in (
            'showSetupMode',
            'showRunnerMode',
            'showCompletedMode',
            'showGlossaryView',
            'renderGlossaryTopics',
            'renderGlossaryCounts',
            'renderGlossaryState',
            'renderGlossaryFeedback',
            'renderGlossaryResult',
        ):
            function_start = self.content.index(f'function {function_name}')
            function_body = self.content[function_start:self.content.index('      }', function_start) + 7]
            self.assertIn('hideSetupWarning();', function_body)

    def test_glossary_choices_use_soft_miniapp_button_styles(self):
        self.assertIn('.miniapp-choice-list {', self.content)
        self.assertIn('.miniapp-choice-button {', self.content)
        self.assertIn('.glossary-choice-button {', self.content)
        self.assertIn('id="mode_topics" class="miniapp-choice-button mode-choice-button"', self.content)
        self.assertIn("choices.className = 'miniapp-choice-list';", self.content)
        self.assertIn("btn.className = 'miniapp-choice-button glossary-choice-button';", self.content)
        self.assertIn("back.className = 'miniapp-choice-button glossary-choice-button';", self.content)

    def test_glossary_feedback_highlights_answer_buttons(self):
        self.assertIn("btn.setAttribute('data-option-index', String(idx));", self.content)
        function_start = self.content.index('function renderGlossaryFeedback(question, feedback)')
        function_body = self.content[function_start:self.content.index('      function renderGlossaryResult', function_start)]
        self.assertIn("const optionButtons = [...glossaryView.querySelectorAll('ol button')];", function_body)
        self.assertIn("btn.disabled = true;", function_body)
        self.assertIn("btn.classList.add('answer-correct');", function_body)
        self.assertIn("btn.classList.add('answer-selected-wrong');", function_body)
        self.assertIn("btn.classList.add('answer-disabled');", function_body)
        self.assertIn("feedback?.selected_option_index", function_body)
        self.assertIn("feedback?.correct_option_index", function_body)
        self.assertIn("status.textContent = feedback?.is_correct ? '✅ Верно' : '❌ Неверно';", function_body)

    def test_timeout_and_feedback_ui_contract(self):
        self.assertIn("AbortController", self.content)
        self.assertIn("Не удалось отправить ответ через API. Попробуйте снова.", self.content)
        self.assertIn("Сеть подвисла, пробую отправить ещё раз...", self.content)
        self.assertIn("Запуск не удался, повторная попытка...", self.content)
        self.assertIn("Не удалось начать викторину. Попробуйте ещё раз.", self.content)
        self.assertIn("feedback-correct", self.content)
        self.assertIn("feedback-wrong", self.content)
        self.assertIn("next.textContent = 'Далее'", self.content)
        self.assertIn("answer-selected", self.content)
        self.assertIn("answer-pending", self.content)
        self.assertIn("answer-disabled", self.content)
        self.assertIn("answer-correct", self.content)
        self.assertIn("answer-selected-wrong", self.content)
        self.assertIn("ol button {", self.content)
        self.assertIn("border-radius: 14px;", self.content)
        self.assertIn("border: 1px solid #d6dce8;", self.content)
        self.assertIn("text-align: left;", self.content)
        self.assertIn("white-space: normal;", self.content)
        self.assertIn("line-height: 1.35;", self.content)
        self.assertIn("ol button.answer-selected {", self.content)
        self.assertIn("ol button.answer-pending {", self.content)
        self.assertIn("ol button.answer-correct {", self.content)
        self.assertIn("ol button.answer-selected-wrong {", self.content)
        self.assertIn("ol button.answer-selected {\n        border: 2px solid", self.content)
        self.assertIn("ol button.answer-pending {\n        border: 2px solid", self.content)
        self.assertIn("ol button.answer-correct {\n        border: 2px solid", self.content)
        self.assertIn("ol button.answer-selected-wrong {\n        border: 2px solid", self.content)
        self.assertIn("ol button.answer-selected {\n        border: 2px solid #5f6778;\n        background: #f3f5fa;", self.content)
        self.assertIn("ol button.answer-pending {\n        border: 2px solid #3653a5;\n        background: #eef3ff;", self.content)
        self.assertIn("ol button.answer-correct {\n        border: 2px solid #0a7d24;\n        background: #edf9f1;", self.content)
        self.assertIn("ol button.answer-selected-wrong {\n        border: 2px solid #b00020;\n        background: #fff1f3;", self.content)
        self.assertNotIn(".answer-selected { outline:", self.content)
        self.assertNotIn(".answer-pending {\n        outline:", self.content)
        self.assertNotIn(".answer-correct {\n        outline:", self.content)
        self.assertNotIn(".answer-selected-wrong {\n        outline:", self.content)
        self.assertIn("ol button:disabled {", self.content)
        self.assertIn("-webkit-text-fill-color: #222;", self.content)
        self.assertNotIn("opacity: 0.65;", self.content)
        self.assertIn("statusEl.textContent = 'Проверяю ответ...';", self.content)
        self.assertIn("card.className = 'question-card';", self.content)
        self.assertIn("card.appendChild(list);", self.content)
        self.assertIn("status.className = 'answer-status';", self.content)
        self.assertIn("statusEl.classList.add('pending');", self.content)
        self.assertIn("Ваш ответ:", self.content)
        self.assertIn("Правильный ответ:", self.content)
        self.assertIn("const isCorrect = feedback?.is_correct === true || (correctIdx !== null && selectedIdx === correctIdx);", self.content)
        self.assertIn("if (!isCorrect && correctIdx !== null && correctText) {", self.content)
        self.assertNotIn("Правильный ответ: ?.", self.content)
        self.assertIn("Отправляю ответ...", self.content)
        self.assertIn("Проверяю, был ли ответ принят...", self.content)
        self.assertIn("Повторная отправка ответа...", self.content)
        self.assertIn("Ответ принят.", self.content)
        self.assertIn("Ответ принят, состояние обновлено.", self.content)
        self.assertIn("Ответ уже был принят, состояние обновлено.", self.content)
        self.assertIn("Не удалось обновить интерфейс после ответа. Попробуйте снова.", self.content)
        self.assertIn("feedback-line", self.content)
        self.assertIn("next.className = 'answer-next';", self.content)


    def test_setup_topic_selection_modes_and_disabled_reasons(self):
        self.assertIn('id="setup_hint" class="meta"', self.content)
        self.assertIn("const setupHint = document.getElementById('setup_hint');", self.content)
        self.assertIn("const inputType = mode === 'selected_mix' ? 'checkbox' : 'radio';", self.content)
        self.assertIn("input.type = inputType;", self.content)
        self.assertIn("input.name = inputType === 'radio' ? 'category_id' : 'category_ids';", self.content)
        self.assertIn("const selectedSet = new Set(mode === 'single' ? selectedIds.slice(0, 1) : selectedIds);", self.content)
        self.assertIn("checked.slice(1).forEach((input) => { input.checked = false; });", self.content)
        self.assertIn("catsFieldset.hidden = allMode;", self.content)
        self.assertIn("category_ids: mode === 'all' ? [] : selected,", self.content)
        self.assertIn("if (!ok) hint = 'Выберите одну тему, чтобы начать.';", self.content)
        self.assertIn("if (!ok) hint = 'Выберите хотя бы одну тему.';", self.content)
        self.assertIn("setupHint.textContent = hint;", self.content)

    def test_answer_rendering_avoids_duplicate_numbering_and_preserves_clickable_cards(self):
        self.assertIn("const list = document.createElement('ol');", self.content)
        self.assertIn("btn.textContent = txt;", self.content)
        self.assertNotIn("btn.textContent = `${Number.isInteger(idx) ? idx + 1 : '?'}: ${txt}`;", self.content)
        self.assertIn("btn.addEventListener('click', () => submitAnswer", self.content)
        self.assertIn("text-align: left;", self.content)
        self.assertIn("white-space: normal;", self.content)


    def test_incomplete_feedback_resync_guard(self):
        self.assertIn('function hasCompleteFeedback(feedback)', self.content)
        self.assertIn("function getResyncedFeedbackForSubmission(stateData, submittedQuestionId, selectedOptionIndex)", self.content)
        self.assertIn("const feedback = stateData?.recent_answer_feedback;", self.content)
        self.assertIn("if (hasCompleteFeedback(answerJson.feedback))", self.content)
        self.assertIn("answerJson.submission_status === 'duplicate'", self.content)
        self.assertIn("answerJson.submission_status === 'stale_question'", self.content)
        self.assertIn("answerJson.submission_status === 'resynced_with_feedback'", self.content)
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
        self.assertIn("function firstSuccessfulOrAllFailed(candidateFactories)", self.content)
        self.assertIn("function apiFetchWithRetry(", self.content)
        self.assertNotIn("Promise.race([attemptPromise, hedgePromise])", self.content)
        self.assertIn("apiDiagState.answerPhase = 'preparing';", self.content)
        self.assertIn("const ANSWER_API_TIMEOUT_MS = 8000;", self.content)
        self.assertIn("const ANSWER_HEDGE_DELAY_MS = 1000;", self.content)
        self.assertIn("apiDiagState.answerPhase = 'retry_scheduled';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'answer_hedge_timer_started';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'answer_hedge_state_resync_attempted';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'answer_hedge_state_resync_success';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'answer_hedge_state_resync_no_change';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'answer_hedge_retry_started';", self.content)
        self.assertIn("apiDiagState.answerHedged = true;", self.content)
        self.assertIn("apiDiagState.answerWinnerAttempt", self.content)
        self.assertIn("hedged=${s.hedged ? 'true' : 'false'}", self.content)
        self.assertIn("winner_attempt=${s.winner_attempt}", self.content)
        self.assertIn("hedge_delay_ms=${s.hedge_delay_ms}", self.content)
        self.assertIn("hedge_started_ms=${s.hedge_started_ms}", self.content)
        self.assertIn("markTelemetry(telemetry, 'hedge_retry_started'", self.content)
        self.assertIn("apiDiagState.answerPhase = 'answer_late_result_ignored';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'pre_retry_state_resync_attempted';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'pre_retry_state_resync_success';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'pre_retry_state_resync_no_change';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'pre_retry_state_resync_failed';", self.content)
        self.assertIn("'retry_started'", self.content)
        self.assertIn("runnerState.textContent = 'Повторная отправка ответа...';", self.content)
        self.assertIn("runnerState.textContent = 'Сеть подвисла, пробую отправить ещё раз...';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'retry_exhausted';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'state_resync_attempted';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'state_resync_success';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'state_resync_failed';", self.content)
        self.assertIn("apiDiagState.answerPhase = 'ui_render_failed';", self.content)
        self.assertNotIn("Authorization: `tma ${initData}` +", self.content)
        self.assertIn("database_busy_retry", self.content)
        self.assertIn("status === 503", self.content)
        self.assertIn("status === 429", self.content)
        self.assertIn("Math.floor(Math.random() * 500)", self.content)
        self.assertIn("function getRetryDelayMs(baseMs)", self.content)
        self.assertIn("await waitMs(getRetryDelayMs(backoffMs[attempt - 1] || 1000));", self.content)
        self.assertIn("function pushDiagPhase(track, phase, startedAt, extras = {})", self.content)
        self.assertIn("pushDiagPhase('answer', 'request_scheduled'", self.content)
        self.assertIn("pushDiagPhase('answer', 'response_headers_received'", self.content)
        self.assertIn("pushDiagPhase('answer', 'response_body_parsed'", self.content)
        self.assertIn("pushDiagPhase('answer', 'state_update_started'", self.content)
        self.assertIn("pushDiagPhase('answer', 'state_update_applied'", self.content)
        self.assertIn("pushDiagPhase('answer', 'ui_render_mark'", self.content)
        self.assertIn("pushDiagPhase('setup', 'request_scheduled'", self.content)
        self.assertIn("pushDiagPhase('setup', 'response_headers_received'", self.content)
        self.assertIn("pushDiagPhase('setup', 'response_body_parsed'", self.content)
        self.assertIn("pushDiagPhase('setup', 'state_update_started'", self.content)
        self.assertIn("pushDiagPhase('setup', 'state_update_applied'", self.content)
        self.assertIn("pushDiagPhase('setup', 'ui_render_mark'", self.content)
        self.assertIn("answer_transport:", self.content)
        self.assertIn("setup_transport:", self.content)

    def test_client_telemetry_debug_contract(self):
        self.assertIn('id="telemetry_debug" class="note telemetry-debug" hidden', self.content)
        self.assertIn("const FRONTEND_VERSION = 'ui-polish-v6-visual-cleanup';", self.content)
        self.assertIn("function startTelemetry(action, endpoint", self.content)
        self.assertIn("marks: { action_start: startedAt, 'tap/action_start': startedAt }", self.content)
        self.assertIn("markTelemetry(telemetry, 'before_build_payload'", self.content)
        self.assertIn("markTelemetry(telemetry, 'before_fetch'", self.content)
        self.assertIn("markTelemetry(telemetry, 'request_start'", self.content)
        self.assertIn("markTelemetry(telemetry, 'response_received'", self.content)
        self.assertIn("markTelemetry(telemetry, 'json_parsed'", self.content)
        self.assertIn("markTelemetry(telemetry, 'render_start'", self.content)
        self.assertIn("markTelemetry(telemetry, 'render_done'", self.content)
        self.assertIn("markTelemetry(telemetry, 'action_done'", self.content)
        self.assertIn("console.info('miniapp_client_telemetry'", self.content)
        self.assertIn("'X-Miniapp-Request-Id'", self.content)
        self.assertIn("function withMiniappRequestId(headers = {}, requestId = '')", self.content)
        self.assertIn("pre_request_ms", self.content)
        self.assertIn("missing_network_marks", self.content)
        self.assertIn("ok_missing_network_marks", self.content)
        self.assertIn("existingRequestId || telemetry?.request_id || buildMiniappRequestId()", self.content)
        self.assertIn("action request_id pre_request_ms request_ms parse_ms render_ms total_ms status/http_code missing_network_marks", self.content)
        self.assertIn("headers: { Authorization: `tma ${tg.initData}` }", self.content)
        self.assertNotIn("apiDiag.textContent = tg.initData", self.content)



    def test_glossary_open_has_loading_fallback_and_visible_failure(self):
        self.assertIn("msg.textContent = 'Загружаем глоссарий...';", self.content)
        self.assertIn("runnerState.textContent = 'Загружаем глоссарий...';", self.content)
        self.assertIn("Не удалось открыть глоссарий. Попробуйте закрыть окно и открыть /ui заново.", self.content)
        self.assertIn("parseFailureType || (resp.ok ? 'unexpected_payload' : 'non_ok_response')", self.content)
        self.assertIn("parse_failure_type: 'request_exception'", self.content)
        self.assertIn("parse_failure_type: 'missing_api_or_init_data'", self.content)
        self.assertIn("const text = await resp.text();", self.content)
        self.assertIn("JSON.parse(text)", self.content)
        self.assertIn("parseFailureType: 'invalid_json'", self.content)
        self.assertIn("parseFailureType: 'empty_body'", self.content)
        self.assertIn("function getGlossaryTopicsFromSetupCache()", self.content)
        self.assertIn("function getGlossaryTopicsFromSetupPayload(payload)", self.content)
        self.assertIn("function hasUsableGlossaryTopics(topics)", self.content)
        self.assertIn("glossarySetupCache.topics = setupResult.topics;", self.content)
        self.assertIn("attemptedSources.push('setup-options');", self.content)
        self.assertNotIn("attemptedSources.push('glossary-topics');", self.content)
        self.assertIn("console.info('miniapp_glossary_open_failed'", self.content)

    def test_glossary_open_uses_setup_options_only_for_primary_flow(self):
        self.assertIn("await fetchJsonWithTelemetry(`${apiBase}/miniapp/setup-options`", self.content)
        self.assertIn("topics: getGlossaryTopicsFromSetupPayload(ctx)", self.content)
        self.assertIn("payload?.setup?.glossary?.topics", self.content)
        self.assertIn("payload?.glossary?.topics", self.content)
        self.assertIn("payload?.setup_options?.glossary?.topics", self.content)
        self.assertNotIn("/miniapp/glossary/topics", self.content)

    def test_glossary_click_prefers_context_cache_before_setup_options(self):
        handler_start = self.content.index("modeGlossary.addEventListener('click', async () => {")
        handler = self.content[handler_start:self.content.index("      });", handler_start) + 10]
        self.assertLess(handler.index("const cachedTopics = getGlossaryTopicsFromSetupCache();"), handler.index("attemptedSources.push('setup-options');"))
        self.assertLess(handler.index("renderGlossaryTopics(glossaryTopicsCache);"), handler.index("if (!apiBase || !tg?.initData)"))
        self.assertIn("showGlossaryOpenError({ ...lastFailure, attempted_sources: attemptedSources });", handler)

    def test_glossary_primary_flow_uses_existing_endpoints_only(self):
        self.assertIn("glossaryFetch('/miniapp/setup', { mode: 'glossary'", self.content)
        self.assertIn("glossaryFetch('/miniapp/answer', { mode: 'glossary', action: 'answer'", self.content)
        self.assertIn("glossaryFetch('/miniapp/answer', { mode: 'glossary', action: 'next'", self.content)
        self.assertIn("glossaryFetch('/miniapp/answer', { mode: 'glossary', action: 'restart'", self.content)
        for endpoint in ("/miniapp/glossary/start", "/miniapp/glossary/answer", "/miniapp/glossary/next", "/miniapp/glossary/restart", "/miniapp/glossary/topics"):
            self.assertNotIn(endpoint, self.content)


    def test_glossary_start_normalizes_count_and_maps_safe_errors(self):
        self.assertIn("glossaryFetch('/miniapp/setup', { mode: 'glossary', topic_id: topic.topic_id, question_count: payloadCount }, requestId)", self.content)
        self.assertIn("function normalizeGlossaryCountForPayload(count)", self.content)
        self.assertIn("return numeric === 5 || numeric === 10 ? numeric : count;", self.content)
        self.assertIn("function getGlossaryStartErrorMessage(errorCode, httpStatus)", self.content)
        self.assertIn("Не удалось начать тест: некорректные параметры глоссария.", self.content)
        self.assertIn("Для этой темы пока недостаточно терминов.", self.content)
        self.assertIn("Не удалось подтвердить сессию Mini App. Закройте окно и откройте /ui заново.", self.content)
        self.assertIn("Не удалось начать тест по глоссарию. Попробуйте открыть /ui заново.", self.content)
        self.assertIn("console.info('miniapp_glossary_start_failed'", self.content)
        self.assertIn("{ http_status: httpStatus, error_code: errorCode, request_id: apiDiagState.setupRequestId || '' }", self.content)
        self.assertIn("const diagnosticLines = [", self.content)
        self.assertIn("`Код: ${errorCode || 'unknown'}`", self.content)
        self.assertIn("`HTTP: ${httpStatus || 'unknown'}`", self.content)
        self.assertIn("`Request: ${requestId || 'unknown'}`", self.content)
        self.assertIn("const visibleMessage = [message, ...diagnosticLines].join('\\n');", self.content)
        self.assertIn("runnerState.textContent = visibleMessage;", self.content)
        self.assertIn("err.textContent = visibleMessage;", self.content)
        function_start = self.content.index("function showGlossaryStartError(details = {})")
        function_body = self.content[function_start:self.content.index("      }", function_start) + 7]
        self.assertNotIn("init_data", function_body)
        self.assertNotIn("token", function_body)
        self.assertNotIn("JSON.stringify(details", function_body)
        self.assertNotIn("source_refs", self.content)
        self.assertNotIn("supplied_snippet", self.content)
        self.assertNotIn("question:m2_exp", self.content)

    def test_glossary_error_only_after_setup_options_attempted(self):
        handler_start = self.content.index("modeGlossary.addEventListener('click', async () => {")
        handler = self.content[handler_start:self.content.index("      });", handler_start) + 10]
        self.assertIn("const attemptedSources = ['cache'];", handler)
        self.assertIn("attemptedSources.push('setup-options');", handler)
        self.assertNotIn("attemptedSources.push('glossary-topics');", handler)
        self.assertEqual(1, handler.count("showGlossaryOpenError({ ...lastFailure, attempted_sources: attemptedSources });"))


    def test_docs_numbered_h2_headings_have_unique_numbers(self):
        docs = Path('docs/miniapp-deployment-qa.md').read_text(encoding='utf-8')
        numbers = re.findall(r'^## (\d+)\)', docs, flags=re.MULTILINE)
        self.assertTrue(numbers, 'Expected numbered ## headings in docs/miniapp-deployment-qa.md')
        duplicates = sorted({n for n in numbers if numbers.count(n) > 1}, key=int)
        self.assertEqual(duplicates, [], f'Duplicate numbered ## headings found: {duplicates}')

    def test_debug_diagnostics_do_not_render_secrets(self):
        self.assertNotIn("tg.initData", " ".join(line for line in self.content.splitlines() if "apiDiag.textContent" in line or "answer_phases" in line or "setup_phases" in line))
        self.assertNotIn("Authorization", " ".join(line for line in self.content.splitlines() if "apiDiag.textContent" in line))

    def test_state_advance_helper_contract(self):
        self.assertIn('function didRunnerStateAdvanceForAnswer(submittedSessionId, submittedQuestionId, runnerState)', self.content)
        self.assertIn('const nestedSessionId = Number(runnerState.session?.session_id);', self.content)
        self.assertIn('const resolvedSessionId = Number.isInteger(nestedSessionId) ? nestedSessionId : (', self.content)
        self.assertIn('if (Number.isInteger(resolvedSessionId) && resolvedSessionId !== Number(submittedSessionId)) return false;', self.content)
        self.assertIn("stateName === 'completed'", self.content)
        self.assertIn("statusName === 'no_current_question'", self.content)
        self.assertIn('currentQuestionId !== Number(submittedQuestionId);', self.content)

    def test_setup_mode_hydration_is_guarded(self):
        self.assertIn("const hydrateOnSetup = ctx?.hydrate_on_setup === true;", self.content)
        self.assertIn("if (apiBase && tg?.initData && (!setupMode || hydrateOnSetup)) {", self.content)
        self.assertIn("await apiFetch(`${apiBase}/miniapp/state`", self.content)

    def test_setup_hydration_required_uses_setup_options_before_mode_chooser(self):
        self.assertIn("const setupHydrationRequired = setupMode && ctx?.setup_hydration_required === true;", self.content)
        self.assertIn("async function hydrateSetupOptionsBeforeModeSelection()", self.content)
        self.assertIn("await fetchJsonWithTelemetry(`${apiBase}/miniapp/setup-options`", self.content)
        self.assertIn("headers: { Authorization: `tma ${tg.initData}` }", self.content)
        self.assertIn("setupOptionsCache.categories = categories;", self.content)
        self.assertIn("glossarySetupCache.topics = topics;", self.content)
        self.assertIn("if (resp.ok && data?.ok === true && applyHydratedSetupOptions(data))", self.content)
        self.assertIn("showModeSelection();", self.content)
        self.assertIn("modeView.hidden = true;", self.content)
        self.assertIn("Не удалось загрузить параметры викторины: Mini App API или данные Telegram недоступны.", self.content)
        self.assertIn("payload?.setup_options?.glossary?.topics", self.content)

    def test_legacy_inline_setup_context_still_renders_without_hydration(self):
        self.assertIn("} else if (setupMode && !setupHydrationRequired && !Array.isArray(ctx.categories)) {", self.content)
        self.assertIn("if (setupHydrationRequired) {", self.content)
        self.assertIn("} else {\n            showModeSelection();\n          }", self.content)


if __name__ == '__main__':
    unittest.main()
