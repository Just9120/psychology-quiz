# Mini App Runner Audit — 2026-05-24 (after #146)

## 1) Executive summary

**Overall health:** **yellow / fragile but serviceable** for experimental `/ui`.

What is **confirmed working** from current code and tests:
- Telegram `initData` verification exists and is used for `/miniapp/state`, `/miniapp/setup`, `/miniapp/setup-options`, `/miniapp/answer`.
- `/ui` can render setup and in-window question flow.
- `/miniapp/setup` and `/miniapp/answer` are implemented and integrated into frontend-first flow.
- Completed state includes in-window restart path (`Новая викторина`) with API-first `GET /miniapp/setup-options` fallback.
- `sendData` fallback is preserved for both setup and answer paths.

What remains **risky / partially broken**:
- Frontend still treats launch context as a primary render source on first paint; stale launch context can be visible until hydration or forever in setup mode when hydration is skipped.
- Completed → new quiz restart can still fail when categories are absent and `setup-options` fetch fails; UX falls back to reopen guidance only.
- Contract tests for frontend are predominantly static string checks and can pass while runtime UX is broken.
- Cache-busting strategy for static Mini App is implicit/partial (`FRONTEND_VERSION`, `v=...` in docs) and not enforced end-to-end in code paths.
- CORS policy is strict origin-match only; correct for safety, but operationally fragile when hostnames/protocol differ.

Recommendation:
- Continue focused patching in small PRs (do **not** rewrite architecture now).
- Simplify responsibilities: server state should become the only authoritative source for runner screen state after bootstrapping.
- Keep `/ui` experimental; keep `/quiz` as safe default.

---

## 2) Current architecture map (as implemented)

### 2.1 `/quiz` classic flow
- Classic flow remains default command path; Mini App is opt-in and supplemental.
- Delivery/README docs repeatedly position `/quiz` as default and `/ui` as experimental.

### 2.2 `/ui` command flow
- `/ui` launches Mini App using context-carrying URL generated in backend helpers (`build_miniapp_*` family referenced by tests), with compact payload fallback when URL length is constrained.
- Inline launch is primary; reply/sendData fallback exists and is still part of runner continuity strategy.

### 2.3 Mini App launch URL/context generation
- Context is URL-encoded and parsed in frontend by `parseContext(getContextParam())`.
- Frontend expects `type=miniapp_setup_context`, `version=1`, and optional `runner_state`, `runner_q`, `categories`, `api_base_url`, `setup_url`, `hydrate_on_setup`, debug markers.

### 2.4 Telegram inline WebApp launch vs reply fallback
- API-first path when `api_base_url` configured + `tg.initData` present.
- Fallback to `tg.sendData` for setup/answer when API unavailable/fails.
- If both API and sendData are unavailable, frontend shows actionable error.

### 2.5 Frontend context parsing
- Decodes `context` from query or hash.
- Accepts both base64url JSON and URI-encoded JSON fallback parsing.
- Invalid context => setup load error path.

### 2.6 `GET /miniapp/state`
- Auth: verified Telegram initData.
- User identity source: verified initData user id only.
- Returns authoritative `runner_state` from DB.

### 2.7 `POST /miniapp/setup`
- Auth: verified initData.
- Validates mode/count/difficulty/category_ids schema.
- Selects approved questions by mode and optional difficulty.
- Abandons user in-progress sessions, starts new session, stores question set, returns `runner_state`.

### 2.8 `GET /miniapp/setup-options`
- Auth: verified initData.
- Returns active categories plus fixed question-count and difficulty choices.
- Used by completed → restart flow when launch context lacks categories.

### 2.9 `POST /miniapp/answer`
- Auth: verified initData.
- Validates payload ints (`type(v) is int` strictness blocks bool coercion).
- Submits answer via runner contract.
- On accepted answer: returns `feedback` (includes correctness and explanation) + updated `runner_state`.
- On stale/duplicate/etc: returns submission status and often `runner_state` for recovery.

### 2.10 Completed result flow
- `renderRunnerState` enters completed branch from server state and renders result + actions.
- Result action includes restart + optional close button.

### 2.11 “Новая викторина” flow
Restart order in frontend:
1. Try in-place render from existing `setupOptionsCache.categories`.
2. Try cache from `ctx.categories`.
3. If API available, fetch `/miniapp/setup-options` and render setup in place.
4. Else try validated `setup_url` same-origin redirect.
5. Else show reopen instruction.

### 2.12 sendData fallback flow
- Setup submit: API attempted first, then fallback sendData.
- Answer submit: API attempted first, then fallback sendData.
- Diagnostic markers in debug mode expose branch taken.

