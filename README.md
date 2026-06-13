# psychology-quiz

`psychology-quiz` — Telegram-бот викторины по психологии для учебного использования.

Текущее состояние продукта:
- **Module 1** — стабильный baseline, 296 approved questions across five active topics.
- **Module 2** — ограниченный рабочий scope, 171 approved questions across two active topics.
- **Module 3** — первая активная категория `Психологическое консультирование`, 108 approved questions.
- Активный банк вопросов: 575 approved questions в JSON source-of-truth under `content/questions/**/*.json`.

Бот по умолчанию работает в режиме **long polling**; production также может работать в validated webhook mode за конфиг-флагом. **Web UI отсутствует**, внешняя генерация вопросов во время работы (RAG/retrieval) отсутствует.

## Переменные окружения

Обязательные/основные runtime-переменные:
- `BOT_TOKEN`
- `BOT_USERNAME` (опционально)
- `APP_ENV` (по умолчанию `dev`)
- `LOG_LEVEL` (по умолчанию `INFO`)
- `DB_PATH` (по умолчанию `/data/quiz.sqlite3`)

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

Keep detailed webhook, reverse-proxy, rollback, and diagnostic procedures outside the README so this file remains navigation/overview material. For CI/CD, deploy, secrets, rollback, and stateful-service safety boundaries, use [`docs/ci-cd-rules.md`](docs/ci-cd-rules.md). For Mini App deployment/manual QA, use [`docs/miniapp-deployment-qa.md`](docs/miniapp-deployment-qa.md).

## CI/CD and deployment model

Repository-visible GitHub Actions are split by responsibility:
- open PR and merge approved changes to `main`;
- CI validation runs on pull requests, pushes to `main`, and manual `workflow_dispatch`;
- the repository also contains a production CD workflow/deploy script for configured deployment environments; do not change or run deploy automation from ordinary docs/product tasks;
- CI must not deploy, access production SSH, or mutate production runtime state;
- deployment/CD uses Repository Secrets and the configured target environment; after merge, verify deployed commit/runtime state when deployment matters;
- docs-only changes do not require runtime sync.


## Быстрый старт и проверки

```bash
pip install -r requirements.txt
python -m compileall app scripts
python scripts/validate_questions.py
DB_PATH=/tmp/quiz-ci.sqlite3 python scripts/init_db.py
DB_PATH=/tmp/quiz-ci.sqlite3 python scripts/seed_questions.py
git diff --check
python -m app.main
```

`BOT_TOKEN` is required for `python -m app.main`; validation/seed commands above can run against a temporary SQLite path.

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
- `Конкретная тема` → выбор одной категории → выбор количества вопросов → выбор сложности.
- `Микс из выбранных тем` → мультивыбор категорий → `Готово` / `Сбросить` → выбор количества вопросов → выбор сложности.
- `Все темы` → выбор количества вопросов → выбор сложности.

Для режима `Микс из выбранных тем` выбранный набор категорий сохраняется на уровне сессии.

## Поток данных: JSON → seed → SQLite

- Source of truth банка вопросов: JSON в репозитории.
- Рабочие директории банка:
  - `content/questions/module1/`
  - `content/questions/module2/`
  - `content/questions/module3/`
- SQLite **не** является source of truth; это runtime layer хранения и выдачи данных.
- Заполнение и обновление SQLite выполняется сидером `scripts/seed_questions.py`.

Runtime sync for JSON/content changes is deployment-environment-specific. Repository-visible CI validates question-bank syntax and seedability, but does not deploy or mutate runtime SQLite. When deployment matters, verify deployed commit/runtime state in the target environment after merge; docs-only changes do not require runtime sync.

Operational deploy/seed/restart details and safety boundaries belong in [`docs/ci-cd-rules.md`](docs/ci-cd-rules.md) and the configured deployment environment, not in this README.

## Вспомогательный UX

- постоянная клавиатура reply keyboard в личном чате: `🎯 Начать` / `🚀 В окне`, `👁 Чтение` / `ℹ️ Помощь`, `🙈 Скрыть меню`
- classic `/quiz` остаётся дефолтным Telegram chat entry point
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

- Standalone Web UI / PWA сейчас не входят в текущий scope проекта.
- Telegram Mini App доступен как экспериментальный opt-in UX mode внутри Telegram: через `/ui` или через кнопку нижнего меню `🚀 В окне`.
- Кнопка `🚀 В окне` запускает безопасный fresh-flow: бот отправляет новое сообщение с inline WebApp-кнопкой `🚀 Открыть викторину`, а не хранит persistent `web_app` URL в reply keyboard.
- Текущий Mini App MVP покрывает setup, state hydration, показ текущего вопроса, отправку ответа, feedback, переход к следующему шагу и итоговый результат с рестартом в окне Mini App.
- `/quiz` остаётся дефолтным entry point и классическим chat-based runner.
- Mini App использует backend API (`GET /miniapp/state`, `GET /miniapp/setup-options`, `POST /miniapp/setup`, `POST /miniapp/answer`) и server-authoritative state.

## Что вне текущего продуктового контура

- standalone Web UI / PWA
- webhook как обязательный/единственный runtime mode; доступен только опциональный infrastructure experiment за `TELEGRAM_UPDATE_MODE=webhook`
- RAG и внешняя генерация вопросов во время работы
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
| [AGENTS.md](AGENTS.md) | Лёгкий first-read guide для coding agents | Перед implementation tasks |
| [Project Specification](docs/project-spec.md) | Каноническая продуктовая/проектная спецификация | Нужно проверить scope, продуктовые правила, модель контента и runtime-ограничения |
| [Delivery Plan](docs/delivery-plan.md) | Операционное состояние delivery | Нужно понять текущие checkpoints, активный фокус и следующий рекомендуемый шаг |
| [Delivery Plan Archive](docs/delivery-plan-archive.md) | Исторический архив delivery | Только для явных history/archive/reconciliation tasks |
| [AI Coding Workflow](docs/ai-coding-workflow.md) | Правила ChatGPT / Codex / PR / docs workflow | Нужно подготовить prompt, проверить PR или понять правила обновления документации |
| [CI/CD Rules](docs/ci-cd-rules.md) | Границы CI/CD, deploy, secrets, rollback и stateful services | Только для CI/CD/deploy/ops tasks |
| [AI Delivery Infrastructure Plan](docs/ai-delivery-infrastructure-plan.md) | Трекинг внедрения AI workflow | Нужно проверить статус docs-first adoption и решение по Context Bundle Builder |
| [Mini App deployment / QA runbook](docs/miniapp-deployment-qa.md) | Чеклист/runbook по настройке `MINI_APP_URL`, HTTPS static hosting и ручной Telegram QA | Перед deployment-валидацией или ручным Mini App QA |

Source-of-truth модель:
- Product scope хранится в `docs/project-spec.md`.
- Текущее delivery-состояние хранится в `docs/delivery-plan.md`.
- Source of truth банка вопросов — JSON-файлы в `content/questions/`.
- SQLite — только runtime layer.


## Mini App setup (MVP)

- `MINI_APP_URL` (optional): URL статического Telegram Mini App runner для opt-in команды `/ui`; при отсутствии переменной бот продолжает работать только в classic chat UX режиме.
- `miniapp/index.html` публикуется отдельно на стороне deploy/infrastructure; runtime-секреты и Telegram токены в frontend не размещаются.
