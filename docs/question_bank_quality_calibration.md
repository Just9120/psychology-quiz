# QUESTION-BANK-QUALITY-CALIBRATION-001

This repository-grounded calibration pass adjusted active canonical JSON question options and audit tooling. It is not external-source certification or SME certification.

## Metrics

Baseline from the prior deterministic audit: 487/575 approved questions had the keyed answer as the uniquely longest option (84.70%). The final audit reports 487/575 (84.70%), after semantic cleanup removed artificial length-padding edits. High-severity length cues remain 21 and are tracked in the review queue because quality was prioritized over metric compliance.

The generated report at `docs/audits/question_bank_quality_report.json` contains the final global and per-topic counts, rates, duplicate checks, negative/exception wording counts, and option-length distribution.

## Calibration scope

Changed questions are listed compactly in `docs/audits/question_bank_calibration_changelog.json`; the changelog records 1 changed active question ID. The compact review queue retains 21 unresolved high-severity length-cue items after removing artificial metric-padding edits.

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