### 2.13 Static `miniapp/index.html` hosting/caching assumptions
- Single static file app (no bundler/chunk hashes).
- Frontend has hardcoded version marker `FRONTEND_VERSION = 'ui-polish-v2'`.
- Docs mention URL cache busting (`v=ui-polish-v2`) but enforcement depends on launch URL generation path.

### 2.14 API nginx/domain/CORS assumptions
- API handler adds CORS only when `Origin` equals configured `allowed_origin` exactly.
- OPTIONS supports all four Mini App endpoints.
- `Cache-Control: no-store` on API responses.
- Requires stable single canonical Mini App origin in deployment.

---

## 3) State machine audit

### States
1. **setup**
2. **setup_submitting**
3. **in_progress_question**
4. **answer_submitting**
5. **feedback_displayed**
6. **next_question_transition**
7. **completed_result**
8. **restart_new_quiz**
9. **fallback_error**

### Transition table

| From | To | Source of truth | Endpoint | Can close app? | Stale risk | Recovery |
|---|---|---|---|---|---|---|
| launch | setup / in_progress / completed | launch context first, then optional server hydration | `GET /miniapp/state` (conditional) | yes | **medium** (context-first render) | reopen / hydrate / `/quiz` |
| setup | setup_submitting | frontend local form | `POST /miniapp/setup` | yes | low | retry button remains available |
| setup_submitting | in_progress_question | server state | `POST /miniapp/setup` success | yes | low | n/a |
| setup_submitting | fallback_error / sendData | frontend + Telegram | fallback sendData | yes | medium | reopen `/ui` |
| in_progress_question | answer_submitting | frontend local click lock | `POST /miniapp/answer` | yes | low | timeout/network fallback |
| answer_submitting | feedback_displayed | server response feedback | `POST /miniapp/answer` success | yes | low | n/a |
| feedback_displayed | next_question_transition | frontend local (`Далее`) + server snapshot bundled | none immediate | yes | medium (if state changes elsewhere) | hydrate via `/miniapp/state` on reopen |
| next_question_transition | in_progress_question / completed_result | server-derived state already returned by answer API | none immediate | yes | low/medium | reopen/hydrate if mismatch |
| completed_result | restart_new_quiz | cached categories or setup-options API | `GET /miniapp/setup-options` optional | yes | **high** when no categories + failed fetch | setup_url redirect or reopen `/ui` |
| any | fallback_error | frontend/local network branches | varies | yes | medium | `/quiz` fallback always available |

Key state machine note:
- System is hybrid: multiple truth sources coexist (launch context, local UI state, server state, Telegram sendData side channel). This improves resilience but increases stale/branch complexity.

---

## 4) Bug inventory

### AUDIT-001
- **Severity:** high
- **Area:** frontend/state consistency
- **Description:** Context-first render can temporarily (or in setup-mode permanently) show stale state before/without server hydration.
- **Evidence:** `miniapp/index.html` (`renderRunnerState(rs, { preferLaunchCompact: true })` runs immediately; hydration skipped for setup unless `hydrate_on_setup=true`).
- **Repro:** Open `/ui` using old context after session changed; observe outdated UI when setup hydration is not enabled.
- **Impact:** User sees wrong phase (setup/result/question) and may take invalid action.
- **Minimal fix:** Always run light server state sync after first paint (with UI flag “syncing”), including setup mode, but keep current setup-guard behavior only for explicit force-setup if needed.
- **Tests:** Add runtime-like test that stale context + fresh server state resolves deterministically to server state.

### AUDIT-002
- **Severity:** medium
- **Area:** completed→restart UX
- **Description:** Restart depends on categories cache/API; if both missing/fail, user is blocked to reopen flow only.
- **Evidence:** `buildCompletionActions()` fallback chain in `miniapp/index.html`.
- **Repro:** Completed state with empty `ctx.categories`, API unavailable, invalid/absent `setup_url`.
- **Impact:** “Новая викторина” appears but cannot continue in-window.
- **Minimal fix:** Cache last successful setup-options in `sessionStorage` and attempt reuse before final reopen fallback.
- **Tests:** Add frontend behavioral test for completed restart under missing categories + API failure.

### AUDIT-003
- **Severity:** medium
- **Area:** frontend resilience
- **Description:** Button-disable windows rely on JS flow completion; unexpected runtime exception before re-enable can strand disabled controls.
- **Evidence:** `submitAnswer()` disables all buttons upfront; re-enable only in specific fallback branches.
- **Repro:** Inject JSON parse/runtime error in answer path after disable.
- **Impact:** User stuck without reload.
- **Minimal fix:** Add `finally`-style re-enable guard for non-feedback branches.
- **Tests:** Simulate thrown exception post-disable and assert controls recover.

