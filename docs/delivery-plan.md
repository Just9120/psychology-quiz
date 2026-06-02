# Delivery Plan

## Current status dashboard
- Module 1 stable baseline; Module 2 limited active scope.
- `/quiz` remains the default classic Telegram chat entry point.
- Production classic chat UX: `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=true` is now the recommended implementation; a 15-question classic smoke completed without hangs, and the cleaner bottom reply keyboard UX is preferred.
- Classic inline callback mode remains available only as legacy/fallback (`CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=false`).
- `/ui` remains experimental opt-in Mini App runner; Mini App does not become the default UX.
- Mini App answer stalls are mitigated: hedged cases improved from roughly 3.4s to roughly 1.3s in observed production behavior.
- Current delivery posture: observe/QA the stabilized production paths with safe classic latency buckets and existing Mini App request/client telemetry before another immediate code change.

## Recently completed PRs (#199–#204)
- #199: webhook/logging/security cleanup and safer operational diagnostics.
- #200: classic inline callback diagnostics for update ingress and callback latency investigation.
- #201: Mini App telemetry for answer/setup state, retries, and safe diagnostics.
- #202: Mini App production diagnostics/operational follow-up for stalled answer reports.
- #203: Mini App hedge mitigation for answer stalls, reducing hedged-case wait time.
- #204: classic reply keyboard mode for `/quiz`, moving answer/`Далее` controls to bottom Telegram reply keyboard text updates.

## Next recommended item
Observe production and run focused manual QA instead of starting another immediate code PR:
1. Keep `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=true` enabled for classic production UX.
2. Run 10–15 question classic `/quiz` smoke checks via bottom reply keyboard after restarts/deploys.
3. Watch safe classic logs: `classic_text_answer_ingress`, `classic_text_answer_latency`, `classic_text_next_ingress`, `classic_text_next_latency`; latency lines include `status`, `elapsed_ms`, and `latency_bucket`.
4. Continue Mini App QA for answer latency/retry behavior, especially hedged cases and completed-result flow.
5. Escalate to a new code PR only if observation shows reproducible hangs, regressions, or unsafe logs.

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
