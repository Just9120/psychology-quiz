# Mini App quiz runner design (next phase)

## Status and scope
- This is a **design-only** document for the next phase after PR #124.
- Current implemented Mini App scope remains **setup-screen only** via `/ui`.
- Runtime behavior remains unchanged in this PR:
  - `/quiz` stays the default classic chat entry point.
  - `/ui` stays experimental opt-in.
  - Questions/answers/results still run in classic chat today.
  - `/stats` remains owner-only and outside Mini App.

## Future target scope
Planned future UX inside Mini App (opt-in path):
1. Question display inside Mini App.
2. Answer selection inside Mini App.
3. Progress display inside Mini App.
4. Result screen inside Mini App.
5. Safe fallback to classic chat UX when needed.

## Entry-point model
- `/quiz`: unchanged classic default flow.
- `/ui`: experimental Mini App flow for users who opt in.
- Product safety rule: no switch of default UX in this phase; any default switch needs a separate product decision.

## Session model (authoritative server state)
1. **Session create**
   - User starts from `/ui` setup and confirms parameters.
   - Backend creates/updates quiz session server-side (owner user id, mode, allowed categories, question_count, difficulty, derived question set).
2. **Load current question state**
   - Mini App requests (or receives) current session snapshot with current question index and allowed options.
   - Client-rendered progress is display-only; canonical progress is server-calculated.
3. **Answer submit**
   - Mini App sends selected answer event with session reference and question reference.
   - Backend validates ownership + active state + expected current question + allowed option, then applies answer idempotently.
4. **Progress derive**
   - Backend returns next state (`next_question` or `completed`) with derived counters.
5. **Result produce**
   - Backend computes completion/result summary server-side and returns read-only result payload for display.

## Transport options considered

### Option A: `Telegram.WebApp.sendData` per answer
**How it works**
- Mini App sends each answer through `sendData`; bot receives `web_app_data` updates and drives session progression.

**Tradeoffs**
- Implementation complexity: low/medium (fits existing bot update handling).
- Security/validation: strong if all checks stay server-side, but message-only contract can be tighter and less explicit than HTTP API contracts.
- UX responsiveness: medium; depends on bot round-trip and chat-update path, can feel slower than direct API calls.
- Deployment requirements: minimal (no extra API surface).
- Compatibility: high with current architecture.
- Observability/debugging: medium/low; harder to inspect structured request/response timelines.
- Failure/retry: needs careful dedupe/idempotency on repeated `sendData` and Telegram delivery edge cases.

### Option B: Dedicated backend API for Mini App runner
**How it works**
- Mini App calls backend endpoints for session state, current question, answer submit, result state.

**Tradeoffs**
- Implementation complexity: medium/high (new endpoints, auth verification, request/response contracts).
- Security/validation: strongest and explicit; easier to enforce typed contracts and idempotency keys.
- UX responsiveness: high (direct in-app request cycle).
- Deployment requirements: higher (API exposure, routing/CORS/security hardening).
- Compatibility: medium; requires adding API layer patterns to current bot-centric runtime.
- Observability/debugging: high (logs/metrics per endpoint).
- Failure/retry: high control (HTTP codes, retry semantics, dedupe strategies).

### Option C: Hybrid (recommended for first implementation phase)
**How it works**
- Keep session authority in current bot/backend domain.
- Use `sendData` for answer events in the first slices.
- Add a minimal state-sync endpoint (or equivalent lightweight fetch contract) for Mini App to recover/render current question and progress on reopen.

**Tradeoffs**
- Implementation complexity: medium (smaller than full API, safer than pure event-only).
- Security/validation: strong if backend remains authoritative for every transition.
- UX responsiveness: medium/high (fast state reload on reopen; answer loop still compatible with current flow).
- Deployment requirements: moderate (small incremental API surface only when needed).
- Compatibility: high with existing bot design and `/ui` opt-in path.
- Observability/debugging: medium/high (state fetch points improve diagnosis).
- Failure/retry: good with idempotent answer handling + explicit state refresh channel.

## Recommended architecture (first implementation phase)
Recommend **Hybrid (Option C)** as safest next step:
- Preserves existing bot-centric authority and validation model.
- Minimizes risky platform changes while enabling in-Mini App question rendering.
- Supports reopen/recovery better than pure `sendData` alone.
- Avoids immediate full API expansion and associated deployment/security overhead.
- Keeps `/quiz` classic default unchanged and `/ui` strictly opt-in.

