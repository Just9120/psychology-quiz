# Phase 1 proposal: topic registry and schema validation

Delivery Item ID: `LEARN-CONTOURS-PHASE1-001`

## 1. Purpose

The current product already has a topic-oriented Tests / Questions contour: approved question JSON files live under `content/questions/**`, and learners can practice by one topic, a selected topic mix, or all approved questions. The future glossary and literature contours proposed in `docs/glossary_literature_contours_rfc.md` need to reuse those same learner-facing topics without renaming or rewriting existing question files.

A shared topic registry should be introduced before implementing Glossary / Terms or Literature / Reading tracker behavior because it gives all contours one stable topic contract:

- stable `topic_id` values that do not depend on future file moves, Russian display-title edits, or UX copy changes;
- a single place to connect Tests, Glossary, and Literature around the same topic;
- explicit metadata for module provenance, display order, lifecycle status, and contour availability;
- a validation target that can check future glossary and literature files against known topics before runtime behavior changes.

This proposal is documentation/design only. It does not implement runtime behavior, does not add glossary or literature content, does not add database migrations, and does not modify existing question JSON files.

## 2. Current topic inventory

Inventory source: current files matching `content/questions/**/*.json`. All current files contain only `approved` questions, and each file uses one learner-facing `category` value.

| Module directory | File path | Existing learner-facing category/title | Approved question count | Proposed stable `topic_id` | Naming / slug notes |
|---|---|---|---:|---|---|
| `module1` | `content/questions/module1/fiziologiya_vnd.json` | `Физиология ВНД` | 57 | `fiziologiya_vnd` | Uses the existing filename slug; abbreviation `ВНД` should stay stable in the display title, while the ID preserves the established transliteration. |
| `module1` | `content/questions/module1/obschaya_psihologiya.json` | `Общая психология` | 56 | `obschaya_psihologiya` | Uses the existing filename slug; note the transliteration `obschaya` rather than alternatives such as `obshchaya`. |
| `module1` | `content/questions/module1/psihofiziologiya.json` | `Психофизиология` | 71 | `psihofiziologiya` | Uses the existing filename slug; no immediate slug risk beyond transliteration consistency. |
| `module1` | `content/questions/module1/fiziologiya_cheloveka.json` | `Физиология человека` | 55 | `fiziologiya_cheloveka` | Uses the existing filename slug; no immediate slug risk. |
| `module1` | `content/questions/module1/vvedenie_v_professiyu.json` | `Введение в профессию` | 57 | `vvedenie_v_professiyu` | Uses the existing filename slug; note the doubled `ss` in `professiyu` should remain stable once adopted. |
| `module2` | `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json` | `Основы экспериментальной психологии` | 118 | `osnovy_eksperimentalnoy_psihologii` | Uses the existing filename slug; long ID but clear and already aligned to the question file. |
| `module2` | `content/questions/module2/kachestvennye_metody_issledovaniya.json` | `Качественные методы исследования` | 53 | `kachestvennye_metody_issledovaniya` | Uses the existing filename slug; long ID but clear and already aligned to the question file. |
| `module3` | `content/questions/module3/psychological_consulting.json` | `Психологическое консультирование` | 108 | `psychological_consulting` | Existing filename is English while the title is Russian; keep the ID stable if adopted, but document this mixed-language slug as intentional. |
| **Total** | `content/questions/**/*.json` | 8 active topics | **575** | — | — |

## 3. Proposed topic registry shape

### Recommendation

Use one consolidated file:

```text
content/topics.json
```

A single registry file is recommended for Phase 1 because the active inventory is small, review needs to compare all topic IDs at once, and validation can enforce global uniqueness without discovering many files. This also keeps the registry clearly separate from future per-topic contour content such as `content/glossary/<topic_id>.json` or `content/literature/<topic_id>.json`.

`content/topics/*.json` remains a reasonable later option if the topic list grows enough that per-topic ownership or review becomes more important than whole-registry visibility. Phase 1 should prefer the simpler consolidated registry.

### Proposed fields

Each topic registry entry should include:

- `id`: stable machine-readable topic identifier used by Tests, Glossary, and Literature.
- `title`: learner-facing topic title.
- `module`: source/curriculum module directory or provenance grouping, such as `module1`.
- `question_file`: existing question JSON path when the Tests / Questions contour is available.
- `status`: lifecycle state, initially `active` for current approved question topics.
- `order`: numeric ordering key for topic display and deterministic validation output.
- `available_contours`: list of currently available contours for the topic; Phase 1 should use only `questions` for current topics.
- `source_notes`: short human-readable provenance and review note.

Example:

```json
{
  "id": "kachestvennye_metody_issledovaniya",
  "title": "Качественные методы исследования",
  "module": "module2",
  "question_file": "content/questions/module2/kachestvennye_metody_issledovaniya.json",
  "status": "active",
  "order": 220,
  "available_contours": ["questions"],
  "source_notes": "Existing approved question topic; glossary/literature contours not implemented yet."
}
```

### Draft registry inventory

If `content/topics.json` is introduced in a later implementation task, the initial entries should be equivalent to:

