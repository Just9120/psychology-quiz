# RFC: Literature / Reading Tracker runtime contour

Delivery Item ID: `LITERATURE-RUNTIME-RFC-004`

## 1. Status and scope

This RFC defines the future product and technical boundary for turning the Literature contour from a static catalog scaffold into a user-facing Reading Tracker.

It is documentation-only. It does not implement runtime behavior, API endpoints, database migrations, Mini App UI, Telegram bot handlers, reminders, reading plans, deployment changes, or content changes.

The current static catalog layer remains authoritative only for repository-managed reading metadata in `content/literature/*.json`. Runtime user progress is deferred to later implementation PRs.

## 2. Product intent

Literature is not just a bibliography. The intended Literature contour is a guided reading experience that helps learners:

- decide what to read next;
- continue readings already in progress;
- mark readings as completed;
- revisit important readings;
- skip readings intentionally when they are not relevant;
- eventually build reading plans by topic, deadline, or available daily reading time.

The contour should remain pedagogical rather than archival: readings are ordered, tagged, explained, and connected to learning outcomes so the user can understand why an item is recommended.

## 3. Contour placement and navigation model

Literature should be a separate learning contour alongside the existing learning contours:

1. Tests / Questions;
2. Glossary / Terms;
3. Literature / Reading Tracker.

Navigation should be contour-first, then topic-based:

```text
Choose contour
├── Tests / Questions
│   ├── Topic
│   └── All questions
├── Glossary / Terms
│   ├── Topic
│   └── All terms
└── Literature / Reading Tracker
    ├── Topic
    ├── All literature
    └── What to read next
```

There should not be one global cross-contour `all` mode. Each contour owns its own aggregate mode because the item type, progress semantics, and recommendation rules are different.

## 4. Static metadata authority

Static Literature metadata lives in repository JSON files under:

```text
content/literature/*.json
```

Those files describe readings and their pedagogical placement. They may include:

- stable `id` and `topic_id`;
- bibliographic metadata such as title, authors, year, and type;
- repository lifecycle `status` such as `draft`, `review`, `approved`, `deprecated`, or `placeholder`;
- `reading_level` and `priority`;
- `topic_order` and `global_order`;
- tags;
- learner-facing `why_read` rationale;
- learning outcomes;
- prerequisites;
- optional estimated reading time;
- internal source references or notes used for review and provenance.

Repository static metadata must not store personal reading progress. Per-user reading states such as `not_started`, `in_progress`, `read`, `revisit`, and `skipped` belong only to future runtime/user state.

## 5. Future user reading state model

A future runtime user-state record should connect one Telegram/Mini App user to one static literature item. Candidate fields:

| Field | Purpose |
|---|---|
| `user_id` | Runtime user identifier, aligned with existing Mini App auth conventions. |
| `literature_id` | Stable id of the static literature entry. |
| `reading_status` | Per-user reading state. |
| `progress_percent` | Optional integer progress marker, usually `0`–`100`. |
| `started_at` | Timestamp when the user first marked or opened the item as started. |
| `completed_at` | Timestamp when the user marked the item as read. |
| `updated_at` | Timestamp for ordering recently changed progress records. |
| `last_opened_at` | Timestamp for continuing the most recent reading. |
| `private_note` | Optional private user note or reflection, if notes are implemented. |
| `remind_at` | Reserved nullable timestamp for future reminders only. |

Supported `reading_status` values:

- `not_started`;
- `in_progress`;
- `read`;
- `revisit`;
- `skipped`.

These statuses are runtime/user-state values. They must not be written into repository literature JSON `status` fields, which remain static lifecycle statuses.

If notes are included, they are private user data. Their content must not be committed to the repository, exposed in static artifacts, or logged as ordinary application diagnostics.

## 6. Storage option: SQLite-backed runtime state

A safe future implementation can add SQLite-backed persistence for Reading Tracker state after a separate migration design and review.

Proposed table name:

```text
user_literature_progress
```

Draft schema shape:

```sql
CREATE TABLE user_literature_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    literature_id TEXT NOT NULL,
    reading_status TEXT NOT NULL,
    progress_percent INTEGER,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    last_opened_at TEXT,
    private_note TEXT,
    remind_at TEXT,
    UNIQUE (user_id, literature_id)
);
```

Draft indexes:

```sql
CREATE INDEX idx_user_literature_progress_user_id
    ON user_literature_progress (user_id);

CREATE INDEX idx_user_literature_progress_reading_status
    ON user_literature_progress (reading_status);

CREATE INDEX idx_user_literature_progress_user_updated
    ON user_literature_progress (user_id, updated_at);
```

Implementation status:

- `LITERATURE-RUNTIME-STATE-MODEL-005` begins Phase B by adding this SQLite table and indexes through the existing idempotent schema/init style.
- No backfill is required because this is new per-user runtime state.
- Rollback should drop only `user_literature_progress` and its indexes, and only after confirming no production reading-progress data must be preserved.
- Production rollout must follow existing deployment/migration rules; this PR does not perform a manual production migration.

Implementation boundaries:

- no API endpoint implementation is added in this state-model step;
- no Mini App UI or Telegram bot UX is added in this state-model step;
- no recommendation, reminder, or reading-plan logic is added in this state-model step;
- no repository literature JSON content is changed in this state-model step.

## 7. Future Mini App API design

