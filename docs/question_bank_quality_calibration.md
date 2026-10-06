# QUESTION-BANK-QUALITY-CALIBRATION-001

> Контекст документа: прежний review/RFC с ограниченным scope и Evidence на описанную в нём версию. Согласованные требования — [spec](project-spec.md), текущие AC/findings и выбор работы — [план](delivery-plan.md). Старые рекомендации и слова «current/ready» не подтверждают новые AC и не разрешают реализацию.

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

Current updates follow [content rollout](question_bank_content_rollout.md) and the [deployment procedure](miniapp-deployment-qa.md). Captured attempt snapshots preserve the presented edition; stopping unfinished sessions is not a normal content-update step. Native backup/isolated restore, user-state preservation and serving parity apply to the validated candidate. The earlier closure recommendation belonged to the pre-snapshot implementation and does not authorize abandoning current attempts.
