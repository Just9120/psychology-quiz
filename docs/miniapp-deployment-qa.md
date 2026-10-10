# Mini App deployment and manual QA checklist

## Итоговый приватный репозиторий (D-45)

Пока идёт разработка, основной репозиторий остаётся PUBLIC ради Actions. Уточнение владельца06.10: не переносить PRIVATE transition или подготовку нового VPS deploy key на текущий этап. Сейчас visibility и Git access не меняются; private Vault notes остаются локально вне Git. Смена visibility относится к окончанию разработки, не к prerequisite текущего PR/merge/CD. Target будущей базы — vault/ единого Just9120/psychology-quiz; существующий отдельный репозиторий сохраняется.

Для финального перехода позднее потребуется проверить authenticated VPS Git read access и actual private visibility, сохранив canonical origin/deployment unit и mandatory host verification. Current preflight06.10: VPS origin HTTPS/github.com, credential helper отсутствует, HEAD3c10221. Это не достаточное доказательство отсутствия всех способов authentication и не поручение менять remote/ключи сейчас. Local GitHub metadata read подтвердил admin/push права, existing deploy keys0; новых keys/visibility mutations не выполнено.

## Действующие правила и delivery snapshot

[AGENTS.md](../AGENTS.md) задаёт routine Git/PR/delivery flow; [ci-cd-rules.md](../ci-cd-rules.md) — настройку и исправление pipeline. Продуктовый target — [spec](project-spec.md); AC/findings/checkpoint — [план](delivery-plan.md). Текущая production БД — PostgreSQL; её подтверждённый cutover и primary records указаны в [плане](delivery-plan.md), а backup/recovery и штатный CD — в [PostgreSQL storage](postgres-storage.md). Ниже сохранены также исторические процедуры Telegram/SQLite, которые применяются лишь к соответствующей среде/версии. Поставка PWA — в [PWA procedure](pwa-delivery.md).

Процедура первоначально введена в PLATFORM-STABILIZATION-001 на base `df383200fd0e6c389038f5b080ec23310a26be07`. Её прежний `PENDING` относился к тому checkpoint, а не к текущей поставке. Действующие CI/CD records и runtime-версию сверяйте по [плану](delivery-plan.md) и primary GitHub/VPS records; исторические результаты ниже действуют только для названных ими версий.

