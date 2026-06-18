# Project Specification

## Product goal
- Проект — Telegram-бот викторины по психологии.
- Продукт ориентирован на учебную практику и самопроверку.
- Текущий контур: стабильный Module 1 + запущенный Module 2 в ограниченном scope + первый активный content-scope Module 3 для психологического консультирования.
- Текущий активный approved банк вопросов: 575 вопросов в 8 topic JSON files.

## Current product scope
- **Module 1** — baseline (стабильный рабочий контур), 296 approved questions across five active topics.
- **Module 2** — уже запущен с двумя активными темами, 171 approved questions total:
  - `Основы экспериментальной психологии` — 118 approved
  - `Качественные методы исследования` — 53 approved
- **Module 3** — открыт только первым активным content-scope по утверждённым source-backed материалам, 108 approved questions:
  - `Психологическое консультирование` — 108 approved
- Этот первый scope Module 3 не авторизует широкое расширение Module 3 за пределы доступных согласованных материалов с явной опорой на источник.
- Активные категории в runtime определяются из БД по `approved`-вопросам, а не хардкодом в UI.
- Режим работы бота: long polling по умолчанию; опциональный webhook mode доступен только как config-gated infrastructure experiment.
- Standalone Web UI отсутствует; Telegram Mini App является opt-in UX внутри Telegram и не считается standalone Web UI.
- RAG/внешняя генерация вопросов во время работы отсутствуют.

## Out of scope
- Standalone Web UI вне Telegram Mini App.
- Webhook как обязательный/единственный production mode; long polling должен сохраняться как default.
- RAG и внешняя генерация вопросов во время runtime.
- Расширение Module 2 на новые темы без отдельного согласованного решения.
- Широкое расширение Module 3 за пределы первой активной категории `Психологическое консультирование` без отдельного согласованного source-backed content batch.

## User roles / actors
- Обычный пользователь Telegram-бота (прохождение викторины и выбор режимов UX).
- Owner/admin (операционный доступ к скрытой агрегированной аналитике через `/stats`).

## Core quiz scenarios
Поддерживаются отдельные режимы работы:
- `Конкретная тема`
- `Микс из выбранных тем`
- `Все темы`

Потоки:
- `Конкретная тема` → выбор одной категории → выбор количества вопросов → выбор сложности.
- `Микс из выбранных тем` → мультивыбор категорий → `Готово` / `Сбросить` → выбор количества вопросов → выбор сложности.
- `Все темы` → выбор количества вопросов → выбор сложности.

Повторяемость выбранного микса:
- режим `Микс из выбранных тем` является отдельным рабочим сценарием;
- выбранный набор тем сохраняется в рамках пользовательской сессии;
- сценарий post-quiz через inline-кнопки `Пройти еще раз` / `Новая викторина` / `Помощь` не является частью текущего активного UX.

## UX behavior
- Используется постоянная клавиатура reply keyboard в личном чате.
- Меню можно скрыть через `🙈 Скрыть меню`.
- Во время активной викторины меню скрывается без отдельного уведомления.
- После завершения викторины итоговый результат автоматически возвращает главное меню.
- Дополнительный резервный способ восстановления интерфейса — `/start`.
- Поддерживаются режимы чтения:
  - `Обычный`
  - `Бионическое чтение`

## Content model and question-bank rules
- Source of truth банка вопросов: JSON-файлы в репозитории.
- Learning contours: tests/questions, glossary/terms, and a literature reading-tracker scaffold.
- Tests/questions contour uses `content/questions/**/*.json` as canonical content and SQLite as runtime serving layer.
- Glossary/terms contour uses static `content/glossary/*.json`; source/source_refs/provenance stay internal and are not shown in user-facing chat or Mini App UI.
- Literature scaffold uses static `content/literature/*.json`; it is content/validation scaffolding until separate source-backed runtime work is explicitly authorized.
- Рабочие директории:
  - `content/questions/module1/`
  - `content/questions/module2/`
  - `content/questions/module3/`
- Категории хранятся отдельными JSON-файлами в соответствующих module-директориях.
- Базовая схема элемента вопроса:
  - `id`
  - `category`
  - `source_ref`
  - `difficulty`
  - `status`
  - `question`
  - `options`
  - `correct_option_index`
  - `explanation`
