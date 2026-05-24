# Mini App deployment and manual QA checklist (MVP)

## Purpose
Этот runbook нужен для безопасной ручной deployment-валидации Telegram Mini App setup-screen MVP из PR #117 без изменения runtime-поведения бота.

## 1) Current state
- Mini App MVP код уже в репозитории.
- Статический frontend setup-screen расположен в `miniapp/index.html`.
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
Для быстрой browser-проверки разметки setup-screen можно локально отдать файл, например:
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
- [ ] `/ui` не показывает persistent bottom WebApp reply-кнопки для Mini App (только стандартное главное меню).
- [ ] Если пользователь видит `API недоступен`, закрыть Mini App, отправить свежий `/ui` и открыть новую inline-кнопку.
- [ ] `/ui` при отсутствии активных категорий показывает no-categories fallback.
- [ ] `/ui` вне private chat корректно отклоняется.

### B. Mini App setup-screen checks
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
- [ ] Повторное открытие `/ui` показывает следующий вопрос/прогресс.
- [ ] После финального ответа повторное открытие `/ui` показывает completed result.
- [ ] Runner mode shows current question/progress without rendering setup form.
- [ ] Completed mode shows result without rendering setup form.
- [ ] Сценарии stale/duplicate кликов безопасны и дают recoverable сообщение.
- [ ] Mini App fallback подсказывает, что можно использовать классический `/quiz`.
- [ ] `/ui` при длинном текущем вопросе/опциях не падает из-за launch-context length: Mini App открывается в compact setup fallback.
- [ ] Если даже compact fallback не помещается, текст ошибки: `Mini App временно недоступен: слишком большой launch context. Используйте /quiz.`

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
  - Questions are still displayed in Telegram chat, not inside Mini App.
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
- [ ] If progress-only fallback is used, Mini App shows: `Текущий вопрос слишком большой для Mini App URL-транспорта. Продолжите этот вопрос через /quiz или откройте /ui позже.`

- [ ] Compact `runner_q` context renders question/options and setup form is hidden.
- [ ] Progress-only runner fallback (`compact_progress_only`) keeps setup form hidden and shows explicit limitation message.

- [ ] Active in_progress: /ui открывает текущий вопрос и в чате есть кнопка «Новый setup в Mini App».
- [ ] После ответа из Mini App пользователь возвращается в чат и получает кнопку открыть следующий шаг (/ui).
- [ ] После последнего ответа кнопка в чате ведёт к просмотру результата в Mini App.

- [ ] Active session -> New setup in Mini App shows warning: "Запуск новой викторины завершит текущую активную попытку." before submit.

- [ ] API path: answer inside Mini App advances to next question/result without closing window (`/miniapp/answer` + `/miniapp/state`).
- [ ] Force transient answer API failure/timeout shows `Ответ не отправился, повторная попытка...`, keeps answer buttons disabled during retry, and auto-recovers on successful retry.
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
  - `req_id` с attempt suffix (`rq_xxx_a1`, `rq_xxx_a2`, ...).
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

## 12) Reverse proxy configuration (production API exposure)
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

## 13) DB migration / upgrade policy
- `schema.sql` is source of truth for fresh database creation.
- Runtime `ensure_*` migration helpers are used for selected additive upgrades on existing DBs (for example, missing indexes/columns that can be added safely).
- Production deploy must run normal bot startup (`init_db_connection`) so runtime checks can ensure expected additive indexes exist.
- Destructive or behavior-changing migrations (drop/rewrite/backfill with risk) require explicit migration scripts + operator-approved backups/rollback plan.

Backup example for production DB file:
- `cp /data/quiz.sqlite3 /data/quiz.sqlite3.backup.$(date -u +%Y%m%dT%H%M%SZ)`

## 14) Architecture notes (planned, docs-only)
- `app/main.py` is currently overloaded and should be split in follow-up refactor PRs:
  - Move Mini App context/URL builder concerns into `app/miniapp_context.py`.
  - Split Telegram handlers by domain responsibility instead of one large module.
- Mini App API is currently implemented via `BaseHTTPRequestHandler` / `ThreadingHTTPServer`; planned medium/long-term target is migration to an ASGI service (e.g. FastAPI, Litestar, or aiohttp) with cleaner routing/lifecycle/testability.
- `miniapp/index.html` currently contains a large imperative state machine; if Mini App remains a strategic product direction, plan a declarative state-management refactor in a dedicated backlog track.

## 15) Prioritized roadmap (after #155)
- **Done / urgent:** SQLite hardening shipped in #155 (WAL, `busy_timeout`, explicit connection closing, performance indexes).
- **Next:** production validation and lock-log monitoring.
- **Near-term:** keep reverse proxy setup and DB migration policy explicit in ops/docs.
- **Medium-term:** split `app/main.py` into focused modules.
- **Backlog:** migrate Mini App API to ASGI stack + move frontend state flow to declarative model.
