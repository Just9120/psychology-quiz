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
- Если в вашей Telegram/BotFather конфигурации требуется доменная привязка для Web App — отдельно подтвердить, что она настроена для выбранного host (без хранения секретов и private деталей в репозитории).

## 5) Manual QA checklist

### A. Private chat checks
- [ ] `/ui` без `MINI_APP_URL` показывает fallback.
- [ ] `/ui` с `MINI_APP_URL` и активными категориями показывает кнопку открытия Mini App.
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
- [ ] Force API failure (bad base URL) falls back to `sendData` behavior and remains recoverable via `/ui` reopen.
