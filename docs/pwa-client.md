# Самостоятельный PWA quiz client

[README](../README.md#pwa-local-run-и-проверки) хранит canonical команды; [auth contract](pwa-auth.md) — конфигурацию сервера, sessions, почту и identity policy. Исходники — [pwa](../pwa/). Owner PWA опубликована на установленном HTTPS target; конфигурация и процедура — [PWA delivery](pwa-delivery.md). Public smoke/browser evidence и оставшиеся owner/mail/standalone checks — [план](delivery-plan.md#current-goal--pwa-first-001).

## Клиент и границы

- Вход/регистрация/подтверждение e-mail/восстановление → явный выбор Telegram linking либо независимого прогресса → quiz topics/setup/question/feedback/result. Разделы будущей платформы не изображаются работающими. Telegram SDK не подключается.
- `App` управляет состоянием экрана; `api` допускает фиксированный список same-origin `/web` actions. Сервер определяет actor, вопросы, score и переходы. Пароль очищается после входа; CSRF и одноразовые mail/link proofs живут только в памяти. Cookie — HttpOnly, production Secure. Local/session storage не используются.
- Mail proof приходит во fragment, немедленно удаляется из адреса; поддерживается открытие в новой и уже загруженной вкладке. При reload после удаления fragment нужно снова открыть письмо. Query string не используется для credentials.
- Пока request выполняется, повторные действия заблокированы. Потерянный ответ сохраняет исходный payload до retry; backend replay возвращает первоначальный outcome. При неопределённом setup клиент сначала читает server state. После reload восстанавливаются current attempt/последний feedback либо итог. Offline sync/локальное обучение не входят.
- Manifest содержит standalone launch и PNG 192/512/maskable icons. Install prompt используется, если его предоставляет браузер; иначе доступны инструкции, включая Safari. `sw.js` кэширует только публичный `offline.html`. Auth/API, вопросы, ответы и результаты остаются network-only. Offline navigation показывает страницу без данных аккаунта.
- Native labels/radios/checkboxes, keyboard focus, skip link и alerts используются вместе с mobile layout. Физическая установка на устройствах/iOS и real SMTP проверяются после публикации; viewport tests этого не доказывают.

## Build и test evidence

`package-lock.json` фиксирует npm graph; Node/npm и scripts заданы manifest/README. Иконки генерируются из собственного SVG через pinned resvg, PNG проверены в browser suite. `dist` — generated artifact, в Git не хранится. `build.json` содержит full source revision, dirty marker и SHA-256 всех остальных assets; service worker cache version совпадает с revision. CI задаёт проверяемый commit SHA; локальный dirty build явно маркируется.

CI `pwa-client` выполняет component tests, typecheck/build и Playwright Chromium desktop/mobile against real FastAPI/temporary SQLite. Нет production secrets, Telegram calls или реальных писем. [Test harness](../pwa/tests/backend.py) существует только в test process на loopback, не импортируется production runtime и не имеет switch в production API. Telegram часть E2E linking использует synthetic trusted adapter; bot handlers/private-user checks отдельно проверяются Python suite.

Artifact `pwa-<tested-SHA>` публикуется после успешных frontend/Nginx checks на 7 дней. PR artifact относится к GitHub test merge revision; main artifact — к merge commit. Для будущей поставки использовать успешный trusted main CI и проверить identity/hashes; PR artifact не подменяет production release. CI не выполняет deploy. [Release tooling и target preconditions](pwa-delivery.md) подготовлены, применение отложено.

## Локальные данные

Browser suite каждый раз создаёт отдельную temporary DB с семью вымышленными вопросами/двумя темами и synthetic mailbox; удаляет её при штатном завершении server process. Тестовый owner и password заданы только в harness/spec. Control routes `__test/*` отсутствуют в production app. Dev preview не предназначен для public bind или VPS hosting.
