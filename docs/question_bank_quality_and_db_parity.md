# Question bank structural quality and SQLite parity audit

## Scope

- Canonical source: `content/topics.json` active topics with the `questions` contour and their referenced JSON files.
- Active question topics covered by structural validation: 8.
- Canonical question rows in active question files: 575.
- Active approved questions covered by JSON → SQLite parity tooling: 575.
- This pass does not claim completed semantic, source-pack, or SME review for every question.
- Content corrections applied in this pass: 0. Question IDs, text, options, correct answers, explanations, source refs, and statuses were not changed.

## Structural validation results

Deterministic validation checks active approved questions for required content shape, option cardinality, answer index validity, canonical category mapping, source reference presence, and global duplicate IDs/stems.

- Duplicate question IDs: 0 found.
- Duplicate normalized question text: 0 found.
- Malformed option counts or blank options: 0 found.
- Invalid `correct_option_index` values: 0 found.
- Category mismatches against active topic titles: 0 found.
- Missing explanations: 0 found.
- Missing `source_ref` values: 0 found.

## Compact actionable quality queue

The previous full one-record-per-question manifest was removed because it over-labeled the bank with generic low-actionability heuristic flags. It is replaced by `docs/audits/question_bank_review_queue.json`, a compact queue for concrete follow-up only.

- Queue item count: 21.
- Queue cap: 50 items.
- Current queue issue type: bounded highest-severity `answer_length_cue` cases.
- Deterministic answer-length severity rule: include only cases where the keyed option is the longest option, `length(correct) / median(length(distractors)) >= 2.75`, and `length(correct) - max(length(distractors)) >= 45`; keep at most the 50 highest ratio/delta cases.
- Confirmed structural blockers, exact duplicate IDs, and duplicate normalized stems are not present in the current active approved bank.

Semantic question-quality calibration remains the next separate content PR. Queue entries are review targets, not automatic authorization to rewrite ambiguous psychology content.

## SQLite parity model

- Canonical JSON is the source of truth: `content/topics.json` plus the active topic question files.
- SQLite is a seeded runtime projection of approved canonical JSON rows.
- `scripts/audit_question_bank.py` supports content-only validation and optional read-only SQLite auditing with `--db-path`.
- SQLite audit mode opens the database with a read-only URI, runs `PRAGMA integrity_check` and `PRAGMA foreign_key_check`, and compares approved canonical rows to DB questions and options.
- DB row classifications are explicit:
  - `missing_approved_db_rows`: approved canonical rows absent from SQLite; blocking.
  - `retired_canonical_db_rows`: non-approved canonical rows that remain in SQLite; informational only.
  - `unknown_db_rows`: DB rows absent from all canonical question JSON files; blocking.
  - `mismatched_approved_rows`: approved canonical rows whose runtime DB projection differs from canonical JSON; blocking.
- Retired canonical rows are reported but are not auto-deleted, auto-deprecated, or treated as blockers solely because they remain in SQLite.
- `docs/audits/question_bank_db_audit_example.json` is an example report generated from a temporary repository-seeded SQLite database, not from production.

## Limitations

- This repository pass is structural validation plus reproducible SQLite parity tooling; it is not a substitute for original source-pack review or psychology SME certification.
- Repository `source_ref` values identify repository/source-pack references only; they are not external-source certification.
- Ambiguous semantic quality questions should be handled in the next separate content calibration PR with source material or SME input.

## QUESTION-BANK-QUALITY-CALIBRATION-001 update

The SQLite audit now distinguishes retained non-blocking rows from true blockers:

- `retired_canonical_db_rows` are non-approved canonical rows that still exist in SQLite and are informational only.
- `legacy_retired_db_rows` are SQLite rows absent from current canonical JSON with DB status `retired` and are informational only.
- `unknown_db_rows` are SQLite rows absent from canonical JSON whose DB status is not `retired` and remain blocking.
- `missing_approved_db_rows` and `mismatched_approved_rows` remain blocking for approved canonical content.

The deterministic quality report is generated with `python scripts/audit_question_quality.py --report-path docs/audits/question_bank_quality_report.json`. After calibration, the active approved bank is 304/575 unique-longest-correct (52.87%) with 0 high-severity length cues.
