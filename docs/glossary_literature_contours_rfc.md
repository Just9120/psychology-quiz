# RFC: Topic-based glossary and literature learning contours

Delivery Item ID: `LEARN-CONTOURS-RFC-001`

## 1. Problem statement

The current product is centered on topic-based tests in the Telegram quiz bot. The active question bank is stored in repository JSON files under `content/questions/**`, and the quiz experience lets learners practice by topic, selected topic mix, or all currently approved questions.

Future learning support should be able to expand beyond questions into additional modes for terminology learning and guided reading while preserving the existing topic-based content model. This RFC proposes three separate learning contours:

1. tests / questions;
2. glossary / terms;
3. literature / reading tracker.

This document is a design proposal only. It does not authorize or implement runtime behavior, data migrations, source extraction, reminders, reading plans, glossary content, or literature content.

## 2. Contour model

A learning contour is a top-level mode of study with its own content type, UX flow, and progress semantics.

### Tests / Questions

The existing contour. It uses approved question JSON files and runtime quiz state to support topic-based self-checking.

### Glossary / Terms

A proposed terminology-learning contour. It would organize key terms, aliases, definitions, examples, confusable concepts, difficulty, and source references by topic.

### Literature / Reading tracker

A proposed guided-reading contour. It would provide a curated checklist of readings by topic, with pedagogical ordering, reading levels, learning outcomes, and per-user progress stored in runtime/user state.

Literature is not just a bibliography. The intended product shape is a reading tracker that helps users decide what to read, continue in-progress reading, mark completion, revisit important items, and eventually build reading plans.

## 3. Navigation model

Navigation should be contour-first, then topic-based. Each contour owns its own “all items” mode; there should not be one global cross-contour “all” mode.

```text
Tests
- Topic A
- Topic B
- All questions

Glossary
- Topic A
- Topic B
- All terms

Literature
- Topic A
- Topic B
- All literature
- Reading plan / What to read next
```

Implications:

- `All questions` aggregates only question items inside the Tests contour.
- `All terms` aggregates only glossary entries inside the Glossary contour.
- `All literature` aggregates only reading entries inside the Literature contour.
- `Reading plan / What to read next` belongs to the Literature contour because it depends on reading priority, pedagogical hierarchy, prerequisites, and user reading state.

## 4. Topic model

Topic is the shared organizing unit across all contours.

The existing question topic files should remain stable. This RFC does not require renaming, moving, or rewriting existing `content/questions/**/*.json` files.

Modules may remain useful as metadata for source provenance, curriculum grouping, reporting, or administration. However, module should not be the primary UX grouping for future glossary or literature flows. Learners should primarily choose a contour and then a topic.

A future topic registry may help all contours share stable topic identifiers, display names, module metadata, ordering, and availability flags without requiring the current question files to change immediately.

## 5. Proposed repository content structure

This section describes possible future static content locations. It is not implemented by this RFC.

### Topic registry options

A future topic registry could be either:

```text
content/topics/*.json
```

or one consolidated file such as:

```text
content/topics.json
```

The registry could include stable fields such as:

```json
{
  "id": "general_psychology",
  "title": "Общая психология",
  "module": "module1",
  "order": 20,
  "status": "active"
}
```

The exact registry shape should be decided during a schema-validation phase, after checking compatibility with existing question categories and runtime category loading.

### Glossary content

Proposed future location:

```text
content/glossary/<topic_id>.json
```

Each file would hold glossary terms for one topic. This keeps glossary review focused and aligns terminology learning with the same topic model used by tests.

### Literature content

Proposed future location:

```text
content/literature/<topic_id>.json
```

Each file would hold curated static metadata for readings in one topic. Per-user reading progress must not be stored in these repository files.

## 6. Glossary schema proposal

A future glossary entry may use the following fields:

```json
{
  "id": "general_psychology_attention",
  "topic_id": "general_psychology",
  "term": "Внимание",
  "aliases": ["attentional process"],
  "definition": "Long-form source-backed explanation of the term.",
  "short_definition": "Brief learner-facing definition.",
  "examples": [
    "Example of the concept in a learning or assessment context."
  ],
  "confusable_with": [
    "general_psychology_perception"
  ],
  "source_refs": [
    "source-pack-or-snippet-reference"
  ],
  "difficulty": "medium",
  "status": "draft"
}
```

Field notes:

- `id` should be stable and unique across glossary entries.
- `topic_id` links the term to the shared topic model.
- `term` is the primary learner-facing term.
- `aliases` captures alternate names, abbreviations, translations, or common variants.
- `definition` is the fuller explanation.
- `short_definition` supports compact review UI.
- `examples` supports applied understanding.
- `confusable_with` points to related entries that learners often confuse.
- `source_refs` records supplied evidence references.
- `difficulty` can support filtering or progressive learning.
- `status` should distinguish draft, review, approved, deprecated, or placeholder content according to a future validation policy.

## 7. Literature schema proposal

A future literature entry may use the following fields:

```json
{
  "id": "general_psychology_intro_chapter_01",
  "topic_id": "general_psychology",
  "title": "Introductory reading title",
  "authors": ["Author A", "Author B"],
  "year": 2026,
  "source_type": "book_chapter",
  "source_ref": "source-pack-or-snippet-reference",
  "reading_level": "foundation",
  "priority": "high",
  "global_order": 100,
  "topic_order": 10,
  "prerequisites": [],
  "estimated_minutes": 45,
  "tags": ["introductory", "conceptual"],
  "why_read": "Why this reading matters for the learner.",
  "learning_outcomes": [
    "Explain the central concept after reading."
  ],
  "status": "placeholder"
}
```

Field notes:

- `id` should be stable and unique across literature entries.
- `topic_id` links the reading to the shared topic model.
- `title`, `authors`, `year`, `source_type`, and `source_ref` describe the source.
- `reading_level` should use the pedagogical hierarchy described below.
- `priority` helps choose what appears in “what to read next”.
- `global_order` supports cross-topic ordering inside the Literature contour.
- `topic_order` supports topic-specific sequencing.
- `prerequisites` identifies readings or concepts that should come first.
- `estimated_minutes` supports future planning by deadline or daily available time.
- `tags` support filtering and discovery.
- `why_read` explains the rationale for learners.
- `learning_outcomes` define what the learner should gain.
- `status` should distinguish verified entries from placeholders and other lifecycle states.

## 8. User reading state model

Static literature metadata belongs in repository content files. Personal reading progress belongs in runtime database/user state, not static GitHub content files.

A future runtime user-reading-state record may include:

```json
{
  "user_id": 123456789,
  "literature_id": "general_psychology_intro_chapter_01",
  "reading_status": "in_progress",
  "progress_percent": 40,
  "started_at": "2026-06-13T12:00:00Z",
  "completed_at": null,
  "remind_at": null,
  "notes": "User-private note or short reflection."
}
```

Supported reading statuses:

- `not_started`;
- `in_progress`;
- `read`;
- `revisit`;
- `skipped`.

Boundary rules:

- Repository literature files describe readings, not personal user progress.
- Runtime/user state stores individual checklist status and progress.
- User notes should be treated as user data and should not be committed to repository content files.
- `remind_at` is reserved for future reminders and does not imply reminder implementation in this RFC.

## 9. Reading hierarchy

The Literature contour should support this pedagogical reading hierarchy:

- `foundation` — introductory orientation, vocabulary, and conceptual framing;
- `core` — central required material for topic comprehension;
- `applied` — practical cases, examples, exercises, and use in context;
- `deepening` — material that extends or complicates core understanding;
- `advanced` — specialized, dense, research-heavy, or interpretation-heavy material;
- `reference` — lookup material that may not need linear reading.

Reading order should be curated pedagogically, not based on Google Drive file order or incidental source-folder order.

Ordering principles:

- foundations first;
- methodology before interpretation-heavy material;
- core concepts before applied cases;
- practice/examples after conceptual framing;
- advanced articles after basic comprehension;
- references available as support material rather than mandatory linear steps.

## 10. Literature checklist and planning

Future Literature UX may support:

- marking readings as `not_started`, `in_progress`, `read`, `revisit`, or `skipped`;
- continuing the current in-progress reading;
- showing “what to read next” based on topic, status, hierarchy, priority, prerequisites, and ordering;
- generating a reading plan by topic, deadline, or available daily time;
- optional reminders later.

These capabilities are proposed future product directions only. This RFC does not implement checklist storage, reading plans, reminder scheduling, notification delivery, or user-facing Literature navigation.

## 11. Provenance and source extraction boundary

Codex must not access or claim access to Google Drive folders, original PDFs, or other external source files for this RFC.

Drive/PDF/source extraction should be handled by a separate source-review pass. That pass should provide extracted source evidence to Codex as supplied snippets, structured notes, or reviewed metadata.

Future literature and glossary entries should distinguish verified sources from placeholders. For example, `status` values or review metadata can make it clear whether an entry is:

- a placeholder needing source review;
- extracted from supplied snippets;
- human-reviewed;
- approved for learner-facing use;
- deprecated or superseded.

No source-backed certification is claimed by this RFC.

## 12. Phased implementation plan

- **Phase 0: RFC** — create this proposal and keep runtime behavior unchanged.
- **Phase 1: Topic registry / schema validation proposal** — design stable topic IDs, registry shape, schema validation, and compatibility with existing question files.
- **Phase 2: Glossary MVP for one topic** — add source-backed glossary content for one topic, validation, and a minimal review workflow.
- **Phase 3: Literature catalog MVP for one topic** — add curated literature metadata for one topic, including hierarchy, ordering, and verified/placeholder status rules.
- **Phase 4: Reading checklist user state** — add runtime/user-state persistence for literature progress and checklist actions.
- **Phase 5: Reading plan / reminders** — add planning and optional reminders after checklist state is stable.
- **Phase 6: Source extraction and curation across the full Drive folder** — perform a dedicated source-review and curation pass outside Codex’s direct-source-access boundary, then provide reviewed evidence for repository content updates.

## 13. Workflow compliance

This RFC does not change current runtime behavior, question JSON, database schema, active quiz UX, CI/CD, deployment configuration, Docker files, secrets, or runtime state.

It also does not add glossary content, literature content, migrations, dependencies, reminders, reading plans, source extraction, or source-backed certification.