- В SQLite загружаются только записи со статусом `approved`.
- Контент банка вопросов должен быть на русском языке.
- Вопросы без подтвержденной опоры на источник добавлять нельзя.
- Интернет не используется как первичный источник для наполнения банка вопросов.
- Приоритет источников для нового контента:
  1. папка `Психология` с исходными лекциями, транскрибациями, презентациями и практиками;
  2. текущий банк вопросов в репозитории;
  3. Obsidian/пересобранная база знаний как вторичный синтетический слой.
- Практико-ориентированные вопросы встраиваются в профильные категории, а не выделяются в отдельную рабочую категорию.


Current approved content inventory:

| Module | Topic/category | JSON source file | Approved questions |
|---|---|---|---:|
| Module 1 | `Физиология ВНД` | `content/questions/module1/fiziologiya_vnd.json` | 57 |
| Module 1 | `Общая психология` | `content/questions/module1/obschaya_psihologiya.json` | 56 |
| Module 1 | `Психофизиология` | `content/questions/module1/psihofiziologiya.json` | 71 |
| Module 1 | `Физиология человека` | `content/questions/module1/fiziologiya_cheloveka.json` | 55 |
| Module 1 | `Введение в профессию` | `content/questions/module1/vvedenie_v_professiyu.json` | 57 |
| Module 2 | `Основы экспериментальной психологии` | `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json` | 118 |
| Module 2 | `Качественные методы исследования` | `content/questions/module2/kachestvennye_metody_issledovaniya.json` | 53 |
| Module 3 | `Психологическое консультирование` | `content/questions/module3/psychological_consulting.json` | 108 |
| **Total** | 8 active topics | `content/questions/**/*.json` | **575** |


## Telegram UX modes
- `classic` — текущий и дефолтный UX в Telegram-чате; `/quiz` остаётся default chat entry point.
- `classic_reply_keyboard` — preferred production implementation внутри classic chat UX: ответы и действие `Далее` отправляются как обычные Telegram message updates через bottom reply keyboard buttons.
- `classic_inline_callback` — legacy/fallback implementation classic chat UX: ответы и переходы идут через inline callback-кнопки в сообщениях.
- `miniapp_test` — opt-in режим Telegram Mini App runner внутри Telegram; доступен через `/ui` / `🚀 В окне` и не включается по умолчанию.
- `miniapp_default` — потенциальный будущий режим по умолчанию для Mini App, сейчас неактивен и не реализован.

Ограничения и позиционирование:
- Classic chat UX остаётся дефолтным режимом.
- В production для classic chat UX рекомендуется reply keyboard mode, потому что answer controls живут в нижней Telegram-клавиатуре и не засоряют сообщения викторины inline-кнопками.
- Inline callback mode сохраняется только как legacy/fallback для classic chat UX.
- Telegram Mini App не является PWA.
- Telegram Mini App не является standalone Web UI.
- Mini App остаётся отдельным opt-in UX и не заменяет текущий bot UX как default mode.
- `/quiz` остаётся дефолтным классическим режимом.
- Opt-in входы в Mini App: `/ui` и кнопка нижнего меню `🚀 В окне`.
- `/ui` и `🚀 В окне` открывают setup/contour chooser даже если у пользователя активен normal quiz runner; в этом случае warning о завершении текущей активной попытки остаётся ожидаемым.
- Chat `📚 Глоссарий` / `/glossary` остаётся отдельным Telegram chat glossary quiz и не открывает Mini App contour chooser.
- Фактический launch Mini App выполняется через fresh inline WebApp-кнопку `🚀 Открыть викторину`, сгенерированную текущим `/ui`-контекстом.
- Persistent reply keyboard не должен хранить stale `web_app` URL/launch-context для Mini App; `/ui` генерирует fresh launch context.

