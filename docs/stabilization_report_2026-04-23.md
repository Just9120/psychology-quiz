# Stabilization / Cleanup Audit Report

Date: 2026-04-23
Scope: runtime path and lag/noise complexity audit (no product behavior changes).

## 1) Executive Summary

- **Runtime noise is confirmed**, primarily from **code-path complexity and redundant runtime operations**, not from obvious infrastructure/deploy misconfiguration.
- The most likely sources of local “lag” feeling are:
  1. extra Telegram API round-trips in menu hide/show and result transitions;
  2. redundant per-action DB safety/migration checks (`PRAGMA table_info`) on hot paths;
  3. growing branching/duplication in quiz startup callbacks (single/all/selected mix) and repeated user/session validation blocks.
- Infra/deploy scripts look mostly deterministic and not on the hot path for user interaction; they are unlikely to explain in-chat lag.

## 2) Confirmed findings (code-confirmed only)

### F1. Schema/migration checks are executed on hot runtime paths

Confirmed:
- `create_or_load_user()` calls `ensure_users_reading_mode_column()` every time it is used.
- `get_user_reading_mode()` and `set_user_reading_mode()` also call `ensure_users_reading_mode_column()`.
- `get_quiz_session()` calls `ensure_quiz_sessions_difficulty_mode_column()`.
- Selected-categories getters/setters call `ensure_quiz_session_selected_categories_table()`.

Impact:
- Each ensure call performs schema introspection (`PRAGMA table_info(...)`) or DDL checks, which are migration-safety concerns, not request-time concerns.
- On frequent callbacks (answer/next/start mode changes), this adds avoidable DB work and contributes to runtime jitter.

### F2. Extra Telegram API chatter in menu/result transitions

Confirmed:
- `remove_main_menu_for_active_quiz()` sends a placeholder message and then immediately deletes it (2 API calls).
- `hide_menu_button_handler()` does the same pattern, then also attempts to delete the triggering user message (up to 3 calls total).
- `send_quiz_result_with_main_menu()` tries to delete previous message and then sends a new one (2 calls).

Impact:
- In normal flows this increases network round-trips and visible jitter.
- Functionality is correct, but technically noisy.

### F3. Post-quiz callback branch appears unreachable from current UX rendering

Confirmed:
- `build_post_quiz_keyboard()` exists with `postquiz:*` callbacks.
- Handlers for `postquiz:new/help/repeat` are registered.
- But finish/result path currently uses `send_quiz_result_with_main_menu()` without attaching this inline keyboard.

Impact:
- Dead branch increases handler complexity and cognitive load.
- Not a direct lag source, but it is accumulated runtime-flow complexity from incremental fixes.

### F4. Answer/next flow includes repeated DB reads and repeated user upsert checks

Confirmed:
- In `answer_callback()`, per answer: session read → user upsert/read → membership check → current unanswered question read → save answer → answered count read → reading mode read (+ optional finalize read/update).
- In `next_callback()`, again: session read → user upsert/read before showing next question.

Impact:
- Correct behavior, but multiple near-overlapping validations/reads per click.
- Adds DB noise and callback latency under active usage.

### F5. Startup flow branching duplication is high (single/all/selected mix)

Confirmed:
- Separate callback chains for count+difficulty by mode (`qcnt`, `qcntall`, `qcntselmix`, `qmode`, `qmodeall`, `qmodeselmix`) contain repeated parsing/validation patterns and repeated “select limit + mode validation + user load + session create + store questions”.

Impact:
- Higher maintenance surface and bug-introduction probability.
- This is complexity pressure rather than direct CPU bottleneck, but it contributes to fragile runtime behavior after many point fixes.

## 3) Cleanup candidates (safe, behavior-preserving)

### High value / low risk

1. **Move schema ensure checks out of hot path**
- File: `app/db.py`
- Place: `create_or_load_user`, `get_user_reading_mode`, `set_user_reading_mode`, `get_quiz_session`, selected categories getters/setters
- Noise: repeated migration checks during normal requests
- Why simplify: these checks are already executed at startup via `init_db_connection()` and in init script
- Risk: low (retain startup/init checks; remove request-time ensures)
- Benefit: lower DB overhead in frequent callbacks; less jitter

