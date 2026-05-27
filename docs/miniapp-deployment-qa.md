# Mini App deployment and manual QA checklist (MVP)

## Purpose
Этот runbook нужен для безопасной ручной deployment-валидации Telegram Mini App runner MVP (implemented through PR #162) без изменения runtime-поведения бота.

## 1) Current state
- Mini App MVP код уже в репозитории.
- Статический frontend runner MVP расположен в `miniapp/index.html`.
- Бот открывает Mini App URL через `MINI_APP_URL` (опциональная env-переменная).
- Классический `/quiz` остаётся дефолтным UX.
- Mini App запускается opt-in через `/ui`.
- `/stats` остаётся скрытой owner-only командой только для private chat.

## 2) Hosting requirement
- `miniapp/index.html` должен быть опубликован по **HTTPS**.
- URL должен быть доступен из Telegram-клиентов (mobile/desktop).
- Production URL задаётся в `MINI_APP_URL` окружении бота.
- `MINI_APP_URL` не должен содержать секретов.
- На текущем состоянии репозитория автоматический production-hosting для `miniapp/index.html` **не реализован** в составе `deploy.sh`/`docker-compose.yml` (операторская задача инфраструктуры).

## 3) Configuration checklist

### Cloudflare Workers Static Assets (GitHub deployment flow)
- Build command: empty
- Deploy command: `npx wrangler deploy`
- Path: `/`
- Static assets directory in `wrangler.toml`: `./miniapp`

1. Опубликовать `miniapp/index.html` на HTTPS static hosting в deployment environment.
2. После готовности Cloudflare custom domain установить `MINI_APP_URL` на этот HTTPS URL в runtime `.env` на VPS.
3. Перезапустить/передеплоить bot service, чтобы env подхватился.
4. Проверить в Telegram, что `/ui` показывает кнопку открытия Mini App (при наличии активных категорий).
5. По возможности в staging/dev отдельно проверить fallback-поведение `/ui`, когда `MINI_APP_URL` отсутствует.

### Optional local sanity check (не заменяет Telegram QA)
Для быстрой browser-проверки разметки runner MVP можно локально отдать файл, например:
- `python -m http.server 8080`

Важно: локальная браузерная проверка **не** является полной валидацией Telegram Mini App интеграции.

## 4) Telegram / BotFather operator checklist (generic)
- Убедиться, что бот в Telegram может открыть указанный Web App URL.
- Проверить валидность HTTPS URL (сертификат/доступность).
- В BotFather настроить Mini App domain на `miniapp.librechat.online` (без коммита токенов/секретов в репозиторий).
- API домен остаётся `quiz-api.librechat.online`; разрешённый origin API остаётся `https://miniapp.librechat.online`.
- Primary launch path для `/ui` должен использовать свежую inline WebApp кнопку (не plain URL button), чтобы Telegram передавал `WebApp.initData`.
- Persistent reply-keyboard WebApp launch-кнопки для Mini App намеренно не используются: они могут сохранить stale launch context.

## 5) Manual QA checklist

### A. Private chat checks
- [ ] `/ui` без `MINI_APP_URL` показывает fallback.
- [ ] `/ui` с `MINI_APP_URL` и активными категориями показывает primary inline кнопку открытия Mini App.
- [ ] После `/start` в нижнем меню видна кнопка `🚀 Викторина в окне`.
- [ ] Кнопка нижнего меню `🚀 Викторина в окне` отправляет свежий launch-сценарий через `/ui` (бот присылает новую inline WebApp-кнопку `🚀 Открыть викторину`).
- [ ] Кнопка `🚀 Викторина в окне` не использует persistent WebApp URL в reply keyboard (stale launch context не хранится).
- [ ] `/ui` не показывает persistent bottom WebApp reply-кнопки для Mini App (только стандартное главное меню).
- [ ] Если пользователь видит `API недоступен`, закрыть Mini App, отправить свежий `/ui` и открыть новую inline-кнопку.
- [ ] `/ui` при отсутствии активных категорий показывает no-categories fallback.
- [ ] `/ui` вне private chat корректно отклоняется.

### B. Mini App runner MVP checks
- [ ] User-facing messages in normal mode avoid technical API/server/transport wording.
- [ ] Mini App открывается внутри Telegram.
- [ ] Контекст корректно читается из URL.
- [ ] Отображаются активные категории из bot context.
- [ ] Категории не хардкодятся во frontend.
- [ ] `single` требует ровно одну категорию.
- [ ] `selected_mix` требует минимум одну категорию.
- [ ] `all` скрывает/отключает выбор категорий и отправляет `category_ids: []`.
- [ ] `question_count=all` отправляется как `question_count: null`.
- [ ] При невалидном/отсутствующем context показывается понятная frontend-ошибка.

### C. Payload / bot validation checks
- [ ] Валидный payload `single` запускает существующий chat quiz runner.
- [ ] Валидный payload `selected_mix` запускает chat quiz runner и сохраняет выбранные категории в сессии.
- [ ] Валидный payload `all` запускает chat quiz runner.
- [ ] Невалидный JSON/payload корректно отклоняется.
- [ ] Поддельные/недоступные category IDs отклоняются.
- [ ] Категория без подходящих вопросов по сложности отклоняется.
- [ ] `web_app_data` service message best-effort удаляется.
- [ ] Первый вопрос появляется в чате с inline answer buttons.

### D. Regression checks
- [ ] `/quiz` работает без изменений.
- [ ] Кнопка `🎯 Начать викторину` в главном меню работает без изменений.
- [ ] Reply keyboard работает как раньше.
- [ ] Reading mode работает.
- [ ] `/stats` остаётся скрытым owner-only.
- [ ] После завершения квиза восстанавливается главное меню.
- [ ] DB schema changes не требуются.

### E. Mini App runner reopen/recovery checks
- [ ] После submit setup бот присылает сообщение «Викторина создана. Откройте Mini App, чтобы пройти первый вопрос.» с кнопкой WebApp.
- [ ] После submit setup первый вопрос не отправляется автоматически в чат.
- [ ] `/ui` setup запускает новую сессию.
- [ ] `/ui` показывает текущий вопрос для активной сессии.
- [ ] Отправка ответа через Mini App работает.
- [ ] После тапа по варианту выбранный ответ сразу подсвечивается, остальные варианты выглядят неактивными, и появляется спокойный pending-статус (`Проверяю ответ...` / `Отправляю ответ...`).
- [ ] После feedback текст опций остаётся читаемым (без «выцветания» disabled-текста), а selected/correct/wrong состояния визуально различимы.
- [ ] Блок feedback визуально сканируется с первого взгляда: заметный `✅ Верно` / `❌ Неверно`, читаемые строки «Ваш ответ», «Правильный ответ», «Пояснение».
- [ ] Кнопка `Далее` заметна как primary action и удобно нажимается на мобильном экране.
- [ ] Во время retry/resync UI не выглядит «зависшим»: есть понятный статус ожидания, а после завершения показывается чистый итоговый feedback без `Правильный ответ: ?`.
- [ ] Повторное открытие `/ui` показывает следующий вопрос/прогресс.
- [ ] После финального ответа повторное открытие `/ui` показывает completed result.
- [ ] Runner mode shows current question/progress without rendering setup form.
- [ ] Completed mode shows result without rendering setup form.
- [ ] Сценарии stale/duplicate кликов безопасны и дают recoverable сообщение.
- [ ] Mini App fallback подсказывает, что можно использовать классический `/quiz`.
- [ ] `/ui` при длинном текущем вопросе/опциях не падает из-за launch-context length: Mini App открывается в compact setup fallback.
- [ ] Если даже compact fallback не помещается, текст ошибки: `Викторину в окне сейчас не удалось открыть. Попробуйте /ui ещё раз или пройдите её в чате через /quiz.`

## 6) Manual QA smoke result

- Environment: production
- Mini App hosting: Cloudflare Workers Static Assets
- Custom domain: https://miniapp.librechat.online/
- Bot entry point: `/ui`
- Result: smoke passed
- Notes:
  - Mini App setup screen opens inside Telegram.
  - Active categories are displayed from bot-provided context.
  - Mini App setup can start the existing chat quiz runner.
  - Classic `/quiz` remains the default UX.
  - Questions are displayed inside Mini App runner using server-authoritative state.
  - Minor UI/polish bugs should be handled as follow-up backlog items, not as blockers for MVP smoke validation.

## 7) Deployment validation evidence template

Заполнить после ручной проверки:

- Date/time (UTC):
- Environment (prod/staging/dev):
- `MINI_APP_URL` class (например: `https://<public-host>/miniapp/index.html`, без секретов):
- Deployed commit SHA:
- Scenarios passed:
- Scenarios failed:
- Screenshots / logs links:
- Blockers / follow-ups:

## 8) Boundary / non-goals reminder
- Этот runbook не деплоит production автоматически.
- Не добавлять в репозиторий реальные секреты, private hostnames или token values.
- Не менять runtime-поведение бота в рамках docs-only readiness PR.

- [ ] Active `/ui` session with normal question shows question text + options (not progress-only).
- [ ] If progress-only fallback is used, Mini App shows: `Этот вопрос не удалось открыть в окне. Продолжите в чате через /quiz или откройте викторину заново.`

- [ ] Compact `runner_q` context renders question/options and setup form is hidden.
- [ ] Progress-only runner fallback (`compact_progress_only`) keeps setup form hidden and shows explicit limitation message.

- [ ] Active in_progress: /ui открывает текущий вопрос и в чате есть кнопка «Новый setup в Mini App».
- [ ] После ответа из Mini App пользователь возвращается в чат и получает кнопку открыть следующий шаг (/ui).
- [ ] После последнего ответа кнопка в чате ведёт к просмотру результата в Mini App.

- [ ] Active session -> New setup in Mini App shows warning: "Запуск новой викторины завершит текущую активную попытку." before submit.

- [ ] API path: answer inside Mini App advances to next question/result without closing window (`/miniapp/answer` + `/miniapp/state`).
- [ ] Force transient answer API failure/timeout shows `Сеть подвисла, пробую отправить ещё раз...`, keeps answer buttons disabled during retry, and auto-recovers on successful retry.
- [ ] При transient timeout/fetch-failure на ответ Mini App сначала делает `GET /miniapp/state` (pre-retry resync) перед следующим `POST /miniapp/answer`.
- [ ] Если первый `POST /miniapp/answer` был принят, но ответ потерялся в сети/WebView, Mini App восстанавливает UI из `runner_state` без duplicate `POST`.
- [ ] После `POST /miniapp/answer` (`_a1`) Mini App запускает ранний hedge-таймер и может выполнить `GET /miniapp/state` до полного timeout `_a1`.
- [ ] Mini App answer flow после transient recovery всё равно показывает feedback (`Верно/Неверно`, правильный ответ, пояснение) перед переходом дальше.
- [ ] Если ранний `GET /miniapp/state` показал продвижение по вопросу/сессии, Mini App восстанавливается без дублирующего `POST`.
- [ ] Если ранний `GET /miniapp/state` не показал продвижение, Mini App запускает bounded retry `POST /miniapp/answer` (`_a1/_a2/_a3`) без ожидания полного timeout первого запроса.
- [ ] If answer retries are exhausted, Mini App shows `Не удалось отправить ответ через API. Попробуйте снова.`, re-enables answer buttons, and keeps manual retry on the same question.
- [ ] Force transient setup API failure/timeout shows `Запуск не удался, повторная попытка...`, keeps setup submit disabled during retry, and auto-recovers on successful retry.
- [ ] If setup retries are exhausted, setup form remains visible, `Начать викторину` is re-enabled, and user can retry manually.
- [ ] When API + `initData` are present, timeout/failure does **not** auto-send `sendData`.
- [ ] QA confirms no disabled-button deadlock after API timeout/failure on both answer and setup paths.
- [ ] Production Mini App UI does **not** show diagnostics by default.
- [ ] Debug diagnostics are visible only when opened with `?debug=1` (or debug context flag) and remain hidden otherwise, including statuses:
  - answer: `api_attempted` / `api_success` / `retry_scheduled` / `retry_started` / `retry_exhausted` / `state_resync_attempted` / `state_resync_success` / `state_resync_failed`
  - setup: `api_attempted` / `api_success` / `retry_scheduled` / `retry_started` / `retry_exhausted`
- [ ] После открытия через primary `/ui` кнопку диагностика показывает `initData: yes`.
- [ ] Diagnostic line shows:
  - frontend version marker value
  - context mode (`setup` / `runner` / `completed` / `invalid`)
  - API configured: yes/no
  - Telegram initData present: yes/no
  - API status transitions (`not_attempted`, `attempted`, `success` or explicit fallback reason)
  - API origin only (when configured)
- [ ] If marker/diagnostics are stale or missing after deploy, close Mini App and open a fresh `/ui` button to bust Telegram WebView cache.
- [ ] Runner mode diagnostics still include:
  - API configured: yes/no
  - Telegram initData present: yes/no
  - API status transitions (`not_attempted`, `attempted`, `success` or explicit fallback reason).
- [ ] On successful API submission, no `sendData` fallback message appears and Mini App does not close.
- [ ] Server logs contain `POST /miniapp/answer` during successful in-place answer flow.
- [ ] Diagnostics never expose secrets (no raw `initData`, no authorization header/token values, no full secret-bearing URLs; origin-only is acceptable).
- [ ] Completed result screen shows a clear next action (`Новая викторина` and optional `Закрыть Mini App`).
- [ ] Clicking `Новая викторина` from completed result opens setup in the same Mini App window (without close/reopen).
- [ ] Completed `Новая викторина` can fetch setup options via authenticated `GET /miniapp/setup-options` when launch context has no categories.
- [ ] Setup submit after completed restart uses `POST /miniapp/setup` and starts a new quiz in-place.
- [ ] After completed → `Новая викторина` → new setup submit, the first question is shown and setup form is not visible below it.
- [ ] Final question flow in Mini App: answer last question → feedback (`Верно/Неверно`) → `Далее` → completed result renders once without hang/loading lock.
- [ ] Explicit close + `/ui` fallback message is shown only as a final fallback path.

## 9) Mini App API route (PR #137 hardening)
- Narrow API runs in the bot process (`MINIAPP_API_BIND`/`MINIAPP_API_PORT`) alongside long polling.
- For Mini App browser fetch, operators must expose a public HTTPS route that proxies:
  - `GET /miniapp/state`
  - `POST /miniapp/answer`
  to the bot API bind/port.
- Required env for API fetch path:
  - `MINI_APP_API_BASE_URL` (public HTTPS API base; injected into Mini App launch context)
  - `MINIAPP_API_ALLOWED_ORIGIN` (exact Mini App origin, e.g. `https://miniapp.librechat.online`)
- Optional env:
  - `MINIAPP_API_BIND` (default `127.0.0.1`)
  - `MINIAPP_API_PORT` (default `8081`)
  - `MINIAPP_API_INITDATA_TTL_SECONDS` (default `3600`)
- If `MINI_APP_API_BASE_URL` is not set, Mini App intentionally uses `sendData` fallback only.

- **Enablement gate:** set `MINIAPP_API_ENABLED=true` to start API server; default is disabled.
- If enabled but `MINI_APP_API_BASE_URL` is missing, API server is not started (safe no-start) and Mini App remains on `sendData` fallback.
- Recommended production: always set `MINIAPP_API_ALLOWED_ORIGIN` to exact Mini App origin when enabling API.
- Mini App API responses now use `HTTP/1.1` with explicit `Content-Length` on JSON responses (and `Content-Length: 0` on `OPTIONS 204`) to reduce connection churn and mobile WebView latency.
- Temporary SQLite lock/contention (`database is locked`) must return structured API response `503` with JSON `{"ok": false, "error": "database_busy_retry"}` (no raw HTML/unstructured 500).
- Mini App should treat `database_busy_retry` as transient, retry within the existing API retry/resync flow, and recover without exposing technical DB errors to normal users.
- Retry waits keep the same base backoff and add a small jitter to avoid synchronized retry bursts under contention.

- [ ] Verify setup submit uses API path and Mini App does not close when `initData` + API are available.
- [ ] Verify startup state hydrates from `GET /miniapp/state` and stale launch context is replaced.
- [ ] Verify timeout/error messages are shown and controls recover.
- [ ] Verify answer feedback shows correctness, correct option, explanation, and `Далее` transition.

- [ ] Проверить сценарий: completed → «Новая викторина» → setup остаётся на экране (авто-hydration не перерисовывает latest completed).
- [ ] Проверить, что после ответа UI показывает: «Верно/Неверно», «Ваш ответ», «Правильный ответ», пояснение (если есть), затем кнопку «Далее».
- [ ] После успешного retry статус «Ответ не отправился, повторная попытка...» исчезает и заменяется на «Ответ принят.» (или нейтральный эквивалент).
- [ ] UI никогда не показывает «Правильный ответ: ?».
- [ ] При duplicate/stale после уже принятого ответа отображается либо нормальный feedback, либо чистый resync состояния без битого текста.

- [ ] Server logs contain `POST /miniapp/setup` after setup submit in /ui API path.

## 10) Troubleshooting: `OPTIONS /miniapp/answer` = 204 but `POST /miniapp/answer` missing
- Начиная с текущей версии, Mini App для критичных `POST /miniapp/setup` и `POST /miniapp/answer` использует transport `simple_body`:
  - `Content-Type: text/plain;charset=UTF-8`
  - body: `{ init_data, request_id, payload }`
  - без `Authorization` и без `X-Miniapp-Request-Id` header
- Это снижает зависимость от CORS preflight в Telegram WebView path. Для legacy-клиентов path с `Authorization` header (`transport=header_auth`) сохранён.
- Симптом: в логах есть preflight `OPTIONS /miniapp/answer` (204), но нет `POST /miniapp/answer` для той же попытки; позже повтор может пройти с `POST /miniapp/answer` 200.
- После rollout ожидается меньше (или отсутствие) `OPTIONS` перед `POST` для актуального frontend.
- Включите debug UI (`/ui` c `?debug=1`) и проверьте:
  - `req_id` — корреляционный id из simple body (`request_id`) или legacy header;
  - `transport` — `simple_body` или `header_auth`;
  - `phase`/`final` — ключевые фазы (`preparing`, `fetch_started`, `retry_scheduled`, `retry_started`, `retry_exhausted`, `state_resync_*`, `api_success`, `ui_render_failed`);
  - `elapsed_ms`, `retry`, `attempt`;
  - `req_id` с attempt suffix (`rq_xxx_a1`, `rq_xxx_a2`, ...); в smoke-паттерне допустимо увидеть ранний `/miniapp/state` между `_a1` и `_a2`.
- Безопасность: diagnostics и логи не должны содержать raw `initData`, `Authorization`, bot token, полный профиль пользователя, текст вопроса/ответов.
- Если в debug UI есть `req_id`, но backend не видит POST c тем же `request_id`, проблема до входа запроса в API (WebView/network/proxy path между клиентом и сервером).
- Если backend видит POST c `request_id`, используйте статус/error_code и duration для локализации причины.
- Если `OPTIONS` всё ещё часто появляется, проверьте cache busting/версию `miniapp/index.html` (возможен старый cached frontend) и наличие fallback path.

Примеры grep для корреляции:
- `grep "miniapp_api endpoint=/miniapp/answer request_id=rq_ab12cd34 transport=simple_body" <bot-log-file>`
- `grep "miniapp_options endpoint=/miniapp/answer request_id=rq_ab12cd34" <bot-log-file>`

## 11) SQLite runtime hardening checks (post-deploy)
- Mini App API handlers explicitly close SQLite connections (`closing(get_connection(...))` + nested `with conn:`) to avoid lingering file locks.
- SQLite connection defaults now include:

## 12) Frontend timing diagnostics vs backend `duration_ms` (debug-only)
- Enable debug mode by opening Mini App with `?debug=1` (for `/ui` launch, append on the Mini App URL in the launch flow).
- In debug mode, `API diag` now shows:
  - frontend marker/version (`Mini App frontend: ...`) to detect stale Telegram WebView cache;
  - correlation fields: `req_id`/`setup_req_id` with attempt suffix (`_a1`, `_a2`, ...), `endpoint`, `method`, `transport`, `status`, `answer_error`;
  - phase timelines (`answer_phases`, `setup_phases`) with per-phase `elapsed_ms` and total elapsed counters.
- Expected phase sequence for healthy calls (answer/setup):
  - `request_scheduled` → `fetch_started` → `response_headers_received` → `response_body_parsed` → `state_update_started` → `state_update_applied` → `ui_render_mark`.
  - Retry flows additionally include `retry_scheduled`, `retry_started`, `retry_exhausted` (if failed).
- Correlation workflow:
  1. Copy `req_id` from debug UI (example `rq_xxx_a2`).
  2. Find matching backend log event by `request_id`.
  3. Compare client total elapsed with backend `duration_ms`.
- Interpretation:
  - backend `duration_ms` low + client total high ⇒ likely WebView/network/proxy/frontend render/retry latency.
  - backend `duration_ms` high **or** `miniapp_api_slow` present ⇒ backend/SQLite/code-path bottleneck.
- Secret-safety reminder:
  - Debug output must never include raw `initData`, `Authorization`, bot token, full request body, full profile, question text, or answer text.

## 13) FastAPI runtime notes: threadpool offload + structured latency logs
- FastAPI Mini App routes are `async`, but Mini App builders (`build_state_response`, `build_setup_options_response`, `build_setup_response`, `build_answer_response`) are synchronous and include SQLite I/O.
- To avoid ASGI event-loop blocking, these builders are intentionally executed through threadpool offload (`asyncio.to_thread(...)`) from `app/miniapp_fastapi.py`.
- Telegram bot async handlers that perform synchronous SQLite/business logic in `app/main.py` are also offloaded through `asyncio.to_thread(...)` on the bot side to keep long-polling update processing responsive.
- This preserves existing transport semantics and response contract (`(status, headers, body)` → `Response(content=body, status_code=status, headers=...)`).
- `database_busy_retry` contract remains unchanged: HTTP `503` with structured JSON `{"ok": false, "error": "database_busy_retry"}`.

### Post-deploy log visibility check (FastAPI container)
1. Run a request that should produce a fast auth failure (missing initData):
   - `curl -i http://127.0.0.1:8081/miniapp/state`
2. Check structured logs in Docker:
   - `docker compose -f docker-compose.yml logs --no-log-prefix --since 1m --timestamps psych_quiz_miniapp_api | grep -Ei 'miniapp_api endpoint=|duration_ms=|miniapp_api_slow'`

Expected signal:
- You should see a `miniapp_api endpoint=/miniapp/state ... status=401 ... duration_ms=...` line even for early returns.
- Slow requests above threshold should additionally produce `miniapp_api_slow ...` at WARNING level.

How to interpret:
- Low `duration_ms` while users still report hangs usually indicates delay outside backend handler execution (network path, Telegram WebView, proxy/CDN, or frontend state flow).
- High `duration_ms` and/or recurring `miniapp_api_slow` points to backend latency (DB contention, slow code path, or server resource pressure) and should be investigated server-side.

## 14) FastAPI Phase 1 local/dev parity run (repo-only, no production switch-over)

> ⚠️ **Local/dev only.** This section is for repository validation and manual QA on a developer machine.
>
> - It does **not** change production deployment.
> - It does **not** change CD/workflows/routing.
> - Legacy `ThreadingHTTPServer` API path remains the current production path.
> - Any production switch-over must happen in a later explicit PR.

Run FastAPI locally from the repo root with the future runtime entrypoint:

```bash
DB_PATH=/absolute/path/to/local.sqlite3 \
BOT_TOKEN=123456:dev-token \
uvicorn app.miniapp_fastapi_runtime:app --host 127.0.0.1 --port 8081
```

Runtime wiring is intentionally minimal and repo-only:

- required env: `BOT_TOKEN`, `DB_PATH`
- optional env: `MINIAPP_API_ALLOWED_ORIGIN`, `MINIAPP_API_INITDATA_TTL_SECONDS`
- the runtime entrypoint uses `create_app_from_env()` and reuses the existing `create_app(...)` + `app.miniapp_api` builders

`GET /healthz` is available for lightweight process-level health checks and returns JSON:

```json
{"ok": true, "service": "miniapp_api"}
```

For local/dev smoke validation (no real Telegram traffic required):

```bash
python scripts/smoke_miniapp_fastapi.py
```

Smoke helper checks:
- `GET /healthz`
- `OPTIONS /miniapp/answer`
- `GET /miniapp/state` without `initData` returns JSON auth error (not HTML)

For automated parity checks, use:

```bash
python -m unittest tests/test_miniapp_fastapi.py
```
  - `PRAGMA busy_timeout = 10000`
  - `PRAGMA journal_mode = WAL`
  - `PRAGMA synchronous = NORMAL`
  - `PRAGMA foreign_keys = ON`
- For file-backed DBs, side files `quiz.sqlite3-wal` and `quiz.sqlite3-shm` may appear; this is expected in WAL mode.
- Runtime performance indexes are ensured on startup for both existing and fresh DBs.

Post-deploy DB checks:
- `sqlite3 /path/to/quiz.sqlite3 "PRAGMA journal_mode;"`
- `sqlite3 /path/to/quiz.sqlite3 "PRAGMA busy_timeout;"`
- `sqlite3 /path/to/quiz.sqlite3 "SELECT name FROM sqlite_master WHERE type='index' AND name IN ('idx_quiz_sessions_user_status','idx_quiz_answers_session_question','idx_quiz_session_questions_session_order','idx_quiz_session_questions_question') ORDER BY name;"`

Post-deploy log checks:
- `grep "miniapp_db_locked endpoint=" <bot-log-file>`
- `grep "database is locked" <bot-log-file>`

## 15) Reverse proxy configuration (production API exposure)
- Mini App API process listens on local bind/port from:
  - `MINIAPP_API_BIND` (default `127.0.0.1`)
  - `MINIAPP_API_PORT` (default `8081`)
- Production HTTPS API domain `quiz-api.librechat.online` must reverse-proxy requests to this local bind/port.
- Mini App frontend origin is `https://miniapp.librechat.online`; `MINIAPP_API_ALLOWED_ORIGIN` must match this exact origin.

Example Nginx server block (reference):
```nginx
server {
    listen 443 ssl http2;
    server_name quiz-api.librechat.online;

    # TLS settings/certs are managed by infrastructure.

    location /miniapp/ {
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
}
```

Minimal operator checklist:
1. Confirm `MINIAPP_API_ENABLED=true` and correct `MINIAPP_API_BIND`/`MINIAPP_API_PORT`.
2. Configure HTTPS vhost `quiz-api.librechat.online` with reverse proxy to local API bind/port.
3. Set `MINIAPP_API_ALLOWED_ORIGIN=https://miniapp.librechat.online`.
4. Set `MINI_APP_API_BASE_URL=https://quiz-api.librechat.online`.
5. Reload Nginx and validate CORS + endpoint reachability.

Smoke checks:
- `curl -i https://quiz-api.librechat.online/miniapp/state`
- `curl -i -X OPTIONS https://quiz-api.librechat.online/miniapp/answer -H "Origin: https://miniapp.librechat.online" -H "Access-Control-Request-Method: POST"`

## 16) DB migration / upgrade policy
- `schema.sql` is source of truth for fresh database creation.
- Runtime `ensure_*` migration helpers are used for selected additive upgrades on existing DBs (for example, missing indexes/columns that can be added safely).
- Production deploy must run normal bot startup (`init_db_connection`) so runtime checks can ensure expected additive indexes exist.
- Destructive or behavior-changing migrations (drop/rewrite/backfill with risk) require explicit migration scripts + operator-approved backups/rollback plan.

Backup example for production DB file:
- `cp /data/quiz.sqlite3 /data/quiz.sqlite3.backup.$(date -u +%Y%m%dT%H%M%SZ)`

## 17) Architecture notes (planned, docs-only)
- `app/main.py` is currently overloaded and should be split in follow-up refactor PRs:
  - Move Mini App context/URL builder concerns into `app/miniapp_context.py`.
  - Split Telegram handlers by domain responsibility instead of one large module.
- Mini App API is currently implemented via `BaseHTTPRequestHandler` / `ThreadingHTTPServer`; planned medium/long-term target is migration to an ASGI service (e.g. FastAPI, Litestar, or aiohttp) with cleaner routing/lifecycle/testability.
- `miniapp/index.html` currently contains a large imperative state machine; if Mini App remains a strategic product direction, plan a declarative state-management refactor in a dedicated backlog track.

## 18) Prioritized roadmap (after #155)
- **Done / urgent:** SQLite hardening shipped in #155 (WAL, `busy_timeout`, explicit connection closing, performance indexes).
- **Next:** production validation and lock-log monitoring.
- **Near-term:** keep reverse proxy setup and DB migration policy explicit in ops/docs.
- **Medium-term:** split `app/main.py` into focused modules.
- **Backlog:** migrate Mini App API to ASGI stack + move frontend state flow to declarative model.

- If `/miniapp/answer` response is lost/delayed but `/miniapp/state` confirms answer acceptance, Mini App still shows the answer feedback card first (`✅/❌`, `Ваш ответ`, `Правильный ответ`, `Пояснение`, `Далее`) and only then advances.


## 19) FastAPI migration QA (phased)
Goal: validate phased migration from legacy `ThreadingHTTPServer` Mini App API to FastAPI + uvicorn without regressions.

### Phase 1 — repo-only implementation validation (no production switch)
- [ ] Production bot runtime behavior remains unchanged.
- [ ] `/quiz` remains fully operational in production.
- [ ] `🚀 Викторина в окне` + `/ui` continue using current production legacy Mini App API path.
- [ ] FastAPI implementation is not receiving production traffic.
- [ ] Production CD/deploy behavior is unchanged (no FastAPI enable/start in production).

### Phase 2 — production switch-over validation (separate PR)
Endpoint smoke:
- [ ] `GET /miniapp/state` works.
- [ ] `GET /miniapp/setup-options` works.
- [ ] `POST /miniapp/setup` works.
- [ ] `POST /miniapp/answer` works.

Protocol/contract checks:
- [ ] CORS behavior is correct for configured Mini App origin.
- [ ] `OPTIONS` preflight behavior is correct.
- [ ] Responses remain JSON where JSON is expected.
- [ ] HTTP framing is ASGI-correct (Content-Length when applicable and/or equivalent correct transfer framing).
- [ ] `database_busy_retry` JSON 503 contract remains unchanged.

Resilience/UX safety:
- [ ] Answer feedback recovery remains correct after transient lost response.
- [ ] Retry behavior (`_a2`/`_a3` patterns) remains controlled and does not corrupt session/score.
- [ ] No silent jump over feedback and no lost feedback card on accepted answers.
- [ ] `/quiz` remains unaffected and default.

Logs/analytics review after switch-over:
- [ ] FastAPI request counts/status/duration look normal by endpoint.
- [ ] No abnormal 4xx/5xx spike versus baseline.
- [ ] `database_busy_retry` incidence is monitored and acceptable.
- [ ] `_a2`/`_a3` retry pattern frequency is reviewed for regressions.

Operational checks:
- [ ] `psych_quiz_miniapp_api` and `psych_quiz_bot` are rebuilt/restarted by CD after switch-over changes.
- [ ] Smoke logs/metrics are reviewed before declaring rollout successful.

Rollback (if smoke fails):
- [ ] Switch route/env/reverse-proxy back to legacy Mini App API.
- [ ] Keep endpoint contracts unchanged to make rollback safe.

Suggested smoke/log commands (adjust service names for environment):
- `docker compose ps`
- `curl -fsS http://127.0.0.1:8081/healthz`
- `docker compose logs --tail=200 psych_quiz_bot | grep -E "Legacy Mini App API server is disabled|Mini App API server started"`
- `docker compose logs --tail=200 psych_quiz_miniapp_api | grep -E "Uvicorn running on|GET /healthz|POST /miniapp/"`
- Telegram smoke: `/ping`, `/quiz`, `🚀 Викторина в окне`.

## 20) Phase 2 production switch-over (bot + FastAPI split)

Failed deploy lesson learned (PR #176 rollback):
- `psych_quiz_bot` must **not** publish host port `8081`.
- `psych_quiz_miniapp_api` must be the **only** service publishing `127.0.0.1:8081:8081`.
- `docker compose ps` must show **both** runtime services: `psych_quiz_bot` and `psych_quiz_miniapp_api`.
- `curl -fsS http://127.0.0.1:8081/healthz` should return JSON with `{"ok": true, ...}`.
- Bot logs must **not** show `Mini App API server started`.
- FastAPI logs must show uvicorn/API process startup and requests.

Target runtime shape after switch-over (SQLite unchanged):
- `psych_quiz_bot` runs Telegram long polling only (`python -m app.main`).
- `psych_quiz_bot` has `MINIAPP_LEGACY_API_ENABLED=false` so legacy `ThreadingHTTPServer` is not started.
- `psych_quiz_miniapp_api` runs FastAPI/uvicorn (`uvicorn app.miniapp_fastapi_runtime:app --host 0.0.0.0 --port 8081`).
- Reverse proxy target stays stable: host `127.0.0.1:8081`.

Expected `docker compose ps` shape:
- `psych_quiz_bot` (no `127.0.0.1:8081->8081/tcp` binding)
- `psych_quiz_miniapp_api` (`127.0.0.1:8081->8081/tcp`)

Health checks:
- `docker compose exec psych_quiz_miniapp_api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8081/healthz', timeout=3).read().decode())"`
- Expect JSON: `{"ok": true, "service": "miniapp_api"}`.

Log expectations:
- Bot logs should include legacy-disable info and should **not** include `Mini App API server started on ...`.
- FastAPI logs should show uvicorn process start and requests for `/miniapp/state`, `/miniapp/setup-options`, `/miniapp/setup`, `/miniapp/answer`, `/healthz`.

Smoke checklist:
- `/ping` in bot chat.
- `/quiz` classic flow.
- Bottom menu `🚀 Викторина в окне` opens Mini App flow.
- Full 5-question Mini App run: setup → answers with feedback after each answer → result screen.

Post-switch log checks:
- 200/204 status for expected endpoint traffic.
- No abnormal 5xx spike.
- Monitor `database_busy_retry` events.
- Monitor retry suffix patterns (`_a2`, `_a3`).
- Confirm no silent jump and no lost answer feedback card.

Rollback plan:
1. Revert this switch-over PR; or
2. Re-enable legacy API in bot (`MINIAPP_LEGACY_API_ENABLED=true`) and move `127.0.0.1:8081:8081` binding back to `psych_quiz_bot` while disabling/removing `psych_quiz_miniapp_api` service.

Endpoint contracts are intentionally unchanged to keep rollback low-risk.

## FastAPI Mini App latency logs and slow-request diagnostics

The FastAPI Mini App API now emits structured request logs for all Mini App endpoints (`GET /miniapp/state`, `GET /miniapp/setup-options`, `POST /miniapp/setup`, `POST /miniapp/answer`, and `OPTIONS` preflight). Each entry includes endpoint, request id, transport, method, status, and `duration_ms`.

### Slow request threshold

Set `MINIAPP_API_SLOW_REQUEST_MS` (default `500`) to control when a request is flagged as slow.

### How to inspect logs

```bash
journalctl -u psych_quiz_miniapp_api -n 200 --no-pager | grep 'miniapp_api endpoint='
```

### How to grep slow requests

```bash
journalctl -u psych_quiz_miniapp_api --since '15 min ago' --no-pager | grep 'miniapp_api_slow'
```

### Interpretation guide

- Low backend `duration_ms` with user-visible hang usually points to network path, Telegram WebView, proxy buffering, or frontend rendering/JS timing.
- High backend `duration_ms` indicates server-side bottlenecks (DB lock contention, expensive code path, or backend compute/IO delay).

## Classic Telegram bot latency diagnostics

The bot now emits structured summary lines per classic user action in `psych_quiz_bot` logs with prefix `bot_latency`.

### How to grep

```bash
docker compose logs --tail=300 psych_quiz_bot | grep 'bot_latency'
```

Filter a specific handler:

```bash
docker compose logs --since=15m psych_quiz_bot | grep 'bot_latency handler=answer_callback'
```

### Interpretation guide

- High `db_elapsed_ms` ⇒ likely SQLite/business path latency (query/transaction/selection flow).
- High `telegram_api_elapsed_ms` ⇒ Telegram Bot API/network/client delivery latency.
- High `render_elapsed_ms` ⇒ local message preparation/formatting overhead.
- High `other_elapsed_ms` ⇒ instrumentation gap, callback dispatch, event-loop scheduling, or other unclassified overhead.
- `bot_event_loop_lag` warning (if present) ⇒ event-loop blocking or CPU pressure in bot process.
