# Mini App / Bot Refactor RFC

Delivery Item ID: `REFACTOR-RFC-MINIAPP-BOT-001`

## Purpose

This RFC proposes safe, incremental architectural seams for the Telegram bot, Mini App launch context, Mini App API, glossary flows, and static Mini App frontend.

This is a planning document only. It does **not** authorize runtime behavior changes by itself.

## No UX behavior change rule

Every refactor PR that follows this RFC must preserve current user-facing behavior unless a later task explicitly authorizes a behavior change.

Refactor PRs must not change:

- `/quiz` as the default classic Telegram chat entrypoint.
- `/ui` and `🚀 В окне` as opt-in Mini App setup/contour chooser entrypoints.
- The first Mini App setup chooser contours: `Тесты по темам` and `Глоссарий`.
- Chat `📚 Глоссарий` / `/glossary` as a separate Telegram chat glossary quiz.
- Mini App API endpoint contracts, request payloads, response payloads, or error semantics.
- Static Mini App frontend hosting model.
- DB schema, seed behavior, JSON content, source refs, provenance visibility, secrets, CI/CD, or deploy scripts.

## Current runtime/product constraints

Observed constraints from `docs/project-spec.md` and `docs/miniapp-deployment-qa.md`:

- Classic Telegram chat UX remains the default; `/quiz` remains the default classic entrypoint.
- Mini App remains opt-in through `/ui` and the lower-menu `🚀 В окне` button.
- `/ui` and `🚀 В окне` open the Mini App setup/contour chooser even when a normal quiz runner is active; the active-attempt warning is expected.
- The Mini App setup chooser has two user-facing contours: `Тесты по темам` and `Глоссарий`.
- Chat `📚 Глоссарий` / `/glossary` remains the separate Telegram chat glossary quiz and must not open the Mini App chooser.
- The Mini App frontend is a Telegram Mini App, not a standalone Web UI or PWA.
- Active categories for Mini App setup are loaded from SQLite runtime state and must not be hardcoded in the frontend.
- URL setup context is a UI rendering context only; client-provided Mini App payloads remain untrusted and server-side validation remains authoritative.
- Source refs, source snippets, and provenance remain internal and hidden from chat and Mini App user-facing UI.
- The production Mini App API runtime is the dedicated FastAPI service `psych_quiz_miniapp_api`; the bot service remains responsible for Telegram command/update handling and classic `/quiz` UX.
- Static Mini App frontend hosting remains separate and operator-managed over HTTPS.
- The production runtime service set is `psych_quiz_bot` plus `psych_quiz_miniapp_api`.
- Legacy in-bot Mini App API serving is not the current production-serving path.
- Persistent reply-keyboard WebApp launch buttons are intentionally not used for Mini App because they can preserve stale launch context; `/ui` must generate a fresh inline WebApp button.

## Current observed pain points

### `app/main.py` mixed responsibilities

`app/main.py` currently combines multiple layers that should be independently testable and reviewable:

- Telegram command/menu registration and runtime wiring.
- `/quiz` classic setup, answer, feedback, next-question, and completion handling.
- Classic reply-keyboard and legacy inline-callback handling.
- Telegram chat `/glossary` topics/count/answer/next flow.
- Mini App setup context encoding, compact runner payloads, URL building, and fallback sizing.
- Mini App launch handlers for `/ui` and `🚀 В окне`.
- Mini App post-setup prompt and launch keyboard helpers.
- Legacy Mini App API server toggles/wiring that sit near handler logic.

This makes small fixes risky because launch-context changes, Telegram handler changes, and quiz/glossary business flow are close together in one file.

### Mini App launch context is central but not isolated

The recent entrypoint and freshness work depends on subtle Mini App context behavior:

- setup vs runner vs completed mode selection;
- compact runner question payload fallback;
- compact progress-only fallback;
- URL length limits;
- setup URL attachment for completed sessions;
- glossary setup metadata in setup context;
- API base URL injection.

This logic is mostly pure and testable, but it currently lives beside Telegram handlers and DB-facing orchestration.

### Chat glossary and Mini App glossary overlap without crisp boundaries

The repository already has `app/glossary.py` for glossary domain/content helpers and `app/miniapp_glossary.py` for Mini App glossary sessions. However:

- Telegram chat glossary handlers still live in `app/main.py`.
- Mini App glossary API compatibility is layered into existing Mini App endpoints.
- Both chat and Mini App glossary paths must keep provenance hidden from users.

Clearer module ownership would reduce accidental cross-flow regressions.

### Mini App API serving and API builders are broad

`app/miniapp_api.py` contains initData verification, setup/answer/state response builders, glossary endpoint builders, compatibility routing, and a legacy `BaseHTTPRequestHandler`. `app/miniapp_fastapi.py` exposes those builders through the dedicated FastAPI runtime.

The immediate RFC does not propose changing endpoint contracts or runtime serving, but later seams should distinguish:

- API transport/routing;
- request authentication/transport extraction;
- classic quiz runner state transitions;
- glossary state transitions;
- response contract builders.

### `miniapp/index.html` is a single large static artifact

`miniapp/index.html` contains HTML, CSS, and a large imperative frontend state machine in one no-build file. This is compatible with the current operator-managed static hosting model, but it increases review risk for future changes because markup, styling, setup flow, runner flow, glossary flow, API retry behavior, and debug diagnostics are tightly coupled.

A later split into `miniapp/index.html`, `miniapp/styles.css`, and `miniapp/app.js` may be useful, but it must preserve no-build deployment unless explicitly changed.

## Proposed target module boundaries

These are intended seams, not a big-bang rewrite.

### `app/miniapp_context.py`

Owns Mini App launch context and URL construction.

Responsibilities:

- Encode Mini App setup/runner/completed context.
- Build Mini App URLs from a base URL and context.
- Build setup entrypoint URLs.
- Build compact runner question payloads.
- Build compact progress-only fallback payloads.
- Enforce URL length fallback behavior.
- Include safe glossary setup metadata when building setup context.

Boundaries:

- No Telegram handler functions.
- No Telegram `Update` or `ContextTypes` dependencies.
- No DB access unless a later task explicitly justifies it.
- No quiz business state transitions.
- No Mini App API endpoint handling.
- Accept already-loaded categories, runner state, frontend version, API base URL, and safe glossary payload inputs as function arguments where practical.

### `app/miniapp_entrypoint_handlers.py`

Owns Telegram entrypoints that launch the Mini App.

Responsibilities:

- `/ui` handler.
- `🚀 В окне` menu-button handler.
- Private-chat checks and user-facing fallback messages for Mini App launch.
- Load active categories and current runner state needed for launch orchestration.
- Call `app.miniapp_context` builders.
- Send fresh inline WebApp buttons.

Boundaries:

- No classic quiz answer/next business logic.
- No glossary chat quiz answer flow.
- No context encoding implementation details beyond calling the context module.
- No endpoint contract changes.

### `app/glossary_handlers.py`

Owns Telegram chat glossary quiz handlers.

Responsibilities:

- `/glossary` command and `📚 Глоссарий` button handler.
- Glossary topic/count callbacks.
- Chat glossary answer/next callback flow.
- Chat text answer parsing if kept for glossary.
- Telegram-specific formatting orchestration using `app/glossary.py` helpers.

Boundaries:

- Keep `app/glossary.py` as domain/content quiz helpers where possible.
- Do not expose `source_refs`, supplied snippets, internal IDs, or provenance.
- Do not change Mini App glossary API contracts.

### `app/classic_quiz_handlers.py` or `app/quiz_handlers.py`

Owns classic Telegram quiz flow.

Responsibilities:

- `/quiz` and `🎯 Начать` entrypoints.
- Category/count/difficulty callbacks.
- Classic answer handling.
- Classic `Далее` handling.
- Completion/result rendering and main-menu restoration.
- Reply-keyboard and legacy inline-callback branching where needed.

Boundaries:

- Do not include Mini App context encoding.
- Do not include Mini App API builders.
- Do not include glossary quiz flow beyond dispatch/registration coordination.

### Existing domain/API modules

Keep and clarify current modules before further splitting:

- `app/glossary.py`: glossary content/domain helpers for chat glossary quiz and shared safe formatting.
- `app/miniapp_glossary.py`: Mini App glossary session/domain helpers and safe payloads.
- `app/miniapp_runner.py`: Mini App runner state and answer-event contracts.
- `app/miniapp_api.py`: Mini App API contract builders and compatibility behavior.
- `app/miniapp_fastapi.py`: FastAPI transport/runtime wrapper around API builders.
- `app/miniapp_fastapi_runtime.py`: uvicorn import entrypoint.