Candidate endpoints for a later implementation:

| Endpoint | Purpose |
|---|---|
| `GET /miniapp/literature/topics` | Return topics that have Literature entries and are available to the user. |
| `GET /miniapp/literature/items?topic_id=...` | Return static reading items for one topic or the Literature contour aggregate view. |
| `GET /miniapp/literature/state` | Return the authenticated user's reading progress state. |
| `POST /miniapp/literature/progress` | Update one reading-progress record. |
| `POST /miniapp/literature/next` | Return a deterministic next-reading recommendation. |

API boundaries:

- auth should reuse existing Mini App `initData` validation conventions;
- client input remains untrusted and must be validated server-side;
- responses should avoid exposing internal `source_refs` unless an explicit product decision says those references are learner-facing;
- errors should follow the existing Mini App API style where applicable;
- endpoints should be implemented only in future focused API PRs;
- this RFC does not change existing endpoint contracts.

## 8. Future Telegram / Mini App UX flow

Flow-level candidate UX:

1. User opens the Mini App.
2. User chooses a contour: Tests, Glossary, or Literature.
3. User chooses Literature.
4. User chooses a topic or `All literature`.
5. User sees a reading list ordered by `topic_order` for topic views or `global_order` for cross-topic views.
6. User opens item detail.
7. User can mark an item as `in_progress`, `read`, `revisit`, or `skipped`.
8. User can ask `What should I read next?`.
9. Future scope may add reading plans by deadline or available daily time.

UX boundaries:

- no UI implementation is added in this PR;
- Telegram chat UX is not changed in this PR;
- Mini App contour chooser changes are future implementation scope;
- Literature UX should not replace the default classic `/quiz` flow unless a separate product decision authorizes that change.

## 9. Deterministic “what to read next” logic

The recommendation should be deterministic and explainable. It should combine existing static metadata with future per-user state.

Suggested rules:

1. Determine the candidate set:
   - topic-specific candidates for a topic view;
   - all Literature candidates for the Literature aggregate view.
2. Exclude `read` and `skipped` items unless the user explicitly asks for revisit/review recommendations.
3. Prioritize the user's current `in_progress` items, ordered by most recent `last_opened_at` or `updated_at`.
4. For unread candidates, filter out items whose prerequisites are not satisfied when prerequisite data is available.
5. Sort remaining topic-specific candidates by:
   - `priority` (`high`, then `medium`, then `low`);
   - `reading_level` hierarchy;
   - `topic_order`;
   - stable `id` as a final tie-breaker.
6. Sort cross-topic candidates by:
   - `priority`;
   - `reading_level` hierarchy;
   - `global_order`;
   - stable `id` as a final tie-breaker.
7. Prefer `foundation` before `core`, `core` before `applied`, `applied` before `deepening`, and `deepening` before `advanced`.
8. Treat `reference` as lookup/support material. It should usually not be forced as the next linear reading unless no better candidate exists or the user explicitly asks for reference material.
9. If no eligible item remains, return an empty-state response that invites the user to revisit completed items, change topic, or wait for new approved readings.

This logic should be covered by deterministic tests when implementation begins.

## 10. Privacy and safety

- User notes are private user data.
- User notes must not be committed to repository files.
- Per-user reading progress must not be exposed in static artifacts.
- Sensitive note content must not be logged as routine diagnostics.
- API responses must be scoped to the authenticated user.
- Repository literature `status` remains static lifecycle state, not user progress.
- Reminders are future scope and require a separate privacy, scheduling, opt-in, and notification design.

## 11. Staged rollout plan

Future implementation should be staged and separately reviewable:

- **Phase A — static catalog complete and validated:** already started through the Literature scaffold, source inventory, seeded Module 1 source lists, and metadata normalization.
- **Phase B — runtime state model / migration PR:** add the user reading state table and migration with rollback/validation notes.
- **Phase C — read-only Literature API endpoints:** expose topics and static items without progress mutation.
- **Phase D — progress update endpoints:** add authenticated progress read/write behavior.
- **Phase E — Mini App Literature UI:** add contour chooser and reading list/detail UI.
- **Phase F — “what to read next”:** add deterministic recommendation logic and tests.
- **Phase G — optional reminders / reading plans:** add only after separate privacy and notification design.

Each phase should avoid broad runtime changes and should not combine DB, API, UI, bot UX, and recommendation changes into one large PR.

## 12. Non-goals for this PR

- No runtime code.
- No database migration.
- No table creation.
- No API endpoint implementation.
- No Mini App UI implementation.
- No Telegram bot UX changes.
- No reminders.
- No reading-plan generation.
- No bibliographic approval of `review` entries.
- No new source extraction.
- No changes to question bank content.
- No changes to glossary content.
- No changes to literature JSON content.
- No Docker, Compose, CI/CD, deploy, or secrets changes.

## 13. Acceptance criteria

This RFC PR is complete when:

- `docs/literature_runtime_rfc.md` exists;
- it describes product flow, state model, storage options, API candidates, UX candidates, next-reading logic, privacy, rollout, and non-goals;
- `docs/delivery-plan.md` has a compact note for `LITERATURE-RUNTIME-RFC-004`;
- no runtime, content, API, DB, UI, deployment, question-bank, glossary, or literature JSON files are changed;
- validation passes with the required documentation-only checks.
