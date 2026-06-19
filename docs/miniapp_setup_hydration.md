# Mini App setup hydration

## Why setup launch URLs stay compact

Telegram Mini App launch URLs have a fixed practical size budget. The setup screen needs the active quiz categories and glossary topic metadata, but those lists grow as content expands. Embedding that full setup payload in the `/ui` URL makes the entrypoint fragile and can exceed `MAX_MINIAPP_URL_LENGTH`.

## Bootstrap vs hydrated data

The setup launch context now carries only compact bootstrap data:

- context type/version/frontend version;
- `mode: "setup"`;
- configured `api_base_url`;
- force/active-session-abandon markers when applicable;
- `setup_hydration_required: true`.

It does not carry the full category list or glossary topic payload. When hydration is required, the frontend waits before rendering the mode chooser, then fills the existing setup caches from the API response.

## Endpoint used

The frontend uses the existing authenticated endpoint:

```text
GET /miniapp/setup-options
Authorization: tma <Telegram WebApp initData>
```

The response contract remains backward compatible. The frontend reads glossary topics primarily from `data.setup_options.glossary`, with existing compatible fallback locations retained for legacy payloads.

## Fallback and error behavior

Legacy setup contexts that already include inline `categories` and `glossary` still render without API hydration.

If `setup_hydration_required` is true but `api_base_url` or Telegram WebApp `initData` is unavailable, the Mini App shows a clear Russian user-facing error instead of rendering an empty chooser. API or payload failures also show a readable retry/open-`/ui` error.

The active-session warning remains tied to the initial chooser and still says: `Запуск новой викторины завершит текущую активную попытку.`

## Test coverage expectations

Coverage should verify that:

- setup entrypoint URLs fit within the real configured `MAX_MINIAPP_URL_LENGTH`;
- compact bootstrap contexts include the hydration marker and omit embedded category/glossary payloads;
- `/miniapp/setup-options` remains authenticated and returns active categories plus all eight glossary topics;
- frontend setup hydration calls `/miniapp/setup-options`, populates category and glossary caches, and only then renders the normal chooser;
- legacy inline setup contexts remain supported;
- hydration failures display a readable user-facing error;
- completed-session “new quiz” flow can return to setup through the same hydrated setup path.