Any future API split should be proposed separately and must preserve existing endpoint contracts.

### Static Mini App split proposal

Later, after backend seams are safer, consider splitting the no-build Mini App frontend into:

- `miniapp/index.html` for document structure and script/style references;
- `miniapp/styles.css` for CSS;
- `miniapp/app.js` for current imperative state machine.

Rules for that later PR:

- Keep no-build static deployment unless explicitly changed.
- Do not add bundlers, TypeScript, state stores, frameworks, package managers, or build pipelines.
- Preserve current Telegram Mini App behavior, API requests, recovery behavior, and diagnostics defaults.
- Update frontend contract tests to read the split files if needed.

## Incremental PR sequence

Each PR should introduce one safe seam and include focused tests or contract checks where appropriate.

### PR 1 — Extract Mini App context/URL builder

Recommended first implementation PR after this RFC.

Scope:

- Create `app/miniapp_context.py`.
- Move Mini App context encoding, URL building, setup entrypoint URL building, compact runner question payload, compact progress fallback, completed setup URL fitting, and URL-length fallback helpers out of `app/main.py`.
- Keep function behavior and public contracts unchanged.
- Update imports in `app/main.py` and existing tests.
- Prefer passing safe glossary payload into the context builder or keeping a tiny injectable default helper so the module remains mostly pure.

Why first:

- Lowest-risk seam because most logic is pure-ish and already contract-tested.
- Central to recent `/ui` launch-context freshness and URL-length fallback bugs.
- Reduces future Mini App entrypoint risk before moving handlers.

Validation:

- `python -m compileall app scripts`
- Mini App runner contract tests.
- Mini App frontend contract tests if context payload expectations are touched.
- `git diff --check`

### PR 2 — Extract Mini App entrypoint handlers

Scope:

- Create `app/miniapp_entrypoint_handlers.py`.
- Move `/ui` and `🚀 В окне` orchestration out of `app/main.py`.
- Keep handler registration in `app/main.py` if that avoids larger runtime wiring churn.
- Preserve private-chat fallback, no-category fallback, active-session warning, fresh inline WebApp button behavior, and no persistent WebApp reply-keyboard launch URL.

Validation:

- Compile checks.
- Existing Mini App runner/entrypoint contract tests.
- Focused handler tests if practical without broad test infrastructure.
- `git diff --check`.

### PR 3 — Extract Telegram chat glossary handlers

Scope:

- Create `app/glossary_handlers.py`.
- Move chat `/glossary`, topic/count callbacks, answer callbacks, and next handling from `app/main.py`.
- Keep `app/glossary.py` as domain/content helper module.
- Preserve chat glossary UX and provenance hiding.

Validation:

- Compile checks.
- `tests/test_glossary_runtime.py`.
- Any relevant main-menu/help tests.
- `git diff --check`.

### PR 4 — Extract classic quiz handlers

Scope:

- Create `app/classic_quiz_handlers.py` or `app/quiz_handlers.py`.
- Move `/quiz`, category/count/difficulty selection, classic answer, feedback, next, and result handling from `app/main.py`.
- Keep runtime registration and shared constants stable unless a narrow import move is required.

Validation:

- Compile checks.
- Existing classic quiz tests, if present.
- Focused smoke/contract checks around reply-keyboard mode if tests exist.
- `git diff --check`.

### PR 5 — Clarify Mini App API module seams without contract changes

Scope:

- Only after handler seams are stable, consider splitting API internals if still needed.
- Candidate seams: auth/initData helpers, transport extraction, setup options, quiz setup/answer/state builders, glossary compatibility builders.
- Keep FastAPI routes and endpoint payload contracts unchanged.
- Keep legacy in-bot API compatibility only if still required by current code/tests; removal would need separate explicit authorization.

Validation:

- Mini App API tests.
- FastAPI tests.
- Compile checks.
- `git diff --check`.

### PR 6 — Optional no-build static frontend split

Scope:

- Split `miniapp/index.html` into HTML/CSS/JS static files only if review risk justifies it.
- Preserve operator-managed static hosting and no-build deployment.
- Update contract tests to inspect all relevant static files.

Validation:

- Frontend contract tests.
- Manual browser sanity if practical.
- Telegram Mini App manual smoke only when deployed by an operator.
- `git diff --check`.

