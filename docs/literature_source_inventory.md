# Literature Source Inventory

## Purpose and scope

This document tracks static source-list inventory for the future Literature / Reading Tracker contour. It records which source lists are known, which topic IDs they map to, and whether their bibliography has been seeded into repository content.

Repository literature files describe reading metadata only. They must not store personal user reading progress.

## Current Drive source-list inventory

| Drive source-list title | Topic ID | Current repository status |
|---|---|---|
| `Список литературы. Общая психология` | `obschaya_psihologiya` | Extracted and seeded in this PR from Drive source `1Qu7CXXravaMnHmmsgSDTeEfgAK36uzZZ`. |
| `Список литературы. Физиология человека` | `fiziologiya_cheloveka` | Seeded from rendered PDF source `1PwOHb_wdshbIgg9-cmO1d4E7iJzere5S`; raw text extraction returned empty. |
| `Список литературы.Физиология высшей нервной деятельности` | `fiziologiya_vnd` | Seeded from rendered PDF source `1H9qgOSUyfvrVRo1Q7hkVG7BgnjHjYuaX`; raw text extraction returned empty. |
| `Список литературы. Психофизиология` | `psihofiziologiya` | Seeded from rendered PDF source `1w7N6-xBrVvPdIx9TxBoEaCZNa4qz8_Ni`; raw text extraction returned empty. |

## Boundary for this scaffold

This scaffold does not implement user reading progress, reminders, reading plans, runtime UI, Mini App behavior, API behavior, database changes, migrations, or runtime storage.

Static literature entry `status` values describe repository content lifecycle state only, such as `draft`, `review`, `approved`, `deprecated`, or `placeholder`. Per-user reading states such as `not_started`, `in_progress`, `read`, `revisit`, or `skipped` belong only to future runtime/user state and must not be stored in repository content files.

## Remaining limitations

The currently available Module 1 source lists have been seeded where the rendered PDFs were readable, even when raw PDF text extraction was empty. All seeded bibliographic metadata remains marked `review`; years, editions, publisher details, title normalization, and editor/translator roles still require human bibliographic verification before approval.

## Module 1 pedagogical metadata normalization

All seeded Module 1 literature entries now include static pedagogical metadata for topic-level ordering, cross-topic ordering, learner-facing rationale, conservative learning outcomes, tags, prerequisites, and optional estimated reading time. This metadata is intended to support future Literature-contour logic such as “what to read next” or reading-plan construction without implementing runtime behavior in this scaffold.

User reading progress remains out of repository content and belongs only to future runtime/user state. All seeded entries remain in `status: "review"` pending separate human bibliographic verification.
