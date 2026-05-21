# psychology-quiz

`psychology-quiz` — Telegram-бот викторины по психологии для учебного использования.

Текущее состояние продукта:
- **Module 1** — стабильный baseline.
- **Module 2** — запущен в ограниченном рабочем scope.

Бот работает в режиме **long polling** (без webhook), **Web UI отсутствует**, внешняя генерация вопросов во время работы (RAG/retrieval) отсутствует.

## Переменные окружения

Обязательные/основные runtime-переменные:
- `BOT_TOKEN`
- `BOT_USERNAME` (опционально)
- `APP_ENV` (по умолчанию `dev`)
- `LOG_LEVEL` (по умолчанию `INFO`)
- `DB_PATH` (по умолчанию `/data/quiz.sqlite3`)

Дополнительно для owner-only аналитики:
- `ADMIN_TELEGRAM_IDS` (опционально) — список numeric Telegram user id через запятую.
  Пример: `ADMIN_TELEGRAM_IDS=123456789,987654321`

Команда `/stats` скрыта из публичного меню/списка команд и доступна только owner-пользователям из `ADMIN_TELEGRAM_IDS` в личном чате.

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
- Telegram Mini App может быть добавлен как экспериментальный opt-in UX mode внутри Telegram.
- Первый MVP Mini App ограничен setup-экраном и не заменяет текущий chat-based quiz runner.
- При будущем открытии через `/ui` Mini App получает активные категории от бота через setup context.

## Что вне текущего продуктового контура

- standalone Web UI / PWA
- webhook
- RAG и внешняя генерация вопросов во время работы
- расширение Module 2 на новые темы без отдельного согласованного решения (помимо уже открытых активных категорий)

## Mini App deployment / QA runbook

Для ручной deployment-валидации Mini App setup-screen используйте чеклист:
- [`docs/miniapp-deployment-qa.md`](docs/miniapp-deployment-qa.md)

Важно: в текущем репозитории hosting `miniapp/index.html` не автоматизирован runtime/deploy-скриптами и остаётся операторской инфраструктурной задачей.

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

- `MINI_APP_URL` (optional): URL статического Telegram Mini App setup-экрана для opt-in команды `/ui`; при отсутствии переменной бот продолжает работать только в classic chat UX режиме.
- В этом PR добавлен только статический setup-screen (`miniapp/index.html`); его hosting и публикация URL должны быть настроены отдельно на стороне deploy/infrastructure.
