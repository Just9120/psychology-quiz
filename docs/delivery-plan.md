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