## Non-goals

This RFC does not propose:

- A big-bang rewrite.
- New frameworks, state stores, bundlers, TypeScript, Redis, PostgreSQL, queues, migrations, or build pipelines.
- Endpoint contract changes.
- Deployment model changes.
- CI/CD or deploy-script changes.
- DB schema changes.
- Seed behavior changes.
- JSON content changes.
- Source/provenance visibility changes.
- Telegram UX changes.
- Changing Mini App to default UX.
- Turning the Telegram Mini App into a standalone Web UI or PWA.
- Removing classic inline-callback fallback mode.
- Changing production runtime service names or operator-managed static hosting.

## Risk analysis

| Risk | Impact | Mitigation |
|---|---|---|
| Import-cycle churn while extracting from `app/main.py` | Runtime import failures or handler registration regressions | Move one seam at a time; keep shared constants minimal; run `compileall`; prefer dependency injection for context builders. |
| Accidental Mini App URL/context contract drift | `/ui` launches stale, oversized, or invalid context | Preserve existing tests; add direct tests around encoded context, fallback flags, runner/completed/setup modes, and URL length limits. |
| Glossary provenance leak | Internal source refs appear in chat or Mini App | Keep safe payload builders; retain tests that assert `source_refs`, snippets, and internal IDs are absent. |
| Telegram UX regression | `/quiz`, `/ui`, or `/glossary` behavior changes during refactor | Require the no-UX-change rule in every PR; keep handler moves mechanical; validate menu/help/entrypoint contracts. |
| Endpoint compatibility regression | Mini App frontend can no longer use existing `/miniapp/setup`, `/miniapp/answer`, `/miniapp/state`, or `/miniapp/setup-options` flows | Do not change endpoint contracts; run Mini App API/FastAPI tests after API-adjacent refactors. |
| Static hosting regression after frontend split | Operator-managed hosting no longer serves assets correctly | Keep no-build files under `miniapp/`; only split frontend in a later explicit PR; document any required static-host asset inclusion. |
| Review scope creep | Refactor becomes architecture rewrite | One seam per PR; no product behavior changes; no new infrastructure; stop after each seam is validated. |

## Validation strategy

For this docs-only RFC PR:

- Markdown review.
- `git diff --check`.
- No runtime tests are required because no runtime code changed.

For follow-up refactor PRs:

- Always run `python -m compileall app scripts`.
- Always run `git diff --check`.
- Run the smallest focused existing test set for the seam being moved:
  - Mini App context/runner: `tests/test_miniapp_runner_contract.py` and relevant frontend contract tests.
  - Chat glossary: `tests/test_glossary_runtime.py` and relevant Mini App glossary API tests if shared helpers are touched.
  - Mini App API/FastAPI: `tests/test_miniapp_api.py` and `tests/test_miniapp_fastapi.py`.
  - Frontend static split: `tests/test_miniapp_frontend_contract.py`.
- Use manual Telegram QA only when runtime deployment or visible Telegram behavior is intentionally touched by a later task.

## Rollback strategy

- Keep each PR narrow enough to revert independently.
- Prefer pure moves with unchanged function names or compatibility re-exports during transition where useful.
- For PR 1, rollback is a single revert returning Mini App context helpers to `app/main.py` imports/definitions.
- For handler extraction PRs, rollback is a single revert restoring handlers in `app/main.py` and previous registrations.
- For frontend split, rollback is a single revert restoring the single-file `miniapp/index.html` artifact.
- No DB migration, seed, JSON content, deployment, or endpoint-contract rollback should be needed for these refactor PRs because those areas are non-goals.

## First recommended implementation PR

Start with **PR 1 — Extract Mini App context/URL builder**.

Proposed delivery item ID: `REFACTOR-MINIAPP-CONTEXT-EXTRACT-001`.

Acceptance criteria:

- `app/miniapp_context.py` owns Mini App context encoding and URL construction helpers.
- `app/main.py` imports and uses those helpers instead of defining them inline.
- `/ui`, `🚀 В окне`, runner reopen, completed result reopen, compact fallback, glossary setup metadata, and post-setup launch prompt behavior remain unchanged.
- Existing Mini App context/runner contract tests pass without endpoint or UX changes.
- No runtime feature, content, schema, seed, CI/CD, deploy, or static hosting behavior changes are included.