Реализованный MVP Mini App:
- поддерживает setup/contour chooser, state hydration, отображение вопроса, отправку ответа, feedback, переход к следующему шагу и completed/result экран;
- на setup entrypoint показывает два пользовательских контура: `Тесты по темам` и `Глоссарий`;
- контур `Тесты по темам` использует обычный question-bank runner;
- контур `Глоссарий` использует glossary quiz по static `content/glossary/*.json` через существующие Mini App API endpoints (`GET /miniapp/setup-options`, `POST /miniapp/setup`, `POST /miniapp/answer`, `GET /miniapp/state`);
- setup поддерживает quiz modes:
  - `single`;
  - `selected_mix`;
  - `all`;
- setup поддерживает выбор категорий, когда применимо;
- setup поддерживает выбор количества вопросов:
  - `5`;
  - `10`;
  - `15`;
  - `all available`;
- setup поддерживает выбор сложности:
  - `any`;
  - `easy`;
  - `medium`;
  - `hard`;
- Mini App runner остаётся separate opt-in flow внутри Telegram и не становится default UX.

Category initialization model для Mini App setup:
- В момент `/ui` бот загружает активные категории из SQLite runtime-слоя.
- Бот формирует компактный setup context с `category_id` и именами категорий.
- Бот передаёт setup context в Mini App через encoded URL query parameter.
- Mini App рендерит категории из URL setup context.
- Хардкод категорий во frontend Mini App запрещён.
- Setup context — только UI rendering context, не source of truth.
- Persistent reply keyboard не должен хранить `web_app` URL/launch-context для Mini App; launch URL/context генерируется fresh через `/ui`.

Payload contract summary (Mini App → bot):
- `type`: `quiz_setup`;
- `quiz_mode`: `single | selected_mix | all`;
- `category_ids`: `number[]`;
- `question_count`: `5 | 10 | 15 | null`;
- `difficulty`: `any | easy | medium | hard`;
- `question_count = null` означает «все доступные вопросы».

Trust boundary:
- Payload из Mini App считается недоверенным client input.
- URL setup context может быть изменён на стороне клиента.
- Бот обязан валидировать payload server-side перед запуском квиза.
- В момент приёма payload бот обязан повторно проверять активность категорий и доступность вопросов.
- `/stats` остаётся скрытой owner-only private-chat-only агрегированной аналитикой и не переносится в Mini App.

Out of scope для первого Mini App MVP:
- standalone Web UI;
- PWA;
- web analytics;
- account area;
- `/stats` внутри Mini App;
- DB schema changes;
- persistence пользовательского UI preference;
- изменения Module 1;
- расширение scope/категорий Module 2;
- изменения workflow question bank.

## Future Mini App direction
- Mini App runner MVP реализован и стабилизирован через PR #155–#162.
- Classic Telegram chat UX остаётся дефолтным; `/quiz` остаётся default entry point.
- `/ui` остаётся экспериментальным opt-in входом в Mini App.
- `miniapp_default` остаётся потенциальным будущим режимом и сейчас не активируется.
- `/stats` остаётся owner-only и вне Mini App на текущем этапе.
- Следующий этап: расширенный MVP QA и наблюдаемость перед любым обсуждением смены default UX.
- Детальная эволюция архитектуры и исторические решения зафиксированы в `docs/miniapp-quiz-runner-design.md`.
- Состояние Mini App клиента считается недоверенным, server-side валидация остаётся авторитативной.


## Mini App API runtime architecture
- Bot runtime remains responsible for Telegram command/update handling and classic `/quiz` UX.
- Dedicated FastAPI service is the production runtime for Mini App API endpoints (`/miniapp/state`, `/miniapp/setup-options`, `/miniapp/setup`, `/miniapp/answer`).
- Static Mini App frontend remains separately hosted over HTTPS (unchanged hosting model).
- API endpoint contracts remain backward-compatible; migration target is HTTP serving/runtime layer, not quiz business semantics.

Deployment model (final target):
- One repository + one VPS/deployment environment + one Docker Compose stack.
- Separate services/containers (`psych_quiz_bot`, `psych_quiz_miniapp_api`) in Compose.
- This is **not** multiple services inside one Docker container.
- Not a separate project/server; operationally coordinated in same deployment environment.

