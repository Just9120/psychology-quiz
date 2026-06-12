# Delivery Plan

## Current status dashboard
- Module 1 stable baseline; Module 2 limited active scope.
- `/quiz` remains the default classic Telegram chat entry point.
- Production classic chat UX: `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=true` remains the recommended implementation; the cleaner bottom reply keyboard UX is preferred for answers and `Далее`.
- Classic inline callback mode remains available only as legacy/fallback (`CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=false`).
- `/ui` / `🚀 В окне` remains opt-in Mini App runner; Mini App does not become the default UX.
- Mini App setup/question/result screens are now product-facing after P1/P2 polish.
- UX-polish runtime smoke passed after manual Telegram/Mini App checks: no current bugs reported, classic `/quiz` + reply keyboard remains stable, and the Mini App opt-in flow has been checked.
- Current delivery posture: observation/manual QA only; do not start another immediate code/refactor PR while no reproducible bugs are present.

## Archived completed delivery groups
Historical completed delivery groups are archived in `docs/delivery-plan-archive.md`.

Current outcome:
- Classic `/quiz` with reply keyboard mode remains stable.
- UX-polish smoke passed with no current bugs reported after manual Telegram/Mini App checks.
- Mini App opt-in flow now has product-facing setup, question, and result screens after P1/P2 polish.
- Delivery posture is observation/QA, not another immediate code PR.

## Next recommended item
Continue observation/manual QA instead of starting another immediate code PR:
1. Keep `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=true` enabled for classic production UX.
2. Run focused classic `/quiz` and Mini App opt-in smoke checks after restarts/deploys.
3. Watch only for reproducible regressions, hangs, unsafe logs, or user-reported bugs with enough detail to reproduce.
4. Avoid speculative code/refactor PRs while no bugs are present.
5. Consider future work only after new evidence from QA/production observation or a clear product priority.

## Product/runtime invariants
- `/quiz` remains default classic Telegram flow.
- Mini App remains opt-in (`/ui`, `🚀 В окне`) and separate from classic chat UX.
- Standalone Web UI/PWA remains out of scope.
- SQLite remains current runtime store; JSON files in the repository remain question-bank source of truth.
- Docs-only changes do not require runtime sync.

## Later technical direction
- Broader MVP QA in production-like conditions.
- Continue lightweight monitoring only if observation shows new gaps after the current classic latency buckets and Mini App telemetry.
- Split overloaded `app/main.py` responsibilities when a code sprint is justified.
- Extract Mini App context/service modules for cleaner ownership and testability.
- Move Mini App API/runtime architecture forward only after observation confirms the next bottleneck and rollback posture.