2. **Reduce send+delete placeholder pattern for keyboard hide**
- File: `app/main.py`
- Place: `remove_main_menu_for_active_quiz`, `hide_menu_button_handler`
- Noise: deliberate extra messages only to remove keyboard
- Why simplify: keep one deterministic path where possible; avoid extra transient messages
- Risk: low-medium (Telegram client quirks must be respected)
- Benefit: fewer network calls and less perceived lag

3. **Remove or wire post-quiz action branch consistently**
- File: `app/main.py`
- Place: `build_post_quiz_keyboard`, `post_quiz_action_callback`, finish/result send path
- Noise: registered handler path not used by current final-result rendering
- Why simplify: either delete dead branch or attach keyboard in result message
- Risk: low
- Benefit: lower handler complexity, clearer runtime flow

### Medium value

4. **Extract shared callback parsing/validation helpers**
- File: `app/main.py`
- Place: question count / difficulty callbacks and mix start logic
- Noise: repeated parsing and mode/limit checks
- Why simplify: shrink branch sprawl without redesign
- Risk: medium (touches multiple handlers)
- Benefit: easier maintenance, lower regression probability

5. **Consolidate repeated session ownership checks**
- File: `app/main.py`
- Place: `answer_callback`, `next_callback`, repeat flow
- Noise: same user/session guard logic repeated with small variations
- Why simplify: local helper returning `(session, user_row)` or error response path
- Risk: medium
- Benefit: cleaner hot path, fewer inconsistency risks

### Low value / optional

6. **Micro-cleanup: remove unused variables and align “finalized result” send paths**
- File: `app/main.py`
- Place: `show_finished_quiz_message(session_id unused)`, duplicate final-message composition styles
- Risk: low
- Benefit: readability and smaller cognitive load

## 4) Lag hypotheses (facts vs inference)

### Confirmed contributors
- **Telegram API noise** from send+delete patterns and delete+send transitions is real.
- **DB runtime noise** from repeated schema ensure checks is real.
- **State/handler complexity** is real (duplicated callback branches and dead-ish postquiz branch).

### Likely (inference from code)
- User-visible “bot lagging” is more likely due to many small network+DB operations per action rather than raw server CPU exhaustion.

### Not confirmed in this audit (needs measurement)
- Actual server resource bottlenecks (CPU/memory/IO spikes).
- Telegram API latency distribution by method (`editMessageText`, `deleteMessage`, `sendMessage`).
- SQLite lock contention under concurrent users.

Recommended measurement before infra changes:
- Add lightweight timing logs around hot callbacks (`answer_callback`, `next_callback`, `send_current_question`) and around each Telegram API call block.
- Log DB call durations for `get_current_unanswered_question`, `save_quiz_answer`, `finalize_quiz_session`.

## 5) Safe next-step plan (small PRs)

### PR A (small, high confidence): “Hot-path DB ensure cleanup”
- Scope:
  - keep schema ensures in startup/init only (`init_db_connection`, `scripts/init_db.py`);
  - remove request-time ensure calls from hot db getters/setters.
- Why safe:
  - schema already provisioned at boot and deploy seed/init path;
  - no UX or product behavior change.
- Expected improvement:
  - fewer DB meta-queries per callback;
  - reduced local latency variance.

### PR B (small, user-visible smoothness): “Telegram interaction noise trim”
- Scope:
  - simplify keyboard hide/show transitions to minimize send+delete chains;
  - unify final result rendering path and either remove unused postquiz callbacks or actually render corresponding inline keyboard.
- Why safe:
  - same user journey, fewer API operations.
- Expected improvement:
  - lower perceived lag in quiz start/finish transitions;
  - cleaner runtime handler map.

---

## Appendix: Files reviewed

Required runtime files:
- `app/main.py`
- `app/db.py`
- `scripts/init_db.py`
- `scripts/seed_questions.py`
- `sql/schema.sql`
- `README.md`
- `docs/TZ_psychology_quiz.md`

Additional infra context:
- `.github/workflows/deploy-production.yml`
- `deploy.sh`
