# psychology-quiz

`psychology-quiz` — репозиторий PsychologyAtlas. Согласованная цель — учебная платформа с PWA, тестами, повторением, прогрессом и source-backed учебными материалами. Требования и AC находятся в [спецификации](docs/project-spec.md), состояние реализации — в [плане](docs/delivery-plan.md).

Текущая реализация — Telegram-бот и Mini App на Python/FastAPI, а также самостоятельный PWA quiz client на React/TypeScript/Vite. Owner PWA опубликована на `psy.cloud-nodes.net`; доступ и поставка описаны в [PWA procedure](docs/pwa-delivery.md), текущая приёмка — в [плане](docs/delivery-plan.md#завершённая-goal--pwa-first-001). Backend поддерживает SQLite и PostgreSQL; [процедура переноса](docs/postgres-storage.md) сохраняет user state и включает verified backup/restore. Фактический cutover требует operator records. pgvector/search остаются отдельным scope.

Текущее состояние продукта:
- **Module 1** — стабильный baseline, 296 approved questions across five active topics.
- **Module 2** — ограниченный рабочий scope, 171 approved questions across two active topics.
- **Module 3** — первая активная категория `Психологическое консультирование`, 108 approved questions.
- Активный банк вопросов: 575 approved questions в JSON source-of-truth under `content/questions/**/*.json`.

Бот по умолчанию работает в режиме **long polling**; production также может работать в validated webhook mode за конфиг-флагом. Самостоятельный Web UI находится в [pwa](pwa/); Telegram Mini App остаётся opt-in UX внутри Telegram. Внешняя генерация вопросов во время работы (RAG/retrieval) отсутствует.

## Переменные окружения

Обязательные/основные runtime-переменные:
- `BOT_TOKEN`
- `BOT_USERNAME` (опционально)
- `APP_ENV` (по умолчанию `dev`)
- `LOG_LEVEL` (по умолчанию `INFO`)
- `DB_PATH` (по умолчанию `/data/quiz.sqlite3`)
- `DATABASE_URL` — приватный PostgreSQL URI; непустое значение имеет приоритет над `DB_PATH`, без fallback при ошибке. Commands/ownership/cutover — в [storage procedure](docs/postgres-storage.md).

Telegram update delivery mode:
- `TELEGRAM_UPDATE_MODE` — `polling` или `webhook`; по умолчанию `polling`.
- `TELEGRAM_WEBHOOK_URL` — публичный HTTPS URL webhook endpoint; обязателен только при `TELEGRAM_UPDATE_MODE=webhook`.
- `TELEGRAM_WEBHOOK_LISTEN` — локальный listen host для webhook сервера python-telegram-bot; обязателен только в webhook mode.
- `TELEGRAM_WEBHOOK_PORT` — локальный listen port для webhook сервера python-telegram-bot; обязателен только в webhook mode.
- `TELEGRAM_WEBHOOK_SECRET_TOKEN` — secret token для Telegram webhook header; не логируется и должен задаваться только как секрет окружения.
- `CLASSIC_QUIZ_SEND_NEXT_AS_NEW_MESSAGE` — экспериментальный UX-флаг для classic quiz: при `true` кнопка «Дальше» отправляет следующий вопрос новым сообщением вместо редактирования предыдущего; по умолчанию `false`.
- `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE` — recommended production classic chat UX: при `true` ответы и действие «Далее» идут обычными Telegram text message updates через bottom reply keyboard вместо inline callback-кнопок; production smoke подтвердил 15 classic quiz questions без hangs. При `false` сохраняется legacy/fallback inline callback mode; env default не меняется.

Дополнительно для owner-only аналитики:
- `ADMIN_TELEGRAM_IDS` (опционально) — список numeric Telegram user id через запятую.
  Пример: `ADMIN_TELEGRAM_IDS=123456789,987654321`

Команда `/stats` скрыта из публичного меню/списка команд и доступна только owner-пользователям из `ADMIN_TELEGRAM_IDS` в личном чате.

Кратко по конфигурации:
- `BOT_TOKEN` — обязательный.
- `MINI_APP_URL` — опциональный; включает экспериментальный opt-in Telegram Mini App runner (`/ui`).
- `ADMIN_TELEGRAM_IDS` — опциональный список numeric Telegram user id через запятую для owner-only команд (например, `/stats`).

## Telegram update delivery mode: polling vs webhook

Production can run in either long polling or webhook mode. Long polling remains the default runtime mode, while webhook mode is an optional infrastructure/runtime configuration guarded by environment flags.

Правила повседневной работы, проверок и поставки находятся в [AGENTS.md](AGENTS.md), проектные deployment/manual QA процедуры — в [Mini App deployment / QA](docs/miniapp-deployment-qa.md). [ci-cd-rules.md](ci-cd-rules.md) применяется при настройке CI/CD и исправлении pipeline.

## CI/CD and deployment model

Repository-visible GitHub Actions are split by responsibility:
- open PR and merge approved changes to `main`;
- CI validation runs on pull requests, pushes to `main`, and manual `workflow_dispatch`;
- routine delivery follows [AGENTS.md](AGENTS.md) and [project procedures](docs/miniapp-deployment-qa.md); workflow/settings changes require their own authorized scope;
- CI must not deploy, access production SSH, or mutate production runtime state;
- deployment/CD uses Repository Secrets and the configured target environment; after merge, verify deployed commit/runtime state when deployment matters;
- тот же production CD публикует PWA из проверенного main CI artifact: общий VPS lock, backend checks, atomic static activation и public smoke; порядок, selection и recovery — в [PWA procedure](docs/pwa-delivery.md);
- docs-only changes do not require runtime sync. The existing CD workflow still triggers on every push to `main`; this is observed behavior, not a requirement to deploy documentation.


## Быстрый старт и проверки

Рабочий каталог — корень репозитория. Runtime/CI: Python 3.12, package manager — pip; прямые зависимости фиксирует [requirements.txt](requirements.txt), transitive lockfile отсутствует. Для локальной работы используйте изолированное Python-окружение; команды ниже предполагают, что оно активировано.

Карта: [app](app/) — bot/API/domain code, [miniapp](miniapp/) — текущая статика, [content](content/) — производный учебный контент, [sql](sql/) — SQLite/PostgreSQL schemas, [scripts](scripts/) — init/seed/validators, [tests](tests/) — pytest suite (включая unittest cases). Entrypoints: [bot](app/main.py) и [FastAPI](app/miniapp_fastapi_runtime.py). Generated audit JSON в docs/audits — прежнее Evidence, не source of truth.

Общий quiz backend: [quiz_service](app/quiz_service.py) задаёт setup/state/answer/feedback для проверенного `users.id`; [quiz_runner](app/quiz_runner.py) — переходы попытки. Telegram API проверяет initData отдельно; `miniapp_runner` сохраняет совместимые imports для bot. [Identity migration](app/identity_schema.py) выполняется через canonical init command, сохраняет legacy данные и допускает пользователей без Telegram. Процедура production migration — в [runbook](docs/miniapp-deployment-qa.md#identity-v1-для-pwa).

```bash
pip install -r requirements.txt
python -m compileall app scripts
python scripts/validate_questions.py
python scripts/validate_topics.py
python scripts/validate_glossary.py
python scripts/validate_literature.py
python scripts/validate_learning_reviews.py
# Bash: один временный DB_PATH для init, seed и локального запуска
export DB_PATH=/tmp/quiz-local.sqlite3
python scripts/init_db.py
python scripts/seed_questions.py
git diff --check
python -m app.main
```

`DATABASE_URL`, если задан, имеет приоритет над `DB_PATH`; перед SQLite quickstart убедитесь, что он пуст. PostgreSQL init/import и test target — в [storage procedure](docs/postgres-storage.md).

PowerShell: вместо Bash export задайте `$env:DB_PATH = Join-Path $env:TEMP 'quiz-local.sqlite3'`; остальные Python-команды те же. Используйте отдельную тестовую БД. Init/seed берут approved fixtures из content; production data не нужны. Для bot/API нужен тестовый BOT_TOKEN, для validators и DB smoke он не нужен. Значения env имеют приоритет над .env согласно [config](app/config.py); Docker Compose дополнительно задаёт service overrides в [compose](docker-compose.yml).

| Назначение | Canonical команда / условие |
| --- | --- |
| Behavioral suite | `python -m pip install -r requirements-dev.txt`, затем `python -m pytest -q`; временные/in-memory DB внутри tests. Frontend security regression требует Node.js без npm dependencies; Docker compose contract требует Docker CLI (локально иначе skip; в CI обязателен) |
| Выбранная suite | `python -m pytest tests/test_miniapp_frontend_contract.py -q` для frontend/docs contracts; выбирайте другие существующие test modules по diff |
| FastAPI local run | `python -m uvicorn app.miniapp_fastapi_runtime:app --host 127.0.0.1 --port 8081`; тот же тестовый DB_PATH/BOT_TOKEN; подробности в [runbook](docs/miniapp-deployment-qa.md) |
| Python format / lint / typecheck | N/A: отдельных команд нет; whitespace проверяет `git diff --check`. Frontend typecheck — ниже |
| Python build | N/A отдельная компиляция; runtime image собирает действующая Docker delivery procedure |

Для ручной проверки сложности есть приватный **read-only** отчёт `python -m scripts.report_difficulty_evidence` из корня репозитория. До запуска задайте `DATABASE_URL` либо `DB_PATH` для известной БД в process environment; если указан PostgreSQL URI, он имеет приоритет. Команда не создаёт SQLite-файл, не меняет `difficulty` и выводит только агрегаты по редакциям: число первых ответов независимых пользователей, долю ошибок и 95% интервал Уилсона. Повторные ответы одного пользователя и неподтверждённые legacy snapshots исключены; интервал не устраняет смещение состава обучающихся. Для production отчёт содержит историю пользователей в агрегированном виде и должен оставаться приватным operator output, без публикации raw JSON в CI/artifacts.

Базовые local services — SQLite и FastAPI; live Telegram smoke требует тестовый bot/client. PostgreSQL runtime и проверки описаны в [PostgreSQL storage](docs/postgres-storage.md); production cutover подтверждён в E-PG-09 [плана](docs/delivery-plan.md). pgvector остаётся отдельным optional scope. Яндекс 360 требуется для реального PWA onboarding; synthetic suite использует test mailbox. CI запускает Python behavioral suite и frontend checks; ограничения — в плане.

Owner PWA auth backend поставляется выключенным по умолчанию. Переменные, API contract, mail/session/linking policy и условия включения — в [PWA auth](docs/pwa-auth.md). Новые credentials не заменяют Telegram initData в прежних routes.

## PWA local run и проверки

Рабочий каталог `pwa/`; Node **22.23.1**, npm **12.0.2**, [package-lock.json](pwa/package-lock.json). Установите Python dependencies в отдельное окружение по командам выше.

```bash
npm ci --ignore-scripts
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

`build` включает `typecheck`; отдельно доступны `npm run typecheck` и `npm run icons` (SVG → checked-in PNG). Format/lint scripts пока N/A, whitespace — корневой `git diff --check`. Linux без browser dependencies: `npx playwright install --with-deps chromium`.

Browser tests сами поднимают изолированный backend на loopback 8085 и production preview на 4173; оба порта должны быть свободны. `python` должен указывать на выбранное окружение; иначе задайте `PWA_TEST_PYTHON` абсолютным путём к interpreter (PowerShell: `$env:PWA_TEST_PYTHON = '...'`). Используются только synthetic DB/mail/owner; внешние сервисы не нужны.

Для ручного preview: из `pwa/` запустите `python tests/backend.py`, во втором терминале `npm run preview`. Synthetic owner `owner@example.test`, пароль `A synthetic browser passphrase`; это публичные тестовые данные, не production credentials. Открывайте loopback 127.0.0.1, порт 4173. Backend не сохраняет данные между запусками. Для разработки исходников `npm run dev` использует 5173; реальному dev API задайте matching `PWA_ORIGIN`, loopback exception и отдельную DB согласно [PWA auth](docs/pwa-auth.md), порт API 8085. Synthetic harness намеренно разрешает origin только preview 4173.

[Клиент, caching и artifact identity](docs/pwa-client.md); [auth/API и конфигурация](docs/pwa-auth.md); [подготовленные static release/Nginx/smoke процедуры](docs/pwa-delivery.md). Existing Mini App и его Cloudflare target не заменяются новой PWA.

## Текущий продуктовый контур

Активные категории в продукте формируются из БД по `approved`-вопросам (не хардкодятся в UI).

Содержательно:
- Module 1: рабочий baseline по основным дисциплинам — **296 approved**.
- Module 2: активные рабочие темы — **`Основы экспериментальной психологии`** (**118 approved**) и **`Качественные методы исследования`** (**53 approved**).
- Module 3: первая активная категория — **`Психологическое консультирование`** (**108 approved**).

## Режимы викторины (UX v2)

Поддерживаются три режима запуска:
- `Конкретная тема`
- `Микс из выбранных тем`
- `Все темы`

Краткий сценарий:
- `Конкретная тема` → выбор одной категории → выбор количества вопросов → первый вопрос.
- `Микс из выбранных тем` → мультивыбор категорий → `Готово` / `Сбросить` → выбор количества вопросов → первый вопрос.
- `Все темы` → выбор количества вопросов → первый вопрос.

По умолчанию используются все уровни сложности. На экране количества кнопка «Настроить сложность (необязательно)» позволяет выбрать фильтр, затем количество. Фильтр не меняет difficulty metadata вопросов по ответам пользователя. Кнопки ранее отправленных сообщений сохраняют свой сценарий.

Для режима `Микс из выбранных тем` выбранный набор категорий сохраняется на уровне сессии.

## Поток данных: JSON → seed → SQLite

- Первичные учебные знания — согласованный Drive corpus; JSON в репозитории — canonical approved derivative для runtime банка.
- Новый/изменённый published derivative требует review точного content/source fingerprint. Библиография не подтверждает содержание книги; legacy baseline не объявляется source-certified. [Контракт публикации](docs/question_bank_content_rollout.md#проверка-происхождения-и-публикация) действует для quiz, glossary и literature.
- Рабочие директории банка:
  - `content/questions/module1/`
  - `content/questions/module2/`
  - `content/questions/module3/`
- SQLite **не** является source of truth; это runtime layer хранения и выдачи данных.
- Заполнение и обновление SQLite выполняется сидером `scripts/seed_questions.py`: полный sync снимает approval с non-approved/отсутствующих IDs без удаления истории. Quiz attempts сохраняют immutable question/options snapshot; legacy backfill явно помечен как доступная текущая редакция. Контракт и recovery — в [content rollout](docs/question_bank_content_rollout.md).

Runtime sync for JSON/content changes is deployment-environment-specific. Repository-visible CI validates question-bank syntax and seedability, but does not deploy or mutate runtime SQLite. When deployment matters, verify deployed commit/runtime state in the target environment after merge; docs-only changes do not require runtime sync.

Операционные процедуры находятся в [deployment / QA](docs/miniapp-deployment-qa.md) и [content rollout](docs/question_bank_content_rollout.md); правила работы агента — в [AGENTS.md](AGENTS.md). Настройка pipeline регулируется [ci-cd-rules.md](ci-cd-rules.md).

## Вспомогательный UX

- постоянная клавиатура reply keyboard в личном чате: `🎯 Начать` / `🚀 В окне`, `👁 Чтение` / `📚 Глоссарий`, `ℹ️ Помощь`, `🙈 Скрыть меню`
- classic `/quiz` остаётся дефолтным Telegram chat entry point
- `📚 Глоссарий` / `/glossary` opens a glossary test/quiz mode backed by static `content/glossary/*.json`, not a reference dictionary; it includes `Качественные методы исследования` and `Основы экспериментальной психологии` and uses the same bottom-button numeric answer style as the classic chat quiz
- для production classic chat UX рекомендуется `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=true`: ответы и «Далее» отображаются в нижней Telegram reply keyboard и приходят в бот как обычные text message updates, поэтому сообщения викторины не засоряются inline-кнопками
- production smoke для reply keyboard mode: пользователь завершил 15 classic quiz questions без hangs
- recent UX polish loop завершён для меню/`/start`/`/help`, Reading Mode, classic feedback/final screen и Mini App setup/result screens; текущая posture — observation/manual QA без immediate code PR при отсутствии багов
- legacy/fallback classic inline callback mode остаётся доступен при `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=false`
- ручное скрытие меню через `🙈 Скрыть меню`
- во время активной викторины меню скрывается без отдельного уведомления
- после завершения викторины итоговый результат автоматически возвращает главное меню
- резервное восстановление через `/start`
- режим чтения: `Обычный` / `Бионическое чтение`


## Telegram Mini App (experimental note)

- PWA входит в согласованный target scope; текущий Mini App остаётся отдельным Telegram-клиентом.
- Telegram Mini App доступен как экспериментальный opt-in UX mode внутри Telegram: через `/ui` или через кнопку нижнего меню `🚀 В окне`.
- Кнопка `🚀 В окне` запускает безопасный fresh-flow: бот отправляет новое сообщение с inline WebApp-кнопкой `🚀 Открыть викторину`, а не хранит persistent `web_app` URL в reply keyboard.
- Текущий Mini App MVP покрывает setup/contour chooser, state hydration, показ текущего вопроса, отправку ответа, feedback, переход к следующему шагу и итоговый результат с рестартом в окне Mini App.
- `/ui` и `🚀 В окне` открывают setup/contour chooser с контурами `Тесты по темам`, `Глоссарий` и `Литература` даже если активен normal quiz runner; chat `📚 Глоссарий` остаётся отдельным Telegram chat glossary quiz.
- Режим глоссария в Mini App использует существующие Mini App API endpoints (`GET /miniapp/setup-options`, `POST /miniapp/setup`, `POST /miniapp/answer`) и статические JSON-файлы `content/glossary`; provenance/source refs не показываются пользователям.
- `/quiz` остаётся дефолтным entry point и классическим chat-based runner.
- Mini App использует dedicated FastAPI backend service `psych_quiz_miniapp_api` с endpoints (`GET /miniapp/state`, `GET /miniapp/setup-options`, `POST /miniapp/setup`, `POST /miniapp/answer`) и server-authoritative state. Глоссарий использует те же endpoints; `mode=glossary, action=state` восстанавливает сохранённую попытку, её варианты, feedback или результат из общей БД.
- «Литература» в PWA — единый каталог проверенных библиографических записей с фильтром темы, module/source связями и Reading Tracker. Повторные упоминания одной работы сгруппированы; отметки сохраняются для выбранного учебного списка и доступны в Telegram. [Контракт каталога](docs/question_bank_content_rollout.md#каталог-литературы) объясняет стабильные IDs, неизвестные metadata и границы source review.
- PWA, Mini App и classic `/glossary` используют общий actor и durable glossary service. Незавершённый тест заменяется только после явного подтверждения; повтор answer/next/restart не увеличивает результат. `/glossary` после перезапуска восстанавливает display context. Прежние in-memory попытки, созданные до миграции, восстановить невозможно; quiz/literature history миграция сохраняет.
- «Мой прогресс» → «Сбросить учебный прогресс» в PWA показывает preview для темы или всего quiz/glossary learning. Отмена ничего не меняет; подтверждение привязано к показанному состоянию. Accounts/linking, банк и Reading Tracker/private notes сохраняются; поздний запрос не возвращает удалённую попытку. История/статистика quiz по-прежнему относятся к вопросам, glossary показывает собственную сохранённую попытку и результат.

## Границы дальнейшей работы

- PWA, PostgreSQL, progress/repetition и knowledge layer планируются по [новой спецификации](docs/project-spec.md), а не реализуются принятием документации
- webhook как обязательный/единственный runtime mode; доступен только опциональный infrastructure experiment за `TELEGRAM_UPDATE_MODE=webhook`
- runtime LLM-генерация вопросов запрещена; optional RAG поверх retrieval требует отдельного решения и оценки
- расширение Module 2 на новые темы без отдельного согласованного решения (помимо уже открытых активных категорий)

## Mini App deployment / QA runbook

Для ручной deployment-валидации Mini App runner используйте чеклист:
- [`docs/miniapp-deployment-qa.md`](docs/miniapp-deployment-qa.md)

Важно: в текущем репозитории hosting `miniapp/index.html` не автоматизирован runtime/deploy-скриптами и остаётся операторской инфраструктурной задачей.

Важно: для Cloudflare Workers Static Assets добавлен root `wrangler.toml` с публикацией статики из `./miniapp` через `npx wrangler deploy`.

## Документация

README is the repository entrypoint and navigation layer, not the full product specification or delivery journal.


| Документ | Роль | Когда читать |
|---|---|---|
| [AGENTS.md](AGENTS.md) | Постоянный router, Goal, AC/Evidence, проверки, Git/PR и поставка | При старте и восстановлении контекста |
| [Project Specification](docs/project-spec.md) | Каноническая продуктовая/проектная спецификация | Нужно проверить scope, продуктовые правила, модель контента и runtime-ограничения |
| [Delivery Plan](docs/delivery-plan.md) | Операционное состояние delivery | Нужно понять текущие checkpoints, активный фокус и следующий рекомендуемый шаг |
| [Delivery Plan Archive](docs/delivery-plan-archive.md) | Исторический архив delivery | Только для явных history/archive/reconciliation tasks |
| [CI/CD Rules](ci-cd-rules.md) | Правила настройки workflows, gates, artifacts, окружений и recovery | При настройке CI/CD и исправлении pipeline |
| [Workflow adoption record](docs/ai-delivery-infrastructure-plan.md) | Происхождение принятых документов и прежнее решение по Context Bundle Builder | При проверке истории workflow; текущие задачи находятся в Delivery Plan |
| [Mini App deployment / QA runbook](docs/miniapp-deployment-qa.md) | Чеклист/runbook по настройке `MINI_APP_URL`, HTTPS static hosting и ручной Telegram QA | Перед deployment-валидацией или ручным Mini App QA |

Source-of-truth модель:
- Product scope хранится в `docs/project-spec.md`.
- Текущее delivery-состояние хранится в `docs/delivery-plan.md`.
- Source of truth банка вопросов — JSON-файлы в `content/questions/`.
- SQLite — только runtime layer.


## Mini App setup (MVP)

- `MINI_APP_URL` (optional): URL статического Telegram Mini App runner для opt-in команды `/ui`; при отсутствии переменной бот продолжает работать только в classic chat UX режиме.
- `miniapp/index.html` публикуется отдельно на стороне deploy/infrastructure; runtime-секреты и Telegram токены в frontend не размещаются.