Current production model:
- FastAPI is enabled as the production Mini App API service.
- Production Compose/CD treats both `psych_quiz_bot` and `psych_quiz_miniapp_api` as the intended runtime service set for app runtime restarts.
- CD must rebuild/recreate both services when runtime code or Mini App API behavior changes.
- Legacy in-bot `ThreadingHTTPServer` Mini App API path is not the current production serving path.

Trust model (unchanged):
- Mini App client remains untrusted.
- Server-side validation/authorization/state transitions remain authoritative.
- `/quiz` classic behavior remains unchanged and default.

Migration non-goals (explicit):
- no PostgreSQL introduction in this sprint;
- no Redis;
- no FastAPI rewrite for Telegram bot handlers;
- no frontend rewrite;
- no scoring/session schema changes.

## Data and runtime state model
- SQLite не является source of truth; SQLite — runtime layer хранения и выдачи данных.
- Обновление runtime-слоя выполняется через `scripts/seed_questions.py`.
- Ручное редактирование SQLite как способ обновления контента запрещено.

## Admin / owner-only operational features
- `/stats` — скрытая owner-only аналитика.
- `/stats` не является частью публичного UX и не должен отображаться в публичном меню/списке команд.
- Доступ к `/stats` контролируется через `ADMIN_TELEGRAM_IDS`.
- Авторизация основана на numeric Telegram user id.
- `/stats` работает только в личном чате.
- `/stats` возвращает только агрегированные метрики.
- `/stats` не должен раскрывать персональные списки пользователей.
- Реальный production owner Telegram id не должен фиксироваться в документации/репозитории.

## CI/CD and operational process
Основной путь синхронизации (CI/CD-first):
1. подготовить изменения в репозитории и оформить PR;
2. выполнить merge в `main`;
3. по `push` в `main` автоматически запускается GitHub Actions CI workflow (validation/checks);
4. repository-visible production CD workflow/deploy script may run only in the configured deployment environment with Repository Secrets and CI/CD safety boundaries; do not invoke or change it from ordinary product/docs tasks;
5. после merge необходимо проверить факт деплоя по deployed commit/runtime state целевой среды, если runtime deployment matters.

Логическая модель runtime-синхронизации (для deployment environment):
- content changes → seed (autoseed).
- Изменения в `app/`, `scripts/`, `sql/` и Docker-related слоях → build/seed/restart по условиям deploy logic среды.
- Docs-only changes не требуют runtime sync (no-op/почти no-op).

Fallback path:
- При необходимости деплой/восстановление инициируется через штатные механизмы deployment environment.
- Ручное server-side вмешательство допускается только как аварийный сценарий, а не основной operational path.

## Security / privacy constraints
- Не коммитить реальные секреты и production owner Telegram id.
- Owner-only аналитика должна оставаться ограниченной списком `ADMIN_TELEGRAM_IDS`.
- Публикуемые метрики `/stats` должны быть агрегированными и безопасными с точки зрения приватности.

## Anti-patterns
- Нельзя объявлять SQLite источником истины для банка вопросов.
- Нельзя обновлять контент через прямые правки SQLite.
- Нельзя добавлять вопросы без внятного `source_ref` и подтвержденной опоры на источник.
- Нельзя смешивать в банке вопросов нерелевантный PM-layer.
- Нельзя расширять Module 2 на новые темы в рамках «широких» PR без отдельного решения.
- README — компактный операционный обзор; детальные нормы фиксируются в этом документе.

## Current roadmap / next-scope rules
1. Поддерживать практику синхронизации документации с фактическим состоянием репозитория после содержательных изменений.
2. Продолжать узкие, grounded PR в рамках текущего запущенного scope Module 2 и синхронизировать документацию при открытии новых активных категорий.
3. Выбор следующей дисциплины Module 2 фиксировать отдельно, отдельным согласованным решением и отдельным PR.
4. Поддерживать контентный рост малыми целевыми итерациями; при контентных изменениях обновлять docs только точечно для устранения расхождений.

Примечание по фазе:
- Module 1 остается baseline.
- Module 2 уже в работе и включает две активные категории, формируемые через approved-вопросы после seed.

## Open questions
- На текущем этапе открытых обязательных scope-вопросов нет; расширение Module 2 и возможные новые категории выносятся в отдельные согласованные решения.
