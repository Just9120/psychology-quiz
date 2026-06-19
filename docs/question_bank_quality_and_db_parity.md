# Question bank quality and SQLite parity audit

## Scope

- Canonical source: `content/topics.json` active topics with the `questions` contour and their referenced JSON files.
- Active question topics reviewed: 8.
- Active approved questions reviewed: 575.
- Complete-review confirmation: `docs/audits/question_bank_review_manifest.json` has one record for each active approved canonical question ID and no additional IDs.
- Content corrections applied in this pass: 0. No high-confidence repository-evidenced corrections were required by deterministic validation.

## Structural results

Deterministic validation now checks active approved questions for required content shape, option cardinality, answer index validity, canonical category mapping, source reference presence, and global duplicate IDs/stems.

- Duplicate question IDs: 0 found.
- Duplicate normalized question text: 0 found.
- Malformed option counts or blank options: 0 found.
- Invalid `correct_option_index` values: 0 found.
- Category mismatches against active topic titles: 0 found.
- Missing explanations: 0 found.
- Missing `source_ref` values: 0 found.

## Pedagogical review

The manifest uses non-blocking pedagogical flags only. These flags identify review signals; they are not hard validation failures and were not used to silently rewrite ambiguous psychology content.

- `ok`: 43.
- `corrected`: 0.
- `needs_source_or_SME_review`: 532.

Summary by topic:

| Topic | Approved questions | ok | corrected | needs source/SME review |
|---|---:|---:|---:|---:|
| `vvedenie_v_professiyu` | 57 | 2 | 0 | 55 |
| `obschaya_psihologiya` | 56 | 10 | 0 | 46 |
| `fiziologiya_cheloveka` | 55 | 5 | 0 | 50 |
| `fiziologiya_vnd` | 57 | 3 | 0 | 54 |
| `psihofiziologiya` | 71 | 4 | 0 | 67 |
| `osnovy_eksperimentalnoy_psihologii` | 118 | 9 | 0 | 109 |
| `kachestvennye_metody_issledovaniya` | 53 | 0 | 0 | 53 |
| `psychological_consulting` | 108 | 10 | 0 | 98 |

## SQLite parity model

- Canonical JSON is the source of truth: `content/topics.json` plus the active topic question files.
- SQLite is a seeded runtime projection of approved canonical JSON rows.
- `scripts/audit_question_bank.py` supports content-only validation and optional read-only SQLite auditing with `--db-path`.
- SQLite audit mode opens the database with a read-only URI, runs `PRAGMA integrity_check` and `PRAGMA foreign_key_check`, and compares approved canonical rows to DB questions and options.
- Stale production rows are reported as stale; the audit does not auto-delete, auto-deprecate, or mutate production data.
- `docs/audits/question_bank_db_audit_example.json` is an example report generated from a temporary repository-seeded SQLite database, not from production.

## Limitations

- This repository review is not a substitute for original source-pack review or psychology SME certification.
- Repository `source_ref` values identify repository/source-pack references only; they are not external-source certification.
- Ambiguous items remain explicitly queued in the manifest as `needs_source_or_SME_review` and were not silently rewritten.