| Поверхность | Контракт / ограничение |
| --- | --- |
| CI | [ci.yml](../.github/workflows/ci.yml): PR к main, push main, manual; Ubuntu/Python 3.12, contents:read, cancellation по workflow/ref. Canonical pytest запускает все unittest/pytest cases, Docker compose contract, deployment failure scenarios; validators/init/seed/parity и whitespace по actual base..HEAD. |
| Проверяемая revision | PR — default merge ref, после merge — main push SHA. Не считать PR head и merge tree одним commit. CD требует успешный последний push CI именно candidate SHA; более поздний failed/in-progress run запрещает reuse старого green. |
| Gates/review | GitHub readback07.10.2026: `main` только через PR, required `pwa-client` и `validate-and-smoke-test` (GitHub Actions app15368), strict/up-to-date base; required approvals0, enforce_admins=true, force/delete запрещены. [main payload](../deploy/github-main-protection.json) сохраняет выбранную конфигурацию. Дождаться опубликованных checks/self-review; bypass не допускается. |
| CD trigger/permissions | [deploy-production.yml](../.github/workflows/deploy-production.yml): successful trusted main push CI через workflow_run либо manual main с тем же exact-CI gate. contents:read/actions:read; actions pinned SHA; PR/fork source не получает SSH credentials. Production Environment: custom branch policy только `main`, без reviewer/wait timer; [environment payload](../deploy/github-production-policy.json), readback07.10.2026. Это GitHub Environment доставки существующего production runtime, не отдельный вариант продукта. |
| Target / unit | Существующий checkout `/opt/psychology-quiz`, origin Just9120/psychology-quiz, main; Docker default context, Compose project `psychology-quiz`, services `psych_quiz_bot` + `psych_quiz_miniapp_api`. Существующие container labels/Running сверяются до изменения; несовпадение блокирует, не разрешает bootstrap. Host/user — existing DEPLOY_HOST/DEPLOY_USER; values UNSET в документации, не выводить. |
| Config owner | Runtime host `.env` обслуживает владелец VPS; routine CD не добавляет keys и не заменяет values. Repository Secrets DEPLOY_SSH_KEY/DEPLOY_KNOWN_HOSTS задают доступ/host identity. Ответственный за rotation персонально UNSET. Compose задаёт revision и выключает legacy API в bot. |
| Очередь / выбор версии | production-deploy concurrency без cancel; host flock ждёт до 60 s, затем FAIL. Только 40-character SHA, совпадающий с origin/main на момент fetch; stale candidate завершается без поставки. Host checkout clean, merge только ff-only. Никогда reset --hard/down/remove-orphans/prune. |
| Artifact identity | CI собирает exact backend image по candidate SHA; [backend promotion](#backend-image-promotion) переносит тот же image с проверкой ZIP/image digest, revision/platform и running container image IDs. VPS runtime больше не выполняет build. Python base image закреплён digest, runtime/search Python dependencies — hash-locked. Search build использует [Debian snapshot](../deploy/search-debian.sources) с датой 20.09.2026 и обязательными archive signatures; его реальную сборку/imports проверяет applicable CI. Конфигурация promotion не доказывает живую поставку до CI/CD records; повторную сборку binary побайтово идентичной не заявлять. |
| Static frontend | Telegram Mini App: React/TS/Vite source `pwa/miniapp-app` + `pwa/src/miniapp`, проверенная сборка `miniapp-react/` и отдельная Cloudflare Git integration/Worker psychology-quiz-miniapp; после PR нужны asset/provider check. Самостоятельная PWA: тот же production CD, trusted main CI artifact и atomic release на VPS по [PWA procedure](pwa-delivery.md). |
| Stateful class | Обычный code-only release — NONE. Schema/seed/content DB release этой Goal — BACKWARD_COMPATIBLE_AUTOMATED; Для первой поставки без прежнего image SHA обязательны backup rehearsal/user preservation; init/seed выполняются только при соответствующем source diff, не из-за отсутствия label. Stateful script останавливает оба writer services, создаёт backup, репетирует restore отдельно, затем init/seed и проверяет сохранность всех прежних user fields. |
| Backup / recovery | [deployment_db.py](../scripts/deployment_db.py): SQLite backup API в private `/data/backups/release-*/quiz.sqlite3`; restore во временный файл, integrity/FK и fingerprint users/sessions/answers/literature. До migrations failure запускает только прежние containers. После начала migration/post-check failure — stop продвижения и forward-fix; production restore/volume cleanup не автоматизированы. Retention/удаление backups — отдельная maintenance задача. |
| Обязательные post-checks | Проверка DB serving questions/options, всех attempt snapshot hashes и canonical parity, неизменности user state для stateful release, [internal HTTP smoke](../scripts/deployment_http_smoke.py) `/healthz` с expected SHA и unauthenticated `/miniapp/state` → 401; затем обе службы Running и image revision. `DEPLOY_OK revision=...` допустим только после всех checks. Bot Telegram roundtrip не входит в read-only smoke. |

Routine entrypoint — [deploy.sh](../deploy.sh), переданный по verified SSH из validated candidate с positional expected SHA, incoming PWA ZIP/digest и backend ZIP/digest. Оба artifacts выбираются из successful trusted main CI той же revision и актуальной попытки required jobs. Параметры формирует existing CD, ручная передача не нужна. SSH сначала читает полный script в аргумент bash -c, чтобы stdin дочернего процесса не забрал оставшийся код; workflow требует exact completion marker и `PWA_DELIVERY_OK`. Не запускать старую host-копию script: checkout обновляется внутри candidate procedure. Docs-only change синхронизирует source без runtime restart/static activation и сообщает отдельно SOURCE_SYNC_OK/runtime_unchanged. Frontend-only change публикует PWA после проверки совместимого backend без его restart. Повторный deploy ради статуса не нужен: читать CI/CD records.

При failure записать run ID, candidate SHA и последний успешно пройденный этап. Не начинать следующий PR до завершения применимой поставки. Если службы остановлены после migration failure, сначала сверить backup, DB integrity/user preservation и совместимость; обычная процедура намеренно требует существующие Running services и не является обходом recovery gate. Production restore или изменение target требует отдельного решения. Read-only runtime smoke не доказывает authenticated/mobile UX или нагрузочную устойчивость.

Изменение файлов content затрагивает live read-only bind при checkout; массовый content rollout этой Goal не разрешён. Для такого scope отдельно проверить окно совместимости и [content rollout](question_bank_content_rollout.md). Эта процедура не закрывает все operational findings.

## Purpose
Этот runbook нужен для безопасной ручной deployment-валидации Telegram Mini App runner без изменения runtime-поведения бота.

## 1) Current state
- Mini App MVP код уже в репозитории и включает post-UX-polish product-facing setup/question/result screens.
- Статический React frontend собирается в `miniapp-react/index.html`; прежний `miniapp/index.html` остаётся legacy reference, не является активным Cloudflare assets directory.
- UX polish loop #207–#211 completed; current delivery posture is observation/manual QA when no reproducible bugs are present.
- Бот открывает Mini App URL через `MINI_APP_URL` (опциональная env-переменная).
- Классический `/quiz` остаётся дефолтным UX.
- Mini App запускается opt-in через `/ui` и нижнюю кнопку `🚀 В окне`.
- `/ui` и `🚀 В окне` открывают setup/contour chooser даже при активном normal quiz runner; warning о завершении активной попытки остаётся ожидаемым.
- Первый экран chooser baseline включает три контура: `Тесты по темам`, `Глоссарий`, `Литература`.
- Chat `📚 Глоссарий` / `/glossary` остаётся Telegram chat glossary quiz, не Mini App chooser.
- Mini App API — dedicated FastAPI service `psych_quiz_miniapp_api`; bot service `psych_quiz_bot` не является production-serving процессом Mini App API.
- Static Mini App frontend hosting remains separate/operator/static hosting.
- `/stats` остаётся скрытой owner-only командой только для private chat.

## 2) Hosting requirement
- `miniapp-react/index.html` должен быть опубликован по **HTTPS**.
- URL должен быть доступен из Telegram-клиентов (mobile/desktop).
- Production URL задаётся в `MINI_APP_URL` окружении бота.
- `MINI_APP_URL` не должен содержать секретов.
- Production hosting для Mini App assets выполняет отдельная Cloudflare Git integration, а не `deploy.sh`/`docker-compose.yml`.

## 3) Configuration checklist

### Trusted frontend API configuration

[React Mini App API client](../pwa/src/miniapp/api.ts) фиксирует deployment-owned API destination. URL context (`api_base_url`) не является доверенной конфигурацией и не используется для отправки initData. API routes ограничены allowlist, credentials-in-URL не передаются, redirects отклоняются. Для другого development/staging backend нужен явный deployment config change, не параметр ссылки. [Старый config](../miniapp/api-config.js) относится только к legacy frontend. Credentials в docs/fixtures не добавлять.

После frontend delivery проверить опубликованный `miniapp-react/index.html`, его versioned JS/CSS assets, provider check и UI load. Component/API tests проверяют trusted fetch boundary без network. Browser smoke без Telegram показывает экран запуска; это не authenticated mobile roundtrip.

### Cloudflare Workers Static Assets (GitHub deployment flow)
- Build command: `npm --prefix pwa ci --ignore-scripts`; устанавливает инструменты по `pwa/package-lock.json`, не пересобирает проверенные tracked assets
- Deploy command: `npm --prefix pwa run deploy:miniapp`; использует локальный pinned Wrangler и root `wrangler.toml`
- Path: `/`
- Static assets directory in `wrangler.toml`: `./miniapp-react`

`miniapp-react/` собирается из pinned frontend dependencies и сверяется с tracked
assets в CI до merge. Не заменять deploy command на bare `npx wrangler`: при
отсутствии root package установка может получить незакреплённую версию. Владелец
подтвердил эти значения и production branch `main` в dashboard 08.10.2026;
их применение подтверждает успешный build `7e0122b9-5f9a-46f7-86d2-50c92beb26b1`.
На 10.10 main build `b0030a9a-1df3-416f-b4f6-d254f4993399` успешен;
проверенные assets соответствуют поставленной версии. Это Evidence указанных
поставок, а не гарантия неизменности внешних настроек после проверки. Актуальные
revision, primary records и ограничения доступа — в [плане](delivery-plan.md#окружения-и-delivery-facts-read-only1010).

1. Опубликовать `miniapp-react/index.html` и его assets на HTTPS static hosting в deployment environment.
2. После готовности Cloudflare custom domain установить `MINI_APP_URL` на этот HTTPS URL в runtime `.env` на VPS.
3. Перезапустить/передеплоить intended runtime service set (`psych_quiz_bot` и `psych_quiz_miniapp_api`), чтобы env/код подхватились где применимо.
4. Проверить в Telegram, что `/ui` показывает кнопку открытия Mini App (при наличии активных категорий).
5. По возможности в staging/dev отдельно проверить fallback-поведение `/ui`, когда `MINI_APP_URL` отсутствует.

### Optional local sanity check (не заменяет Telegram QA)
Для быстрой browser-проверки разметки runner можно локально отдать файл, например:
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
- [ ] После `/start` в нижнем меню видна кнопка `🚀 В окне`.
- [ ] Кнопка нижнего меню `🚀 В окне` отправляет свежий launch-сценарий через `/ui` (бот присылает новую inline WebApp-кнопку `🚀 Открыть викторину`).
- [ ] `/ui` and `🚀 В окне` open setup/contour chooser even when a normal quiz runner is active.
- [ ] If a normal quiz runner is active, the new-quiz warning remains visible before setup submit.
- [ ] First Mini App setup/chooser screen includes `Тесты по темам` and `Глоссарий`.
- [ ] Chat `📚 Глоссарий` / `/glossary` still opens the chat glossary quiz, not the Mini App chooser.
- [ ] Кнопка `🚀 В окне` не использует persistent WebApp URL в reply keyboard (stale launch context не хранится).
- [ ] `/ui` не показывает persistent bottom WebApp reply-кнопки для Mini App (только стандартное главное меню).
- [ ] Если пользователь видит `API недоступен`, закрыть Mini App, отправить свежий `/ui` и открыть новую inline-кнопку.
- [ ] `/ui` при отсутствии активных категорий показывает no-categories fallback.
- [ ] `/ui` вне private chat корректно отклоняется.

### B. Mini App runner checks
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

### C. Post-UX-polish Mini App smoke checklist
- [ ] `/ui` opens Mini App via fresh inline WebApp button.
- [ ] Setup/contour chooser screen renders cleanly and includes `Тесты по темам` and `Глоссарий`.
- [ ] `single` allows one topic.
- [ ] `selected_mix` allows multiple topics.
- [ ] `all` hides topics and starts without category selection.
- [ ] Disabled start explains missing input.
- [ ] Answer cards are readable and not double-numbered.
- [ ] Correct feedback does not duplicate `Правильный ответ`.
- [ ] Wrong feedback shows `Ваш ответ` and `Правильный ответ`.
- [ ] Final screen is product-facing and neutral.
- [ ] `Новая викторина` works.
- [ ] Close action works when available.

### D. Payload / bot validation checks
- [ ] Валидный payload `single` запускает существующий chat quiz runner.
- [ ] Валидный payload `selected_mix` запускает chat quiz runner и сохраняет выбранные категории в сессии.
- [ ] Валидный payload `all` запускает chat quiz runner.
- [ ] Невалидный JSON/payload корректно отклоняется.
- [ ] Поддельные/недоступные category IDs отклоняются.
- [ ] Категория без подходящих вопросов по сложности отклоняется.
- [ ] `web_app_data` service message best-effort удаляется.
- [ ] Первый вопрос появляется в чате с classic answer controls according to configured mode (recommended production: bottom reply keyboard; fallback: inline answer buttons).

### E. Classic reply keyboard production smoke
- [ ] Enable `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=true` in the target environment.
- [ ] Restart the affected services/containers.
- [ ] Run `/quiz` in Telegram classic chat UX.
- [ ] Answer 10–15 questions via the bottom Telegram reply keyboard, including the `Далее` action.
- [ ] Verify there are no long inline-callback-style hangs and the chat stays cleaner because answer controls do not remain attached to quiz messages.
- [ ] Check only safe logs/metrics: `classic_text_answer_ingress`, `classic_text_answer_latency`, `classic_text_next_ingress`, `classic_text_next_latency`; latency lines include deterministic `status` and `latency_bucket` fields.
- [ ] Roll back if needed by setting `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=false` and restarting services.

### F. Regression checks
- [ ] `/quiz` работает без изменений as the default classic Telegram chat entry point.
- [ ] Кнопка `🎯 Начать` в главном меню работает без изменений.
- [ ] Reply keyboard работает как раньше.
- [ ] Reading mode работает.
- [ ] `/stats` остаётся скрытым owner-only.
- [ ] После завершения квиза восстанавливается главное меню.
- [ ] DB schema changes не требуются.

### G. Mini App runner reopen/recovery checks
- [ ] После submit setup бот присылает сообщение «Викторина создана. Откройте Mini App, чтобы пройти первый вопрос.» с кнопкой WebApp.
- [ ] После submit setup первый вопрос не отправляется автоматически в чат.
- [ ] `/ui` setup opens the setup/contour chooser and can launch a new session.
- [ ] `/ui` and `🚀 В окне` do not default to showing the current question when used as primary entrypoints; runner/result reopen links remain valid after setup/answer where applicable.
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
  - Mini App setup/contour chooser screen opens inside Telegram.
  - Active categories are displayed from bot-provided context.
  - Mini App setup can start the question runner and glossary contour through the existing Mini App API endpoints.
  - Classic `/quiz` remains the default UX.
  - Questions are displayed inside Mini App runner using server-authoritative state.
  - No current UI/polish blockers are recorded here. Treat new UI/polish notes as observation/manual QA findings unless they are reproducible bugs with clear scope.

## 7) Deployment validation evidence template

Заполнить после ручной проверки:

- Date/time (UTC):
- Environment (prod/staging/dev):
- `MINI_APP_URL` class (проверенный HTTPS entrypoint текущего Mini App build, без секретов):
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
- [ ] После `POST /miniapp/answer` (`_a1`) Mini App запускает ранний hedge-таймер примерно на 1 секунду и может выполнить `GET /miniapp/state` до полного timeout `_a1`.
- [ ] Mini App answer flow после transient recovery всё равно показывает feedback (`Верно/Неверно`, правильный ответ, пояснение) перед переходом дальше.
- [ ] Если ранний `GET /miniapp/state` показал продвижение по вопросу/сессии, Mini App восстанавливается без дублирующего `POST`.
- [ ] Если ранний `GET /miniapp/state` не показал продвижение, Mini App запускает bounded retry `POST /miniapp/answer` (`_a1/_a2/_a3`) без ожидания полного timeout первого запроса; в debug-telemetry ожидаются `hedged=true`, `winner_attempt=2`, `hedge_delay_ms=1000` и `hedge_started_ms` около 1000 мс, если победил hedge/retry.
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

## 9) Mini App API route
- Production Mini App API runs as the dedicated FastAPI service `psych_quiz_miniapp_api`, separate from `psych_quiz_bot` long polling.
- For Mini App browser fetch, operators must expose a public HTTPS route that proxies to the FastAPI bind/port.
- Production Mini App API endpoints include:
  - `GET /miniapp/state`
  - `GET /miniapp/setup-options`
  - `POST /miniapp/setup`
  - `POST /miniapp/answer`
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
- Если `OPTIONS` всё ещё часто появляется, проверьте cache busting/версию опубликованного `miniapp-react/index.html` и наличие fallback path; `miniapp/index.html` — legacy reference.

Примеры grep для корреляции:
- `grep "miniapp_api endpoint=/miniapp/answer request_id=rq_ab12cd34 transport=simple_body" <bot-log-file>`
- `grep "miniapp_options endpoint=/miniapp/answer request_id=rq_ab12cd34" <bot-log-file>`

## 11) SQLite runtime hardening checks (post-deploy)
- Mini App API handlers explicitly close SQLite connections (`closing(get_connection(...))` + nested `with conn:`) to avoid lingering file locks.
- SQLite WAL mode is enabled during startup/init (`init_db_connection`) for file-backed databases, not on every regular connection; ordinary `get_connection(...)` calls avoid connection-time journal mode changes.
- SQLite connection defaults now include `PRAGMA busy_timeout = 10000`, `PRAGMA synchronous = NORMAL`, and `PRAGMA foreign_keys = ON`.

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

## 14) FastAPI local/dev parity run

> ⚠️ **Local/dev only.** This section is for repository validation and manual QA on a developer machine.
>
> - It does **not** change production deployment.
> - It does **not** change CD/workflows/routing.
> - Production already uses the dedicated FastAPI service; this section is only for local parity checks and does not imply deploy changes.

Run FastAPI locally from the repo root with the runtime entrypoint:

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
  - Startup/init enables `PRAGMA journal_mode = WAL` once for file-backed databases.
  - Regular connections configure `PRAGMA busy_timeout = 10000`, `PRAGMA synchronous = NORMAL`, and `PRAGMA foreign_keys = ON` without changing journal mode.
- For file-backed DBs, side files `quiz.sqlite3-wal` and `quiz.sqlite3-shm` may appear; this is expected in WAL mode.
- SQLite startup сохраняет compatibility helpers для performance indexes; PostgreSQL startup только проверяет schema/version/catalog. Создание и обновление PostgreSQL indexes выполняются явной миграцией до запуска writers по [PostgreSQL procedure](postgres-storage.md).
- Repeated user loads should not update `users.updated_at` unless Telegram profile fields (`username`, `first_name`, `last_name`) changed; this keeps read-like bot and Mini App flows from taking avoidable SQLite write locks.
- Mini App answer timeout remains longer than hedge timing (`ANSWER_API_TIMEOUT_MS = 8000`, `ANSWER_HEDGE_DELAY_MS = 1000`). The answer hedge still waits briefly before attempt 2 and performs state-resync first, but it now recovers from a stalled first WebView/fetch attempt in roughly 1 second instead of roughly 3 seconds. If debug telemetry shows `attempt=2`, `hedged=true`, `winner_attempt=2`, and `pre_request_ms`/`hedge_started_ms` roughly equal to the hedge delay while backend logs have no matching `_a1` `miniapp_api` line, interpret it as the first frontend/WebView fetch attempt likely stalling before it reached backend; the `_a2` backend `duration_ms` should then represent the successful hedged request.

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

### 15.1) Telegram webhook experiment route
For the controlled Telegram webhook-delivery experiment, reuse the production HTTPS vhost and add an exact webhook route. The bot container listens on `TELEGRAM_WEBHOOK_LISTEN=0.0.0.0` / `TELEGRAM_WEBHOOK_PORT=8090`, while Compose publishes only `127.0.0.1:8090:8090` on the host, keeping direct public access closed.

```nginx
location = /telegram/webhook {
    proxy_pass http://127.0.0.1:8090/telegram/webhook;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 30s;
}
```

Experiment runtime env values, with secrets redacted:
- `TELEGRAM_UPDATE_MODE=webhook`
- `TELEGRAM_WEBHOOK_URL=https://quiz-api.librechat.online/telegram/webhook`
- `TELEGRAM_WEBHOOK_LISTEN=0.0.0.0`
- `TELEGRAM_WEBHOOK_PORT=8090`
- `TELEGRAM_WEBHOOK_SECRET_TOKEN=<redacted-random-long-secret>`

Rollback is only `TELEGRAM_UPDATE_MODE=polling`, followed by the standard two-service restart.

Smoke checks:
- `curl -i https://quiz-api.librechat.online/miniapp/state`
- `curl -i -X OPTIONS https://quiz-api.librechat.online/miniapp/answer -H "Origin: https://miniapp.librechat.online" -H "Access-Control-Request-Method: POST"`

## Identity v1 для PWA

`scripts/init_db.py` запускает [identity-v1](../app/identity_schema.py) в отдельной SQLite transaction: existing `users.id` остаётся learning actor, `telegram_user_id` становится nullable UNIQUE. Runtime requests не перестраивают users. Миграция сохраняет все значения columns, IDs, indexes/triggers и AUTOINCREMENT high-water mark; FK check до/после, rollback при ошибке и повторный запуск проверены `tests/test_identity_schema.py`. Неизвестная legacy declaration отказывается мигрировать; не исправлять её вручную без reconciliation.

Класс изменения для текущего Telegram-only rollout: BACKWARD_COMPATIBLE_AUTOMATED, до появления web users; нет удаления пользовательских данных. Target и writers — существующий `/opt/psychology-quiz`, Compose `psychology-quiz`, bot/API. Обязательны stop writers, backup с isolated restore, init/seed, полный prior-user fingerprint/snapshot/parity и post-checks из таблицы выше. `app/identity_schema.py` входит в stateful classifier. После начала migration failure требует сверки DB/backup и forward-fix; production restore не автоматизирован. После появления web identities rollback к Telegram-only schema несовместим и не допускается без отдельного плана. PWA credentials/session tables и включение web routes поставляются отдельными следующими этапами; эта migration их не включает.

## 16) DB migration / upgrade policy
- [SQLite schema](../sql/schema.sql) используется canonical [init](../scripts/init_db.py) для SQLite. Этот же init явно применяет identity/auth/glossary/learning/homework/privacy/reading migrations; legacy `ensure_*` helpers в SQLite startup не заменяют этот шаг.
- Действующий production использует PostgreSQL: init вызывает ordered `upgrade_schema`, а `init_db_connection` при старте вызывает только `verify_schema`. Не рассчитывайте на создание PostgreSQL таблиц, колонок или indexes при старте приложения.
- Для stateful изменений [deploy](../deploy.sh) под штатной lock останавливает оба writer-сервиса, подтверждает backup/isolated restore, выполняет init/seed, проверяет сохранность прежнего user state и только затем запускает проверенную версию. Точный version/catalog, поддержанные исходные схемы и recovery описаны в [PostgreSQL procedure](postgres-storage.md).
- Неизвестная схема, failed migration или расхождение preservation не допускают продолжения поставки. После начала миграции нет автоматического data restore/application rollback; необходима сверка recovery record и согласованный forward-fix либо отдельное recovery-решение. Destructive изменения требуют явного разрешения.

Для действующей production SQLite с WAL используйте SQLite backup API и isolated restore rehearsal из [DB checks](../scripts/deployment_db.py), вызываемые штатным [deploy](../deploy.sh). Простое копирование основного файла не является принятой backup procedure.

## 17) Historical architecture notes (planned at that time)
- `app/main.py` is currently overloaded and should be split in follow-up refactor PRs:
  - Move Mini App context/URL builder concerns into `app/miniapp_context.py`.
  - Split Telegram handlers by domain responsibility instead of one large module.
- Mini App API production serving is now the dedicated FastAPI/uvicorn service `psych_quiz_miniapp_api`; legacy in-bot `ThreadingHTTPServer` notes are historical only.
- Старый `miniapp/index.html` содержит imperative state machine, но активный Telegram Mini App собирается из React-кода в `pwa/`; отдельный refactor старого файла не является текущим условием поставки.

## 18) Historical roadmap (after #155; superseded by project-spec)
- **Done / urgent:** SQLite hardening shipped in #155 (WAL, `busy_timeout`, explicit connection closing, performance indexes).
- **Next:** production validation and lock-log monitoring.
- **Near-term:** keep reverse proxy setup and DB migration policy explicit in ops/docs.
- **Medium-term:** split `app/main.py` into focused modules.
- **Backlog:** consider moving frontend state flow to a declarative model in a dedicated track.

- If `/miniapp/answer` response is lost/delayed but `/miniapp/state` confirms answer acceptance, Mini App still shows the answer feedback card first (`✅/❌`, `Ваш ответ`, `Правильный ответ`, `Пояснение`, `Далее`) and only then advances.


## 19) Dedicated FastAPI Mini App API production QA
Goal: validate the current dedicated FastAPI/uvicorn Mini App API service without regressions.

Baseline checks:
- [ ] Production bot runtime behavior remains unchanged.
- [ ] `/quiz` remains fully operational in production.
- [ ] `🚀 В окне` + `/ui` use the dedicated production Mini App API service.
- [ ] `psych_quiz_miniapp_api` receives Mini App API traffic.
- [ ] Production CD/deploy recreates both runtime services when app runtime changes.

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

Logs/analytics review after deploy:
- [ ] FastAPI request counts/status/duration look normal by endpoint.
- [ ] No abnormal 4xx/5xx spike versus baseline.
- [ ] `database_busy_retry` incidence is monitored and acceptable.
- [ ] `_a2`/`_a3` retry pattern frequency is reviewed for regressions.

Operational checks:
- [ ] `psych_quiz_miniapp_api` and `psych_quiz_bot` are rebuilt/restarted by CD after runtime changes.
- [ ] Smoke logs/metrics are reviewed before declaring rollout successful.

Rollback (if smoke fails):
- [ ] Revert the faulty runtime/deploy change or use an explicit rollback task.
- [ ] Keep endpoint contracts unchanged to make rollback safe.

Suggested smoke/log commands (adjust service names for environment):
- `docker compose ps`
- `curl -fsS http://127.0.0.1:8081/healthz`
- `docker compose logs --tail=200 psych_quiz_bot | grep -E "Legacy Mini App API server is disabled|Mini App API server started"`
- `docker compose logs --tail=200 psych_quiz_miniapp_api | grep -E "Uvicorn running on|GET /healthz|POST /miniapp/"`
- Telegram smoke: `/ping`, `/quiz`, `🚀 В окне`.

## 20) Production runtime shape (bot + FastAPI split)

Failed deploy lesson learned (PR #176 rollback):
- `psych_quiz_bot` must **not** publish host port `8081`.
- `psych_quiz_miniapp_api` must be the **only** service publishing `127.0.0.1:8081:8081`.
- `docker compose ps` must show **both** runtime services: `psych_quiz_bot` and `psych_quiz_miniapp_api`.
- `curl -fsS http://127.0.0.1:8081/healthz` should return JSON with `{"ok": true, ...}`.
- Bot logs must **not** show `Mini App API server started`.
- FastAPI logs must show uvicorn/API process startup and requests.

Target runtime shape (SQLite unchanged):
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
- Bottom menu `🚀 В окне` opens Mini App flow.
- Full 5-question Mini App run: setup → answers with feedback after each answer → result screen.

Post-deploy log checks:
- 200/204 status for expected endpoint traffic.
- No abnormal 5xx spike.
- Monitor `database_busy_retry` events.
- Monitor retry suffix patterns (`_a2`, `_a3`).
- Confirm no silent jump and no lost answer feedback card.

Rollback plan:
1. Revert the runtime/API change being validated; or
2. Use an explicit rollback task/runbook before moving API serving back to the legacy bot process, because production source of truth is the dedicated `psych_quiz_miniapp_api` service.

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


## Production Telegram webhook operating mode

Production may run the classic Telegram bot in webhook mode after HTTPS termination by Nginx. Use only secret-free environment documentation in the repository:

```dotenv
TELEGRAM_UPDATE_MODE=webhook
TELEGRAM_WEBHOOK_URL=https://quiz-api.librechat.online/telegram/webhook
TELEGRAM_WEBHOOK_LISTEN=0.0.0.0
TELEGRAM_WEBHOOK_PORT=8090
TELEGRAM_WEBHOOK_SECRET_TOKEN=<secret>
```

Port `8090` must remain loopback-only on the Docker host, for example `127.0.0.1:8090:8090`, with public traffic reaching it only through the Nginx `location = /telegram/webhook` reverse proxy. Do not publish the webhook listener on a public interface.

Rollback knob:

```dotenv
TELEGRAM_UPDATE_MODE=polling
```

After changing the update mode, restart the bot service and verify the startup diagnostic (`bot_update_mode mode=webhook` or `bot_update_mode mode=polling`). Existing bot diagnostics such as `bot_update_ingress`, `bot_handler_start`, `bot_latency`, `bot_latency_slow`, and `bot_event_loop_lag` should remain visible. Third-party HTTP client INFO logs should not be used for Telegram Bot API tracing because request URLs can contain `BOT_TOKEN`.

If `BOT_TOKEN` was exposed in logs, rotate the token manually via BotFather and update the production environment secret. Token rotation is an operational action; do not store replacement tokens in code, docs, commits, or pasted logs.

## Classic Telegram bot latency diagnostics

For production classic reply keyboard observation (`CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=true`), watch the text-update logs first: `classic_text_answer_ingress`, `classic_text_answer_latency`, `classic_text_next_ingress`, and `classic_text_next_latency`. Ingress lines confirm that a numeric answer or `Далее` reached the bot for an active session; latency lines include safe IDs plus `elapsed_ms`, deterministic `latency_bucket` (`lt_100ms`, `lt_500ms`, `lt_1000ms`, `gte_1000ms`), and `status` values such as `accepted`, `invalid_input`, `duplicate`, `stale_question`, `ignored_repeated_input`, or `ok`. These lines intentionally omit Telegram payloads, answer text, option text, question text, profile names, `initData`, tokens, and webhook secrets.

The bot also emits three low-noise diagnostics around classic user actions in `psych_quiz_bot` logs:

- application-level update ingress with prefix `bot_update_ingress`;
- specific handler start with prefix `bot_handler_start`;
- completion summary with prefix `bot_latency`.

`bot_update_ingress` is logged from an early, generic update handler before specific callback/message handlers. It includes only safe metadata such as `update_id`, `update_type`, `telegram_user_id`, `message_kind`, and a redacted `callback_prefix`; it must not include raw callback payloads or message text.

### How to grep

```bash
docker compose logs --tail=300 psych_quiz_bot | grep -E 'classic_text_(answer|next)_(ingress|latency)|bot_update_ingress|bot_handler_start|bot_latency'
```

Compare handler start and completion lines together:

```bash
docker compose logs --since=15m psych_quiz_bot | grep -E 'bot_update_ingress|bot_handler_start|bot_latency'
```

Filter a specific handler:

```bash
docker compose logs --since=15m psych_quiz_bot | grep -E 'callback_prefix=ans|handler=answer_callback'
```

Example ingress/start/done triplet:

```text
bot_update_ingress update_id=987654 update_type=callback_query callback_prefix=ans telegram_user_id=123
bot_handler_start handler=answer_callback phase=handler_start callback_prefix=ans telegram_user_id=123 session_id=456
bot_latency handler=answer_callback phase=handler_done status=ok elapsed_ms=42 db_elapsed_ms=8 render_elapsed_ms=1 telegram_api_elapsed_ms=27 other_elapsed_ms=6 callback_prefix=ans telegram_user_id=123 session_id=456
```

### Interpretation guide

- `tap -> bot_update_ingress late -> bot_handler_start immediate -> bot_latency low` ⇒ Telegram delivery, long polling, client, or network delay before application-level processing.
- `tap -> bot_update_ingress quick -> bot_handler_start late` ⇒ dispatcher queue/backpressure or handler routing delay inside the bot process before the specific handler starts.
- `tap -> bot_handler_start quick -> bot_latency high` ⇒ backend handler delay or Telegram Bot API await delay.
- `bot_latency_slow` ⇒ backend-side slow handler requiring investigation.
- High `db_elapsed_ms` ⇒ likely SQLite/business path latency (query/transaction/selection flow).
- High `telegram_api_elapsed_ms` ⇒ Telegram Bot API/network/client delivery latency.
- High `render_elapsed_ms` ⇒ local message preparation/formatting overhead.
- High `other_elapsed_ms` ⇒ instrumentation gap, callback dispatch, event-loop scheduling, or other unclassified overhead.
- `bot_event_loop_lag` warning (if present) ⇒ event-loop blocking or CPU pressure in bot process.

## Mini App client telemetry smoke (PR #201)

Client-side telemetry is opt-in and hidden by default. Use it only for operator diagnostics when a Telegram WebView user reports that the Mini App appears to hang.

### How to run the smoke

1. Open the Mini App URL with `?debug=1` appended (preserve the existing `context` parameter). Example shape: `https://miniapp.librechat.online/?debug=1&context=...`.
2. Tap a user action that performs an API request, for example choose an answer, tap `Далее` until an answer is available, or start a new quiz from setup.
3. In the debug panel, copy the `request_id` from the latest telemetry row for `answer`, `setup`, `state`, or `setup_options`.
4. Compare that `request_id` with backend API logs from `psych_quiz_miniapp_api`:

```bash
docker compose logs --since=15m psych_quiz_miniapp_api | grep 'miniapp_api' | grep '<request_id>'
```

Backend `miniapp_api` lines include the safe `request_id`, endpoint, method, status, and backend `duration_ms`. The client request also sends `X-Miniapp-Request-Id` so header-auth GETs and simple-body POSTs can be correlated without logging Telegram init data, question text, answer text, or secrets.

### How to interpret the client row

The debug panel shows the latest safe rows as `action request_id request_ms parse_ms render_ms total_ms status`:

- High `request_ms` means the delay is on the frontend-to-API path: network, Nginx/API, Cloudflare/frontend path before the API request reaches the backend, or backend response delivery.
- Low backend `duration_ms` for the same `request_id` but high frontend `total_ms` means the backend is fast and the remaining delay is likely Telegram WebView, frontend JavaScript, rendering, proxy buffering, or client UI update.
- A large gap before `request_start` (visible in console as `pre_request_ms`) means the Mini App JavaScript/UI froze before the network request began.
- High `parse_ms` points to JSON body parsing or a WebView main-thread stall immediately after response receipt.
- High `render_ms` points to DOM rendering or WebView paint/update delay after the JSON was parsed.

### Remaining ops experiment

Because `miniapp.librechat.online` is Cloudflare-proxied while `quiz-api.librechat.online` appears to be direct Nginx, a remaining production experiment is to temporarily bypass Cloudflare for the Mini App frontend (or publish an equivalent non-proxied frontend hostname) and compare debug rows for the same user action. If `request_ms` and `total_ms` improve only on the bypassed frontend while backend `duration_ms` remains low, Cloudflare/frontend caching/proxy/WebView interaction remains a likely contributor. This experiment should not change classic Telegram callback routing or production DNS permanently in this PR.


## Owner content dashboard

PWA «Содержание» использует только owner session и CSRF через `POST /web/owner/content`.
Другим аккаунтам, anonymous requests и Telegram clients operational API недоступен.
Клиент не задаёт actor или путь к файлу. Обзор только читает approved bank, опубликованный
каталог глоссария и библиографию; personal learning rows не читает и не меняет.
Отсутствующий вопрос определённого вида — подтверждённый пустой раздел банка,
а достаточность количества не оценивается без предметного критерия. Неизвестные
термины/Obsidian notes показываются как неподтверждённые, а не как нулевое покрытие.

Source processing summary готовится оператором из полного private inventory и выбранного
private processing snapshot. Canonical команда, cwd root репозитория:

```bash
python scripts/owner_source_summary.py --current data/current-inventory.json \
  --processed data/current-processing.json --observed-at "$INVENTORY_OBSERVED_AT" --reviewed \
  --output data/owner-source-summary-candidate.json
```

При необходимости добавьте `--private-registry data/reviewed-source-registry.json` к этой же команде с `--reviewed`. Дополнение должно быть непустым ignored private JSON в `data/`, принадлежащим оператору; corpus root должен совпадать, дубликаты source IDs отклоняются. Оно влияет только на coverage агрегата, не меняет публичный registry, processing states или разрешения публикации. Дисциплинарный глоссарий не становится источником отдельной лекции без подтверждённой связи.

Пути здесь обозначают проверенные operator inputs; не создавайте пустые файлы вместо них.
`INVENTORY_OBSERVED_AT` — подтверждённое время metadata-наблюдения с timezone,
а не время запуска команды. Output создаётся только новым ignored `data/*.json`;
существующий файл не перезаписывается. В него входят counts, дата наблюдения и время
подготовки; тексты, названия, Drive IDs, locators и reviewer identities не переносятся.
Даже полный inventory не доказывает полный semantic review: summary сохраняет `PARTIAL`,
известные holds учитываются отдельно от pending records. Поздние потерянные review
records остаются неизвестными; этот файл не является разрешением публикации.

После проверки схемы, readback и отсутствия приватных полей разрешённая сводка включается
в `content/owner-source-summary.json`. Она содержит только дату, counts и identifiers
уже публичных тем, без source IDs, текстов, locators и operator identities. Git, runtime
artifact и обычный CD поставляют её вместе с той же revision приложения; отдельный SFTP
перенос не требуется. Приватные inputs остаются в ignored `data/`.
`OWNER_SOURCE_SUMMARY_PATH` позволяет явно выбрать operator snapshot вместо поставляемой
сводки; default — `/app/content/owner-source-summary.json`. Явный отсутствующий или
невалидный override не заменяется встроенной сводкой. Не передавайте raw review JSON.
Отсутствующий/невалидный snapshot возвращает UNSET, без исключения приватного текста.
Обзор показывает дату и ограничение актуальности, не объявляет старый snapshot текущим
состоянием Drive. Изменение snapshot не меняет auth gates, банк или пользовательские данные.


`--reviewed` включает только проверенные registry/curriculum edges и допущенные
publication gate вопросы текущего checkout. Привязка требует совпадения ID и
`item_sha256`; новая формулировка со старым ID остаётся вне lesson coverage.
Snapshot хранит counts по публичным lesson IDs, состояние metadata/review и known hold;
Drive ID/locator не переносит. API повторно проверяет вложенные counts и использует
только текущие публичные lesson/discipline названия. Неизвестные термины/Obsidian notes
не превращаются в нули. Цифры lesson coverage относятся к snapshot, а не к живому DB
запросу. Обновление текущего банка само по себе не обновляет ignored snapshot.


При наличии проверенного private note manifest добавьте `--notes-manifest` с
ignored input, допустимым для canonical Obsidian exporter. Это operator-only
проверка подготовки: exporter source/revision/digest/hold/link gates выполняются
до подсчёта. Lesson получает note count только при exact source ID/revision/hash
совпадении с curriculum; остальные notes считаются отдельно как unmapped.
В API/summary попадают только числа и `notes_state=PREPARED`, без note IDs,
названий, body, source IDs, locators или reviewer. Runtime не импортирует Vault.

Число 0 означает отсутствие notes для этой темы в переданном manifest, а не
отсутствие личных заметок в Vault. `PREPARED` не означает export, private GitHub
publication, opening smoke или полноту базы. Без manifest сохраняются
`notes=null`/`UNSET`; stale/conflicted inputs дают отказ вместо прежнего PASS.
Отдельные glossary terms по lessons этим флагом не классифицируются.

## Backend image promotion

Основной backend image собирается единожды для candidate revision в `validate-and-smoke-test`:
`Dockerfile`, hash-locked requirements и pinned base image. PR CI проверяет build/import/package;
только trusted `push main` публикует `backend-<SHA>` в Actions artifacts. Package содержит
`manifest.json` и `image.tar.gz`; его identity — revision, `linux/amd64`, Docker image ID и
SHA-256 compressed image. CI artifact retention — 7 дней, как для PWA; это не retention
личных backups. Prod secrets, `.env`, host `data/`, `.postgres/` и private search inputs не
входят в Dockerfile COPY или Docker context. Образ не требует нового external registry.

[Backend artifact procedure](../scripts/backend_artifact.py) переиспользует exact trusted
main CI/run/attempt selection из PWA delivery. Проверки перед SSH и после transfer:
required jobs успешны, artifact принадлежит backend producer window, не expired,
GitHub digest/ZIP layout/manifest/image bytes совпадают. Fork/PR artifacts не являются
production inputs. Процедура не запускает workflow ради получения статуса.

На VPS под прежним deployment lock сначала проверяются archive/digest, target
Docker platform и loaded image ID/revision. Runtime services используют один
`psychology-quiz-runtime:<SHA>` с разными commands и `pull_policy: never`;
production script не вызывает `compose build` и не устанавливает dependencies.
Отсутствующий backend artifact блокирует runtime поставку до stop/backup/migration;
fallback к host rebuild не предусмотрен. Docs/frontend-only flow сохраняет прежний
runtime и не требует загрузки image. Ручной старый трёхаргументный вызов для runtime
недостаточен — штатный CD передаёт все пять аргументов.

Backup/isolated restore, stateful migration, user preservation, serving parity,
HTTP/PWA smoke и exact completion markers сохраняются. После запуска revision label
и фактический container image ID обоих сервисов должны совпасть с проверенным CI image.
До публикации PWA и completion marker read-only `scripts/runtime_exposure.py` проверяет каждый runtime container: project/service/revision, running state, единственную owned Compose bridge network и фактические/requested bindings только на 127.0.0.1:8090/8081. Public wildcard, дополнительные опубликованные порты, host/чужие сети останавливают поставку. PostgreSQL ports/network/storage проверяются существующим postgres_vps image-state/verify. Guard не меняет firewall/container/network и не выводит raw Docker inspection с environment secrets. Failure сохраняет действующие recovery gates; автоматического удаления или data rollback нет.
Ошибка после миграции не запускает автоматический data rollback; действуют прежние
forward-fix/recovery gates. Исторический snapshot этого раздела не применял GitHub protections; актуальная policy применена07.10.2026 и описана в действующей таблице выше.
Actual Docker build, GitHub artifact provenance и VPS promotion требуют CI/CD evidence;
адресные fake-boundary checks не заменяют живые records.

## Search image build inputs

[Dockerfile.search](../Dockerfile.search) использует закреплённый Python image с Debian Trixie и [подписанный Debian snapshot](../deploy/search-debian.sources). Base suite и отсутствие иных apt sources проверяются до установки `libgomp1`; неизвестный новый источник останавливает build. Historic Release expiry отключён только в этих двух snapshot stanzas, проверки подписи и archive keyring сохранены. Timestamp зафиксирован вместе с Dockerfile; обновление базового image или системных пакетов требует согласованного обновления snapshot и applicable CI build/import check. Обычный `apt-get update` не выбирает текущую версию из mutable mirror. Версии wheels и модели задаются существующими lockfiles/модельной identity; эта фиксация не разрешает установку приватного индекса или включение RAG.


## Isolated user recovery with current content

Подготовленная operator-процедура проверяет восстановление личного состояния
из существующего verified native backup независимо от новой редакции serving
content. Она не восстанавливает данные поверх production, не меняет `.env`,
не переключает database target и не запускает/останавливает runtime services.
Входной backup и его verified record остаются неизменными; private search index
не восстанавливается и пересобирается своей отдельной процедурой.

Рабочий каталог — `/opt/psychology-quiz`, environment — root VPS operator с
известным target и текущим candidate application image. Для отдельного ручного запуска требуется
согласованное окно с остановленными обоими writers; процедура проверяет это,
но не останавливает их сама. После процедуры writers остаются в исходном
состоянии. Запуск не является обычным smoke check на работающем production.

При штатной PostgreSQL stateful поставке, которая меняет schema/content,
`deploy.sh` выполняет тот же rehearsal автоматически после verified backup,
под inherited delivery lock и до изменения production schema/content.
Используется уже существующее stopped-writer окно. Возвращённый owned record
и `USER_RECOVERY_OK` подтверждают successful candidate-content rebuild и
сохранность personal state в изолированной копии; запись остаётся приватной.
При failure live migration, PWA publish и `DEPLOY_OK` не выполняются. Если DB
ещё не менялась, существующий pre-migration recovery возвращает прежние
containers; после начала image transition сохраняется прежний stop/reconcile
flow. Новый автоматический restore production или переключение DB не добавлен.
Non-migration runtime/docs updates дополнительный rehearsal не запускают.

`EXPECTED_SHA` — проверенный текущий checkout/candidate image; `VERIFIED_RECORD`
— обычный приватный `record.json` внутри `.postgres/backups/` с неизменённым
`database.dump`. Старую revision backup допускают только при совпадении
project/database/service/cluster. Неизвестный target, неверный checksum,
несовместимая schema или отсутствие места останавливают действие.

```bash
python3 scripts/postgres_vps.py rehearse-user-recovery   --expected-sha "$EXPECTED_SHA" --record "$VERIFIED_RECORD" </dev/null
```

Под штатным delivery lock процедура создаёт новый owned
`psychology_restore_<random>` database и восстанавливает в него snapshot.
Сначала exact manifest должен совпасть с backup record. Затем тот же
проверенный candidate image выполняет canonical `scripts/init_db.py` и
`scripts/seed_questions.py` с target override только на этот owned database.
Publication gates не обходятся. Personal tables, identity sequences и import
provenance сверяются с исходным snapshot; новая reading schema допускает только
ранее рассчитанную безопасную derivation. Исходная production БД проверяется
на неизменность независимо от восстановленного snapshot.

Успех подтверждает `phase=verified` в возвращённом приватном
`.postgres/recovery-rehearsals/rehearsal-*/record.json`; временная owned database
удалена. Запись содержит hashes/manifests и identity, без DSN или текстов
учебных ответов. Этот результат доказывает rehearsal на конкретной revision,
а не разрешает реальное переключение production на старую историю.

При failure не переключать production и не изменять backup. Сохранить record.
`restore_cleanup=removed` означает cleanup подтверждённой owned копии;
`pending` или `creation_unconfirmed_inspect_owned_name` требуют сверки точного
имени/owner перед recovery. Не удалять database по одному совпадению prefix.
Rehearsal не восстанавливает удалённую после backup историю автоматически;
выбор snapshot и reconciliation более новых данных требуют отдельного решения.

Validation: адресные failure/ownership tests
`tests/test_postgres_user_recovery.py`; required native CI scenario
`tests/postgres/test_recovery.py::test_native_restored_history_survives_current_content_rebuild`
проверяет реальные `pg_dump`/`pg_restore`, две legacy schema revisions,
canonical content update и сохранение attempt snapshots. Local synthetic PASS
не заменяет native CI и фактический operator rehearsal. Retention/RPO/RTO
остаются UNSET до решения владельца.

### Unreleased lesson coverage in the owner summary

From the repository root, optional `--private-topics data/<topics>.json` requires `--reviewed --private-registry data/<registry>.json`. Both inputs pass the existing private ignored-file and exact source/revision gates. Unreleased lesson names and bindings stay in operator storage; the owner client receives only total, processing counts, current metadata count and known holds. Metadata classification does not grant derivative publication or index approval. The public curriculum and published lesson rows remain authoritative.


## Переход Mini App на согласованный hostname

PWA остаётся psy.cloud-nodes.net; Mini App переходит с miniapp.librechat.online на miniapp.psy.cloud-nodes.net; API hostname не меняется. Владелец уже добавил оба production Custom Domains к существующему Worker. Новая frontend страница должна открываться по HTTPS до переключения runtime. Старую привязку пока не удалять: прежние Telegram-кнопки содержат прежний адрес.

После успешного CI → merge → CD новой revision выполните на VPS из `/opt/psychology-quiz` одну процедуру: `bash scripts/miniapp_domain_cutover.sh EXPECTED_MERGE_SHA`, подставив фактический поставленный merge SHA. [Процедура](../scripts/miniapp_domain_cutover.sh) проверяет target, revision, image и текущие службы, берёт штатную deploy lock, сохраняет private `.env` backup в root-only record и через [config helper](../scripts/miniapp_domain_config.py) меняет только MINI_APP_URL и MINIAPP_API_ALLOWED_ORIGIN. Последний принимает конечный список двух точных origins; response отражает только совпавший origin, чужому origin разрешение не выдаётся. Telegram initData/auth остаётся обязательным.

Повторный запуск без необходимости не требуется. Процедура пересоздаёт только bot/API с уже поставленным image; БД, PWA, прочие env values и OAuth не изменяются. Post-checks: exact revision/readiness/auth boundary, оба разрешённых origins и запрещённый контрольный origin, новый URL в контейнере, обе службы Running. Итог `MINIAPP_DOMAIN_OK` подтверждает runtime/config; owner Telegram launch проверяет личный roundtrip. При failure восстанавливается сохранённый config только если после cutover владелец его не изменил; затем прежняя конфигурация пересоздаётся и проверяется. При concurrent edit автоматический restore останавливается и сохраняет record для recovery.

Новые кнопки `/ui` используют MINI_APP_URL; уже отправленные кнопки не переписываются. Процедура сохраняет существующий root path `/` и query parameters ссылки, меняя только известный HTTPS origin; произвольный hostname/path, credentials и fragment отклоняются. Фиксированная причина validation failure выводится без значений `.env`; прочие ошибки показывают только тип. Если отдельный Main Mini App URL или menu button был настроен владельцем в BotFather, его внешняя настройка не управляется этой процедурой: укажите там новый hostname, сохранив старый Worker domain на время перехода.
