# Literature Source Inventory

## Purpose and scope

This document tracks static source-list inventory for the future Literature / Reading Tracker contour. It records which source lists are known, which topic IDs they map to, and whether their bibliography has been seeded into repository content.

Repository literature files describe reading metadata only. They must not store personal user reading progress.

## Current Drive source-list inventory

| Drive source-list title | Topic ID | Current repository status |
|---|---|---|
| `Список литературы. Общая психология` | `obschaya_psihologiya` | Extracted and seeded in this PR from Drive source `1Qu7CXXravaMnHmmsgSDTeEfgAK36uzZZ`. |
| `Список литературы. Физиология человека` | `fiziologiya_cheloveka` | Source exists; extraction pending because text extraction returned empty. |
| `Список литературы.Физиология высшей нервной деятельности` | `fiziologiya_vnd` | Source exists; extraction pending because text extraction returned empty. |
| `Список литературы. Психофизиология` | `psihofiziologiya` | Source exists; extraction pending because text extraction returned empty. |

## Boundary for this scaffold

This scaffold does not implement user reading progress, reminders, reading plans, runtime UI, Mini App behavior, API behavior, database changes, migrations, or runtime storage.

Static literature entry `status` values describe repository content lifecycle state only, such as `draft`, `review`, `approved`, `deprecated`, or `placeholder`. Per-user reading states such as `not_started`, `in_progress`, `read`, `revisit`, or `skipped` belong only to future runtime/user state and must not be stored in repository content files.

## Remaining limitations

Only `Список литературы. Общая психология` has been seeded. The remaining source lists require readable extraction or manual bibliographic normalization before content entries are added. The seeded entries from `Список литературы. Общая психология` are marked `review` where OCR artifacts or incomplete bibliographic metadata require follow-up verification.
