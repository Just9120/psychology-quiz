# Delivery Plan

## Current status
- Module 1 stable baseline; Module 2 limited active scope.
- `/quiz` remains default classic Telegram UX.
- `/ui` is experimental opt-in Mini App runner (MVP) and is now stabilized for broader QA.
- PR #166 completed Mini App entry UX polish: safe bottom-menu entry `🚀 Викторина в окне` delegates to fresh `/ui` inline launch flow.

## Completed checkpoints
- #156: proxy / DB migration docs and deployment notes synchronized.
- #157: shorter answer timeout + GET diagnostics for Mini App API.
- #158: pre-retry state resync before answer retries.
- #159: early hedge recovery (`ANSWER_HEDGE_DELAY_MS = 1200`).
- #160: HTTP/1.1 + explicit `Content-Length` + keep-alive behavior.
- #161: answer-submit UX polish (pending/disabled states, clearer flow).
- #162: feedback readability and visual hierarchy polish.
- #166: Mini App entry UX polish + safe bottom-menu entry (`🚀 Викторина в окне` → fresh inline `🚀 Открыть викторину`).

## Next recommended item
Run expanded MVP QA with 2–3 real users/devices; collect UX/latency findings before changing default UX.

## Next technical sprint
### Repo-only FastAPI Mini App API implementation
- Scope: implement FastAPI + uvicorn Mini App API layer in repository code/tests only, preserving current endpoint contracts and quiz/session semantics.
- Phase 1 guardrails (explicit):
  - production CD must **not** start FastAPI in this phase;
  - production Mini App traffic must **not** route to FastAPI in this phase;
  - `MINI_APP_API_BASE_URL` and reverse proxy upstream remain pointed to the current legacy Mini App API;
  - production bot + current Mini App API runtime behavior remains unchanged.
- Why this shape:
  - reduce migration risk by validating implementation quality before traffic cutover;
  - keep user-visible behavior stable while hardening tests/observability hooks;
  - preserve safe rollback posture before production switch-over.
- Product/runtime invariants:
  - `/quiz` remains default classic Telegram flow;
  - Mini App remains opt-in (`/ui`, `🚀 Викторина в окне`);
  - SQLite remains current runtime store.
- Data-layer position:
  - PostgreSQL and Redis are explicitly deferred; PostgreSQL is a later option only if concurrency/analytics/ops needs require it.
- Non-goals (Phase 1):
  - no production routing/CD/runtime switch;
  - no FastAPI rewrite of Telegram bot handlers;
  - no frontend rewrite;
  - no scoring/session schema changes;
  - no `/quiz` behavior change.

## Later sprint
### FastAPI production switch-over
- **Status: in progress (Phase 2 switch-over PR).**
- Implemented via separate explicit switch-over PR after Phase 1 repo-only implementation is merged and reviewed.
- Switch-over PR responsibilities:
  1. deploy FastAPI Mini App API **instead of** current legacy production Mini App API path;
  2. update compose/CD/routing/env wiring as needed;
  3. ensure CD rebuilds/restarts both runtime services/containers after cutover:
     - `psych_quiz_bot`
     - `psych_quiz_miniapp_api`
  4. run Mini App smoke QA (`GET /miniapp/state`, `GET /miniapp/setup-options`, `POST /miniapp/setup`, `POST /miniapp/answer`, CORS/OPTIONS);
  5. analyze logs/metrics (status mix, latency, retry patterns, `database_busy_retry` rates).
- Rollback requirement:
  - keep rollback path to legacy `ThreadingHTTPServer` API via route/env/reverse-proxy switch if smoke/monitoring fails;
  - preserve endpoint contracts to keep rollback low-risk.

## Mini App roadmap
### Done (through #166)
- SQLite runtime hardening (WAL, busy timeout, explicit connection closing, indexes).
- GET diagnostics for state/answer flows.
- Pre-retry state resync.
- Early hedge recovery.
- HTTP/1.1 keep-alive + explicit content length stability.
- Visual polish for submit/feedback/readability states.
- Safe bottom-menu Mini App entry that always reissues a fresh inline launch button.

### Next
- Broader MVP QA in production-like conditions.
- Lightweight monitoring pass (latency/error buckets, retry-rate visibility, stale-state frequency).

### Medium-term
- Split overloaded `app/main.py` responsibilities.
- Extract Mini App context/service modules for cleaner ownership and testability.

### Backlog (strategic)
- Move Mini App API toward ASGI service when justified by scale/maintenance.
- Consider declarative frontend architecture if Mini App remains strategic default candidate.