## Security and validation requirements (must remain explicit)
- Mini App client state is **untrusted**.
- Server/bot/backend must validate on each state transition:
  - user identity and session ownership;
  - active quiz session existence/status;
  - expected current question;
  - allowed answer options for that question;
  - category/mode/count/difficulty constraints;
  - completion and result calculation.
- Client-provided question IDs, answer IDs, category metadata, and progress values are hints only and must not be trusted blindly.
- No secrets/tokens/private hostnames/private internal paths/production env values in docs.
- `/stats` must not be exposed via Mini App in this phase.

## Reopen/recovery/failure behavior
1. **Mini App closed mid-session**
   - Session stays server-side with TTL/state marker.
2. **User reopens `/ui`**
   - Mini App requests current authoritative state and resumes from current question when session is active.
3. **Session expired/not found**
   - Show recoverable UI state: prompt to restart quiz via `/ui` setup or fallback to `/quiz`.
4. **Stale question submission**
   - Backend returns stale-state response; client refreshes current question snapshot.
5. **Duplicate answer submission**
   - Backend handles idempotently (ignore duplicate or return same resolved transition).
6. **Network failure / `sendData` failure**
   - Client shows retry affordance and performs state refresh before resubmit.
7. **Fallback to classic chat flow**
   - User can always continue/start via `/quiz`; fallback remains supported during rollout.

## Phased implementation slices

### Slice 1 — session/transport contract baseline
- Status: **implemented** in PR #126 (current PR).
- Delivered baseline: minimal authoritative server-side contract for answer submission with explicit ownership/session/current-question/allowed-option validation and predictable stale/duplicate handling.
- Validation approach: unit tests for ownership, stale submission, duplicate safety, and invalid option rejection.
- Non-goals kept: no full Mini App UI runner screens in this slice.
- Risks: contract drift between Mini App payload and backend expectations.

### Slice 2 — render current question in Mini App
- Status: **implemented** in this PR.
- Goal: show authoritative current question/answers in Mini App for opt-in `/ui` users.
- Likely files: Mini App frontend rendering logic, minimal state-load contract, bot/backend state adapter.
- Validation approach: manual QA + targeted tests for empty/expired state rendering.
- Non-goals: final result screen completeness.
- Risks: reopen race conditions and stale client cache assumptions.
 - Implementation note: because Mini App assets are static and no dedicated backend API is introduced in this slice, snapshot delivery is embedded into `/ui` launch context from bot-side authoritative DB state.

### Slice 3 — answer submission + next transition
- Status: **implemented** in this PR (minimal `sendData` transport and chat-confirmed transition).
- Goal: submit answers from Mini App and transition to next question safely.
- Likely files: answer submit handlers, Mini App submit UI state, dedupe/idempotency handling.
- Validation approach: stale/duplicate/out-of-order submission tests and manual Telegram QA.
- Non-goals: default UX switch away from `/quiz`.
- Risks: double-submit under poor network conditions.

### Slice 4 — progress + result screen
- Goal: add in-app progress indicators and final server-derived result view.
- Note: Slice 3 keeps lightweight UX due to static hosting and no dedicated backend state-refresh API; users reopen `/ui` to render the next authoritative snapshot.
- Likely files: Mini App progress/result components, backend result payload formatter.
- Validation approach: result consistency checks against server session data.
- Non-goals: `/stats` integration.
- Risks: mismatched client display vs server canonical score if mapping is wrong.

### Slice 5 — recovery/reopen hardening + polish
- Goal: robust resume/fallback UX and operational hardening.
- Likely files: Mini App recovery states, backend TTL/expiry messaging, QA docs.
- Validation approach: manual scenario matrix for reopen/failure paths; regression checks for classic `/quiz`.
- Non-goals: introducing standalone Web UI/PWA.
- Risks: edge-case churn and increased state-machine complexity.

## Non-goals for this design phase
- No runtime code changes.
- No default UX switch from classic chat to Mini App.
- No `/stats` exposure in Mini App.
- No DB schema change required by this design document itself.
