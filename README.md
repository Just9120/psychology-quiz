# psychology-quiz

`psychology-quiz` — Telegram-бот викторины по психологии для учебного использования.

Текущее состояние продукта:
- **Module 1** — стабильный baseline.
- **Module 2** — запущен в ограниченном рабочем scope.

Бот по умолчанию работает в режиме **long polling**; для инфраструктурного эксперимента доступен опциональный webhook mode за конфиг-флагом. **Web UI отсутствует**, внешняя генерация вопросов во время работы (RAG/retrieval) отсутствует.

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
- `TELEGRAM_WEBHOOK_SECRET_TOKEN` — опциональный secret token для Telegram webhook header; не логируется.

Дополнительно для owner-only аналитики:
- `ADMIN_TELEGRAM_IDS` (опционально) — список numeric Telegram user id через запятую.
  Пример: `ADMIN_TELEGRAM_IDS=123456789,987654321`

Команда `/stats` скрыта из публичного меню/списка команд и доступна только owner-пользователям из `ADMIN_TELEGRAM_IDS` в личном чате.

Кратко по конфигурации:
- `BOT_TOKEN` — обязательный.
- `MINI_APP_URL` — опциональный; включает экспериментальный opt-in Telegram Mini App runner (`/ui`).
- `ADMIN_TELEGRAM_IDS` — опциональный список numeric Telegram user id через запятую для owner-only команд (например, `/stats`).

## Telegram update delivery experiment: polling vs webhook

Current production default remains long polling. To run the current mode explicitly:

```bash
TELEGRAM_UPDATE_MODE=polling python -m app.main
```

Expected safe startup log:

```text
bot_update_mode mode=polling
```

To enable webhook mode behind a reverse proxy, terminate public HTTPS on the proxy and forward only the webhook path to the bot container/listener. Example environment:

```dotenv
TELEGRAM_UPDATE_MODE=webhook
TELEGRAM_WEBHOOK_URL=https://quiz.example.com/telegram/webhook
TELEGRAM_WEBHOOK_LISTEN=127.0.0.1
TELEGRAM_WEBHOOK_PORT=8090
TELEGRAM_WEBHOOK_SECRET_TOKEN=<operator-generated-secret>
```

Example reverse-proxy smoke checks from the host after deploy:

```bash
docker compose up -d --build --remove-orphans psych_quiz_bot
docker compose logs --tail=100 psych_quiz_bot | grep 'bot_update_mode mode=webhook'
curl -fsS http://127.0.0.1:8090/telegram/webhook -X POST -H 'Content-Type: application/json' -d '{}' || true
```

Safe webhook startup logs include the mode, local listen host/port, and URL path only; they must not include `BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET_TOKEN`, or raw update payloads. Example:

```text
bot_update_mode mode=webhook webhook_host=quiz.example.com listen=127.0.0.1 port=8090 path=/telegram/webhook
```

Diagnostic comparison for the experiment:
- If a user tap is visibly slow and `bot_update_ingress` appears late in polling but quickly in webhook mode, the likely bottleneck is long polling / `getUpdates` delivery before application ingress.
- If a user tap is visibly slow and `bot_update_ingress` is still late in webhook mode, the likely bottleneck is Telegram/client/network delivery before the webhook reaches the application.
- Existing `bot_update_ingress`, `bot_handler_start`, `bot_latency`, and `bot_latency_slow` diagnostics are preserved in both modes.

## Текущий продуктовый контур

Активные категории в продукте формируются из БД по `approved`-вопросам (не хардкодятся в UI).

Содержательно:
- Module 1: рабочий baseline по основным дисциплинам.
- Module 2: активные рабочие темы — **`Основы экспериментальной психологии`** и **`Качественные методы исследования`**.

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
- SQLite **не** является source of truth; это runtime layer хранения и выдачи данных.
- Заполнение и обновление SQLite выполняется сидером `scripts/seed_questions.py`.

Операционный поток (основной путь, CI/CD-first):
1. подготовить изменения в repo и сделать PR;
2. выполнить merge в `main`;
3. по `push` в `main` автоматически запускается GitHub Actions workflow;
4. workflow по SSH вызывает deploy-процесс на сервере;
5. deploy logic условно выполняет build/seed/restart (или no-op) по diff;
6. runtime-слой получает актуальные изменения без ручного `git pull + seed` как базового сценария.

Fallback:
- при необходимости деплой можно запустить вручную через GitHub Actions (`workflow_dispatch`).

## Operational nuance: как отрабатывает deploy logic

- `content`-only изменения → автосидинг (autoseed) в deploy-процессе.
- Изменения в `app/`, `scripts/`, `sql/` и runtime/Docker-related частях → deploy logic conditionally выполняет build/seed/restart.
- Docs-only изменения → no-op или почти no-op на runtime-слое.

## Вспомогательный UX

- постоянная клавиатура reply keyboard в личном чате (`🎯 Начать викторину`, `ℹ️ Помощь`, `👁 Режим чтения`, `🙈 Скрыть меню`)
- ручное скрытие меню через `🙈 Скрыть меню`
- во время активной викторины меню скрывается без отдельного уведомления
- после завершения викторины итоговый результат автоматически возвращает главное меню
- резервное восстановление через `/start`
- режим чтения: `Обычный` / `Бионическое чтение`


## Telegram Mini App (experimental note)

- Standalone Web UI / PWA сейчас не входят в текущий scope проекта.
- Telegram Mini App доступен как экспериментальный opt-in UX mode внутри Telegram: через `/ui` или через кнопку нижнего меню `🚀 Викторина в окне`.
- Кнопка `🚀 Викторина в окне` запускает безопасный fresh-flow: бот отправляет новое сообщение с inline WebApp-кнопкой `🚀 Открыть викторину`, а не хранит persistent `web_app` URL в reply keyboard.
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

| Документ | Роль | Когда читать |
|---|---|---|
| [Project Specification](docs/project-spec.md) | Каноническая продуктовая/проектная спецификация | Нужно проверить scope, продуктовые правила, модель контента и runtime-ограничения |
| [Delivery Plan](docs/delivery-plan.md) | Операционное состояние delivery | Нужно понять текущие checkpoints, активный фокус и следующий рекомендуемый шаг |
| [AI Coding Workflow](docs/ai-coding-workflow.md) | Правила ChatGPT / Codex / PR / docs workflow | Нужно подготовить prompt, проверить PR или понять правила обновления документации |
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

## Deploy safety note

- Во время deploy `deploy.sh` безопасно дополняет production `.env` отсутствующими ключами из `.env.example`, если оба файла существуют.
- Существующие production-значения в `.env` никогда не перезаписываются.
- Реальные production-значения (например, `BOT_TOKEN`, `MINI_APP_URL`) оператор заполняет вручную.
- Секреты и реальные значения не должны коммититься в репозиторий.