```json
[
  {
    "id": "vvedenie_v_professiyu",
    "title": "Введение в профессию",
    "module": "module1",
    "question_file": "content/questions/module1/vvedenie_v_professiyu.json",
    "status": "active",
    "order": 110,
    "available_contours": ["questions"],
    "source_notes": "Existing approved question topic; glossary/literature contours not implemented yet."
  },
  {
    "id": "obschaya_psihologiya",
    "title": "Общая психология",
    "module": "module1",
    "question_file": "content/questions/module1/obschaya_psihologiya.json",
    "status": "active",
    "order": 120,
    "available_contours": ["questions"],
    "source_notes": "Existing approved question topic; glossary/literature contours not implemented yet."
  },
  {
    "id": "fiziologiya_cheloveka",
    "title": "Физиология человека",
    "module": "module1",
    "question_file": "content/questions/module1/fiziologiya_cheloveka.json",
    "status": "active",
    "order": 130,
    "available_contours": ["questions"],
    "source_notes": "Existing approved question topic; glossary/literature contours not implemented yet."
  },
  {
    "id": "fiziologiya_vnd",
    "title": "Физиология ВНД",
    "module": "module1",
    "question_file": "content/questions/module1/fiziologiya_vnd.json",
    "status": "active",
    "order": 140,
    "available_contours": ["questions"],
    "source_notes": "Existing approved question topic; glossary/literature contours not implemented yet."
  },
  {
    "id": "psihofiziologiya",
    "title": "Психофизиология",
    "module": "module1",
    "question_file": "content/questions/module1/psihofiziologiya.json",
    "status": "active",
    "order": 150,
    "available_contours": ["questions"],
    "source_notes": "Existing approved question topic; glossary/literature contours not implemented yet."
  },
  {
    "id": "osnovy_eksperimentalnoy_psihologii",
    "title": "Основы экспериментальной психологии",
    "module": "module2",
    "question_file": "content/questions/module2/osnovy_eksperimentalnoy_psihologii.json",
    "status": "active",
    "order": 210,
    "available_contours": ["questions"],
    "source_notes": "Existing approved question topic; glossary/literature contours not implemented yet."
  },
  {
    "id": "kachestvennye_metody_issledovaniya",
    "title": "Качественные методы исследования",
    "module": "module2",
    "question_file": "content/questions/module2/kachestvennye_metody_issledovaniya.json",
    "status": "active",
    "order": 220,
    "available_contours": ["questions"],
    "source_notes": "Existing approved question topic; glossary/literature contours not implemented yet."
  },
  {
    "id": "psychological_consulting",
    "title": "Психологическое консультирование",
    "module": "module3",
    "question_file": "content/questions/module3/psychological_consulting.json",
    "status": "active",
    "order": 310,
    "available_contours": ["questions"],
    "source_notes": "Existing approved question topic; English filename slug retained as stable ID candidate; glossary/literature contours not implemented yet."
  }
]
```

## 4. Phase 1 schema validation approach

A future focused implementation task should add repository-level validation before any runtime code consumes the registry. The first validator should be static and CI-friendly; it should not seed the database or change runtime state.

Recommended validation rules for `content/topics.json`:

1. The file must be valid JSON and contain a list of topic objects.
2. Every topic must include `id`, `title`, `module`, `question_file`, `status`, `order`, `available_contours`, and `source_notes`.
3. `id` must be unique, lowercase ASCII, and match `^[a-z0-9_]+$`.
4. `title`, `module`, `question_file`, and `source_notes` must be non-empty strings.
5. `module` should match the parent directory of `question_file` for current question topics.
6. `question_file` must exist when `available_contours` contains `questions`.
7. The question file must contain at least one `approved` item when `status` is `active` and `available_contours` contains `questions`.
8. The question file should use exactly one `category` value, and that value should match the registry `title` for current question-backed topics.
9. `status` should be one of `active`, `draft`, `deprecated`, or `placeholder`.
10. `order` must be an integer and unique across active topics.
11. `available_contours` should contain only known contour identifiers. Initially the only implemented value should be `questions`; future values may include `glossary` and `literature` only after separate focused implementation tasks.
12. The validator should report all detected errors in one run so content reviewers can fix batches efficiently.

Future glossary and literature validators should reference the same registry by `topic_id` and reject entries whose `topic_id` is missing, deprecated, or unavailable for the relevant contour.

## 5. Runtime and rollout boundaries

Phase 1 should remain non-runtime until a separate task explicitly changes application behavior. In particular:

- existing `content/questions/**/*.json` files should remain stable;
- active quiz categories should continue to be loaded from approved question records through the current database seeding path;
- `content/topics.json` should not become runtime authority until a later migration plan defines compatibility, fallback behavior, and rollout checks;
- glossary and literature content should not be added as part of the registry/schema validation task;
- no database migrations are needed for this proposal.

## 6. Open decisions for a future implementation task

- Whether the first implementation should add only `content/topics.json`, only a validator, or both together.
- Whether `topic_id` should be stored in question JSON later or remain an external mapping through `question_file` and `category`.
- Whether registry order should mirror current runtime category ordering or establish a new contour-first topic ordering.
- When, if ever, the mixed-language `psychological_consulting` ID should be normalized. The Phase 1 recommendation is to keep it stable if adopted.