### AUDIT-004
- **Severity:** low
- **Area:** deployment/caching
- **Description:** Cache-busting is documented but not guaranteed by audited frontend file itself; static hosting may serve stale HTML in Telegram WebView.
- **Evidence:** hardcoded `FRONTEND_VERSION`; docs mention query `v=` strategy; no manifest/hash pipeline.
- **Repro:** Publish new HTML without query bump; Telegram client can reuse cached asset.
- **Impact:** production mismatch between expected and loaded frontend behavior.
- **Minimal fix:** enforce versioned launch URL generation in backend with CI assertion + `Cache-Control` guidance in runbook.
- **Tests:** backend test asserts `/ui` launch URL contains current frontend version token.

### AUDIT-005
- **Severity:** medium
- **Area:** tests/frontend
- **Description:** Frontend contract tests are string-presence checks and may pass while runtime logic is broken.
- **Evidence:** `tests/test_miniapp_frontend_contract.py` only checks substrings in HTML source.
- **Repro:** break event wiring but keep strings; tests still green.
- **Impact:** false confidence.
- **Minimal fix:** add minimal headless DOM test (Playwright/Pyppeteer or jsdom-like) for critical paths.
- **Tests:** add scenario tests: setup submit API success/failure, completed restart chain, button state recovery.

### AUDIT-006
- **Severity:** low
- **Area:** docs consistency
- **Description:** Mini App docs still include historical statements that can conflict with current API-first progression (e.g., reopen-after-each-submit language in design history sections).
- **Evidence:** `docs/miniapp-quiz-runner-design.md` status/history sections mix implemented and obsolete flow notes.
- **Repro:** read top-to-bottom; operator may infer outdated required reopen behavior.
- **Impact:** QA/operator confusion.
- **Minimal fix:** add explicit “current behavior as of 2026-05-24” block and archive historical notes under timeline heading.
- **Tests:** docs lint/checklist item requiring “current behavior” section.

### AUDIT-007
- **Severity:** medium
- **Area:** deployment/CORS
- **Description:** Exact-origin CORS match is secure but brittle; minor origin drift (www/non-www/protocol) silently breaks API path and pushes users to fallback.
- **Evidence:** `MiniAppApiHandler._set_common_headers` strict equality with one `allowed_origin`.
- **Repro:** configure allowed origin with trailing/alternate host and open from slightly different origin.
- **Impact:** API seemingly “down”, restart/setup regress to fallback.
- **Minimal fix:** normalize origin config and add startup validation/logging; optionally support explicit allowlist (still strict, not wildcard).
- **Tests:** add handler tests for mismatch diagnostics and exact-match positive/negative cases.

### AUDIT-008
- **Severity:** low
- **Area:** backend/session lifecycle
- **Description:** Setup always abandons all in-progress sessions for user before starting new one; intentional but race-sensitive under parallel setup requests.
- **Evidence:** `build_setup_response()` calls `abandon_in_progress_sessions_for_user` then `start_quiz_session`.
- **Repro:** rapid duplicate setup submissions.
- **Impact:** possible user confusion over which session is active.
- **Minimal fix:** idempotency token for setup submit or short debounce lock per user.
- **Tests:** concurrency test with two setup posts and deterministic active-session result.

Auth/leak checks from requested list:
- No direct correctness leakage in state/setup/setup-options responses observed.
- Correct answer/explanation appears only after accepted answer via `/miniapp/answer`.
- Identity source in API handlers uses verified initData, not payload user id.

---

## 5) Documentation audit

Reviewed:
- `README.md`
- `docs/miniapp-quiz-runner-design.md`
- `docs/miniapp-deployment-qa.md`
- `docs/delivery-plan.md`

Findings:
1. **Outdated/historical blending risk (medium):** design doc mixes prior-phase constraints with newer API behavior without a strict “current canonical flow” section.
2. **Operator ambiguity (low/medium):** deployment QA doc is thorough but should explicitly include cache invalidation verification in Telegram WebView after each Mini App HTML update.
3. **Delivery plan drift risk (low):** timeline table includes many post-fix notes; lacks a concise “latest verified production behavior” checksum entry.
4. **README under-describes current /ui API flow (low):** still emphasizes MVP/setup framing; could confuse new maintainers about current in-window answer/setup APIs.

Doc-only recommendations:
- Add a short “Current production behavior (dated)” section to each Mini App doc.
- Add explicit cache-busting operator step with pass/fail criteria.
- Add one line in delivery plan referencing this audit as pre-patching gate.

---

## 6) Test audit

