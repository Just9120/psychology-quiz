# Самостоятельный PWA quiz client

[README](../README.md#pwa-local-run-и-проверки) хранит canonical команды; [auth contract](pwa-auth.md) — конфигурацию сервера, sessions, почту и identity policy. Исходники — [pwa](../pwa/). Owner PWA опубликована на установленном HTTPS target; конфигурация и процедура — [PWA delivery](pwa-delivery.md). Public smoke/browser evidence и owner-reported mail/standalone acceptance — [план](delivery-plan.md#завершённая-goal--pwa-first-001).

## Клиент и границы

- Вход/регистрация/подтверждение e-mail/восстановление → явный выбор Telegram linking либо независимого прогресса → quiz topics/setup/question/feedback/result. Разделы будущей платформы не изображаются работающими. Telegram SDK не подключается.
- `App` управляет состоянием экрана; `api` допускает фиксированный список same-origin `/web` actions. Сервер определяет actor, вопросы, score и переходы. Пароль очищается после входа; CSRF и одноразовые mail/link proofs живут только в памяти. Cookie — HttpOnly, production Secure. Local/session storage не используются.
- Mail proof приходит во fragment, немедленно удаляется из адреса; поддерживается открытие в новой и уже загруженной вкладке. При reload после удаления fragment нужно снова открыть письмо. Query string не используется для credentials.
- Пока request выполняется, повторные действия заблокированы. Потерянный ответ сохраняет исходный payload до retry; backend replay возвращает первоначальный outcome. При неопределённом setup клиент сначала читает server state. После reload восстанавливаются current attempt/последний feedback либо итог. Offline sync/локальное обучение не входят.
- Manifest содержит standalone launch и PNG 192/512/maskable icons. Install prompt используется, если его предоставляет браузер; иначе доступны инструкции, включая Safari. `sw.js` кэширует только публичный `offline.html`. Auth/API, вопросы, ответы и результаты остаются network-only. Offline navigation показывает страницу без данных аккаунта.
- Native labels/radios/checkboxes, keyboard focus, skip link и alerts используются вместе с mobile layout. Физическая установка на устройствах/iOS и real SMTP проверяются после публикации; viewport tests этого не доказывают.

## Личный прогресс и ошибки

`Мой прогресс` читает shared quiz history проверенного actor: finished/in_progress/abandoned попытки и только отвеченные вопросы. Процент = correct / answered; planned question count отдельно, незавершённая попытка не считается завершённой. Сводка охватывает всю историю; страницы истории/ответов/ошибок — по 20 записей с keyset cursors. Темы берутся из immutable edition. Динамика показывает последние 14 активных UTC-дней, в том числе для выбранной темы; это результат практики с counts, не mastery. Нет отдельного progress cache/table и request-time schema changes.

[Progress service](../app/progress_service.py) получает actor только от проверенного adapter. `GET /web/progress/overview`; JSON POST `progress/history` (`before` session ID), `progress/attempt` (`session_id`, `after` order index), `progress/errors` (`before` answer ID). Missing/foreign attempt возвращают одинаковый 404. Неотвеченные вопросы и правильные варианты будущих вопросов не попадают в detail. POST reads используют existing Origin/CSRF guards; все responses no-store, raw IDs/body не логируются.

Policy D-14 из [spec](project-spec.md#e04--повторение-и-личный-прогресс): последний сохранённый answer ID на question/hash/provenance определяет ошибку редакции. Captured и legacy backfill различаются; historical result не пересчитывается по live bank. Правильный ответ на текущую captured редакцию исключает вопрос из тренировки, даже если сохранилась ошибка старой редакции. Retired вопросы только просматриваются. В UI старые/восстановленные редакции обозначены явно; история прежних ответов остаётся доступной после исправления ошибки.

`POST /web/progress/train`: `expected_session_id` (последняя наблюдённая попытка, nullable), `replace_active` (явный boolean), `question_count` (5/10/15/null). Server повторно выбирает distinct approved вопросы из собственных ошибок, перемешивает и ограничивает выбранным объёмом; меньшее количество — весь доступный набор. Actor/content transaction locks защищают selection/snapshot/start от concurrent writers. Stale expected session/replay → 409 `practice_changed`, активная попытка без подтверждения → 409 `active_attempt`, пустой набор → 409 `no_errors`; существующая попытка не меняется. После lost reply клиент читает shared runner state; repeated start не создаёт второй session. Прямой arbitrary question/actor selection отсутствует. Existing Telegram/API contracts не меняются.

UI data живут только в памяти и очищаются при logout/401. Навигация заново читает данные; failed fetch не подменяет их вымышленным нулём. Training использует общий quiz runner и его persisted answer/retry/reload semantics. SQLite и PostgreSQL проверяются одинаковыми domain/API fixtures; browser suite покрывает оба backend, отмену замены, потерю ответа после commit, сохранение истории, keyboard/desktop/mobile и отсутствие private cache. Canonical commands остаются в README.

## Build и test evidence

`package-lock.json` фиксирует npm graph; Node/npm и scripts заданы manifest/README. Иконки генерируются из собственного SVG через pinned resvg, PNG проверены в browser suite. `dist` — generated artifact, в Git не хранится. `build.json` содержит full source revision, dirty marker и SHA-256 всех остальных assets; service worker cache version совпадает с revision. CI задаёт проверяемый commit SHA; локальный dirty build явно маркируется.

CI `pwa-client` выполняет component tests, typecheck/build и Playwright Chromium desktop/mobile against real FastAPI/temporary SQLite и PostgreSQL. Нет production secrets, Telegram calls или реальных писем. [Test harness](../pwa/tests/backend.py) существует только в test process на loopback, не импортируется production runtime и не имеет switch в production API. Telegram часть E2E linking использует synthetic trusted adapter; bot handlers/private-user checks отдельно проверяются Python suite.

Artifact `pwa-<tested-SHA>` публикуется после успешных frontend/Nginx checks на 7 дней. PR artifact относится к GitHub test merge revision; main artifact — к merge commit. Для поставки использовать успешный trusted main CI и проверить identity/hashes; PR artifact не подменяет production release. CI не выполняет deploy. [Release tooling и target preconditions](pwa-delivery.md) используются после успешного backend CD; runtime status восстанавливается по первичным records.

## Локальные данные

Browser suite каждый раз создаёт отдельную temporary DB с семью вымышленными вопросами/двумя темами и synthetic mailbox; удаляет её при штатном завершении server process. Тестовый owner и password заданы только в harness/spec. Control routes `__test/*` отсутствуют в production app. Dev preview не предназначен для public bind или VPS hosting.
