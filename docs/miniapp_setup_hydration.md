# Mini App setup hydration

## Действующий React-клиент

Активный Mini App собирается из `pwa/src/miniapp/` в `miniapp-react/`; build/deployment задаёт [процедура поставки](miniapp-deployment-qa.md). Сохранённый `miniapp/index.html` и compact launch context относятся к legacy compatibility. Их tests не заменяют проверку действующего клиента.

[MiniApp](../pwa/src/miniapp/MiniApp.tsx) при запуске вызывает Telegram `ready`/`expand`. Без `window.Telegram.WebApp.initData` показывает «Откройте в Telegram» и не отправляет API requests. Наличие строки initData в браузере само по себе не подтверждает identity: проверку подписи и срока действия initData выполняет backend.

При начальной загрузке `loadInitial` параллельно запрашивает `GET /miniapp/setup-options` и `GET /miniapp/state`; после успешного получения обоих responses применяет backend options и сохранённый runner state. Незавершённая попытка открывается вместе с доступным recent-answer feedback. Query/context payload не подменяет authoritative state.

[Transport](../pwa/src/miniapp/api.ts) закрепляет API origin `quiz-api.librechat.online` и allowlist routes. Launch parameters не определяют destination для initData. GET отправляет `Authorization: tma <initData>`; POST — `text/plain` JSON envelope с `init_data` и `payload`. Credentials omitted, redirects запрещены, cache no-store; request timeout — 9 секунд. PWA owner auth/cookie не используется как Telegram identity.

При первом сбое загрузки клиент показывает ошибку и «Повторить загрузку», которая повторно получает options/state. После неопределённого результата записи используется восстановление сохранённой попытки; frontend не начинает новую попытку автоматически. Новый квиз с активной попыткой требует явного подтверждения и `expected_session_id`/`replace_active`, проверяемых backend.

Действующий browser contract — [Mini App E2E](../pwa/tests/e2e/miniapp.spec.ts): запуск без Telegram, fixed-origin requests, first-load retry, ответы и восстановление потерянного ответа/чужой сессии. Эти сценарии используют synthetic proof и route mocks, не подтверждают живой Telegram/VPS. Canonical commands и обязательные CI checks находятся в [README](../README.md); актуальные результаты и ограничения — в [плане](delivery-plan.md).

## Сохранённый legacy HTML contract

Ниже сохранено описание прежнего HTML-клиента и compact contexts. Оно относится к `miniapp/index.html`, [context builder](../app/miniapp_context.py), [legacy frontend contracts](../tests/test_miniapp_frontend_contract.py) и [runner contracts](../tests/test_miniapp_runner_contract.py). Это не инструкция выбирать API origin из launch payload для React и не описание текущего initial loader. Старое число eight glossary topics ниже относится к описанному историческому состоянию, а не к текущему инвентарю.

### Why setup launch URLs stay compact

Telegram Mini App launch URLs have a fixed practical size budget. The setup screen needs the active quiz categories and glossary topic metadata, but those lists grow as content expands. Embedding that full setup payload in the `/ui` URL makes the entrypoint fragile and can exceed `MAX_MINIAPP_URL_LENGTH`.

### Bootstrap vs hydrated data

The setup launch context now carries only compact bootstrap data:

- context type/version/frontend version;
- `mode: "setup"`;
- configured `api_base_url`;
- force/active-session-abandon markers when applicable;
- `setup_hydration_required: true`.

It does not carry the full category list or glossary topic payload. When hydration is required, the frontend waits before rendering the mode chooser, then fills the existing setup caches from the API response.

### Endpoint used

The frontend uses the existing authenticated endpoint:

```text
GET /miniapp/setup-options
Authorization: tma <Telegram WebApp initData>
```

The response contract remains backward compatible. The frontend reads glossary topics primarily from `data.setup_options.glossary`, with existing compatible fallback locations retained for legacy payloads.

### Fallback and error behavior

Legacy setup contexts that already include inline `categories` and `glossary` still render without API hydration.

If `setup_hydration_required` is true but `api_base_url` or Telegram WebApp `initData` is unavailable, the Mini App shows a clear Russian user-facing error instead of rendering an empty chooser. API or payload failures also show a readable retry/open-`/ui` error.

The active-session warning remains tied to the initial chooser and still says: `Запуск новой викторины завершит текущую активную попытку.`

### Test coverage expectations

Coverage should verify that:

- setup entrypoint URLs fit within the real configured `MAX_MINIAPP_URL_LENGTH`;
- compact bootstrap contexts include the hydration marker and omit embedded category/glossary payloads;
- `/miniapp/setup-options` remains authenticated and returns active categories plus all eight glossary topics;
- frontend setup hydration calls `/miniapp/setup-options`, populates category and glossary caches, and only then renders the normal chooser;
- legacy inline setup contexts remain supported;
- hydration failures display a readable user-facing error;
- completed-session “new quiz” flow can return to setup through the same hydrated setup path.