### `tests/test_miniapp_runner_contract.py`
**Covers well:**
- Core submission contract (accepted/stale/duplicate/forbidden/invalid option).
- Runner-state selection behavior (in-progress preference, completed fallback).
- Payload parsing strictness including bool rejection.

**Missing:**
- Concurrency/race behavior for setup/session abandonment.
- End-to-end transition combining API setup + answer + completed restart.

**False-confidence risk:**
- Strong unit contract coverage, but no browser flow validation.

**Add tests:**
- Multi-request race test for setup.
- Deterministic latest-session selection under near-simultaneous starts.

### `tests/test_miniapp_api.py`
**Covers well:**
- initData auth validation.
- Basic endpoint happy paths and safe payload constraints.
- OPTIONS/CORS baseline.

**Missing:**
- Detailed setup-options failure/retry semantics.
- More CORS negative-path observability assertions.
- Timeouts/network behavior at integration boundary.

**False-confidence risk:**
- Mostly function-level tests, not full HTTP integration for all endpoints and error branches.

**Add tests:**
- End-to-end HTTP server test for `/miniapp/setup` + `/miniapp/answer` + `/miniapp/setup-options` restart chain.
- Explicit tests for mismatched origin behavior diagnostics.

### `tests/test_miniapp_frontend_contract.py`
**Covers well:**
- Guards against accidental removal of important strings/branches.

**Missing:**
- Runtime event wiring correctness.
- Actual DOM transitions across setup/question/feedback/completed/restart states.

**False-confidence risk:** **high**
- Tests can pass even when handlers break.

**Add tests:**
- Minimal browser-like smoke (headless) for:
  1) setup API success path,
  2) answer feedback and next,
  3) completed restart with setup-options API,
  4) fallback messaging when API fails.

---

## 7) Recommended fix plan (post-audit PR sequence)

### PR-A: Verify #146 completed→new-quiz in production-like QA
- **Scope:** Repro matrix + diagnostics/logging-only adjustments + docs evidence.
- **Likely files:** `docs/miniapp-deployment-qa.md`, possibly logging touchpoints in bot/API if needed.
- **Risk:** low.
- **Validation:** manual Telegram matrix (completed with/without categories cache, API up/down, setup_url present/absent).
- **Acceptance:** documented pass/fail table; no silent dead-end branch.

### PR-B: Source-of-truth cleanup for setup/new-quiz
- **Scope:** deterministic state precedence (server beats launch context after boot) with minimal UX change.
- **Likely files:** `miniapp/index.html`, maybe context flags in `app/main.py` launch builder.
- **Risk:** medium.
- **Validation:** automated frontend runtime tests + existing unit tests.
- **Acceptance:** stale context cannot override fresh server state beyond initial skeleton render.

### PR-C: Hang/retry/recovery hardening
- **Scope:** robust button enable/disable lifecycle, retry affordances, timeout copy consistency.
- **Likely files:** `miniapp/index.html`.
- **Risk:** medium.
- **Validation:** simulated timeout/network failure tests; manual QA.
- **Acceptance:** no persistent disabled controls after recoverable failures.

### PR-D: Docs + tests truthfulness cleanup
- **Scope:** align docs with current behavior; add runtime-oriented frontend tests.
- **Likely files:** Mini App docs + `tests/test_miniapp_frontend_contract.py` + new runtime test file.
- **Risk:** low/medium.
- **Validation:** CI + doc review checklist.
- **Acceptance:** docs no longer overpromise/underdescribe; test suite fails on real UX regressions.

### PR-E (optional): Responsibility simplification
- **Scope:** reduce launch context to bootstrap only; lean on `/miniapp/state` for runtime truth.
- **Likely files:** `app/main.py`, `miniapp/index.html`, runner context helpers/tests.
- **Risk:** medium/high.
- **Validation:** load/perf + Telegram reopen QA.
- **Acceptance:** fewer stale-state branches with same or better UX.

Priority order matches requested focus:
1) production verification for #146 restart,
2) setup/new-quiz truth-source cleanup,
3) hang/recovery hardening,
4) docs/tests cleanup,
5) optional simplification.

---

## 8) Go / no-go recommendation

- **`/ui` status:** keep **experimental**.
- **`/quiz` status:** remains **safe default** and should continue as primary path.
- **Before considering Mini App production-ready, must fix/validate:**
  1. deterministic server-state precedence after launch,
  2. completed→new-quiz reliability without dead-end fallback in normal ops,
  3. runtime (not string-only) frontend regression coverage,
  4. explicit operator cache-busting + origin/CORS verification checklist.

Final recommendation: **No-go for default UX switch**; proceed with targeted stabilization PRs only.
