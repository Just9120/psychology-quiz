# QUESTION-BANK-QUALITY-CALIBRATION-001

This repository-grounded calibration pass adjusted active canonical JSON question options and audit tooling. It is not external-source certification or SME certification.

## Metrics

Baseline from the prior deterministic audit: 487/575 approved questions had the keyed answer as the uniquely longest option (84.70%). The final audit reports 304/575 (52.87%), meeting the <=60% target. High-severity length cues were reduced from 21 to 0.

The generated report at `docs/audits/question_bank_quality_report.json` contains the final global and per-topic counts, rates, duplicate checks, negative/exception wording counts, and option-length distribution.

## Calibration scope

Changed questions are listed compactly in `docs/audits/question_bank_calibration_changelog.json`; the changelog records 184 changed active question IDs. The compact review queue now has 0 unresolved items after resolving the queued high-severity length-cue cases and confirmed rapport near-duplicate.

The rapport pair was resolved by keeping `m3_psychological_consulting_009` as the definition-level item and reworking `m3_psychological_consulting_031` into recognition of rapport forming during the consultation.

## SQLite audit classification

The parity audit now separates blocking and informational rows:

- `missing_approved_db_rows`: approved canonical rows absent from SQLite; blocking.
- `retired_canonical_db_rows`: non-approved canonical rows present in SQLite; informational.
- `legacy_retired_db_rows`: SQLite rows absent from canonical JSON with DB status `retired`; informational.
- `unknown_db_rows`: SQLite rows absent from canonical JSON with non-retired DB status; blocking.
- `mismatched_approved_rows`: approved canonical rows whose SQLite projection differs; blocking.

## Safe rollout

Use `docs/question_bank_content_rollout.md` before replacing content in a database with unfinished sessions. The key safety point is to snapshot the database, run read-only audits, dry-run the in-progress session closure, explicitly apply it only if acceptable, reseed content, rerun parity, and smoke-test a new quiz. Unfinished-session closure is never automatic.
