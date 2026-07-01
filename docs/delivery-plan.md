# Delivery Plan

## Current status dashboard
- ✅ `LITERATURE-MODULE1-SOURCE-SEED-002` — Remaining currently available Module 1 literature source lists seeded from readable rendered PDFs; all entries remain static `review` metadata, with no runtime, user-progress, UI/API, DB, deploy, Docker, or migration changes.
- ✅ `LITERATURE-SOURCE-INVENTORY-001` — Literature scaffold/source inventory started with one `Общая психология` static metadata topic seeded; remaining Drive source lists are documented as extraction-pending, with no runtime, user-progress, UI/API, DB, deploy, or migration changes.
- ✅ `REFACTOR-RFC-MINIAPP-BOT-001` — Mini App / bot refactor RFC added; proposal defines incremental no-UX-change seams and recommends Mini App context extraction first.
- ✅ `REFACTOR-MINIAPP-CONTEXT-EXTRACT-001` — Mini App context encoding, URL construction, setup entrypoint, compact runner payload, and URL-length fallback helpers extracted from `app/main.py` into `app/miniapp_context.py` without UX/runtime/API/deploy/DB/content changes.
- ✅ `REFACTOR-MINIAPP-ENTRYPOINT-HANDLERS-EXTRACT-001` — `/ui` and `🚀 В окне` Mini App launch orchestration extracted from `app/main.py` into `app/miniapp_entrypoint_handlers.py` without UX/runtime/API/deploy/DB/content changes.
- ✅ `REFACTOR-MINIAPP-GLOSSARY-HANDLERS-EXTRACT-001` — Telegram chat `/glossary` / `📚 Глоссарий` orchestration extracted from `app/main.py` into `app/glossary_handlers.py` without UX/runtime/API/deploy/DB/content changes.
- ✅ `REFACTOR-MINIAPP-CLASSIC-QUIZ-HANDLERS-EXTRACT-001` — Classic Telegram chat `/quiz` orchestration extracted from `app/main.py` into `app/classic_quiz_handlers.py` without UX/runtime/API/deploy/DB/content changes.
- ✅ `REFACTOR-MINIAPP-API-SEAMS-CLARIFY-001` — FastAPI Mini App transport wrapper mechanics clarified in `app/miniapp_fastapi.py` without endpoint contract, UX/runtime/API payload/deploy/DB/content changes.
- ✅ Module 1 content QA — answer-position cleanup completed; flagged long-stem readability candidates shortened; repo-local source_ref hygiene reviewed; `m1-q3` kept stable as an intentional legacy ID.
- ✅ Module 2 content QA — experimental-psychology answer-position balance completed; qualitative-methods light polish completed with `m2_qual_023` / `m2_qual_041` kept as intentional scaffolding; repo-local source_ref hygiene reviewed; qualitative-methods provenance-limited tracking report added without changing question JSON.
- ✅ Module 3 first active scope — `Психологическое консультирование` contains 108 approved source-backed questions after the consulting content and polish sequence.
- ✅ `GLOSSARY-CONTENT-AUDIT-001` — Documentation-only audit of active glossary content delivered; no glossary data, runtime, UI/API, deploy, DB, or test behavior changed.
- ✅ `GLOSSARY-COVERAGE-EXPANSION-ALL-TOPICS-001` — One implementation PR expanded glossary coverage from 2 to all 8 currently active main-quiz categories; total glossary entries now: Введение в профессию 12, Общая психология 12, Физиология человека 12, Физиология ВНД 12, Психофизиология 12, Качественные методы исследования 14, Основы экспериментальной психологии 10, Психологическое консультирование 12. Source-backed terminology certification against original external materials and any future distractor-logic work remain deferred.
- ✅ `GLOSSARY-GLOBAL-QUALITY-ALIGNMENT-001` — One global repository-evidence quality baseline now covers the complete 96-entry glossary system across all 8 active topics; conservative glossary JSON corrections and deterministic registry/source/confusable validation were added without question-bank, runtime, API, UI, DB, deploy, Docker, or external source-certification claims. Future glossary work should be source-pack / SME alignment only unless a concrete runtime issue is found.
- ✅ `MINIAPP-SETUP-URL-DECUPLING-001` — Mini App setup launch URLs now carry compact bootstrap data and hydrate categories/glossary topics through the existing authenticated `/miniapp/setup-options` API, protecting `/ui` from category/glossary growth without changing user-visible quiz semantics.
- ✅ `GLOSSARY-DISTRACTOR-QUALITY-ENGINE-001` — Glossary distractors are now selected from curated same-topic `confusable_with` relationships first, then reciprocal relations, then same-topic fallback; future source/SME review remains a separate optional quality layer.
- ✅ `GLOSSARY-ALL-TOPICS-QUALITY-BATCH-001` — All 8 active glossary topic files were reviewed for one source-backed quiz-quality batch; 13 existing entries were improved and 3 qualitative-methods entries were added using repository source materials/supplied snippet evidence plus preserved approved question refs. Ordinary question-bank files and runtime behavior were unchanged.
- ✅ `QUESTION-BANK-GLOBAL-QUALITY-AND-DB-PARITY-001` — All 575 active approved canonical questions across 8 active topics are structurally validated and auditable against SQLite with read-only JSON → DB parity checks; the oversized full-bank review manifest was replaced with a compact actionable quality queue.
- ✅ `QUESTION-BANK-QUALITY-CALIBRATION-001` — Active question-bank calibration kept repository-grounded quality ahead of metric compliance, removed artificial length-padding edits, resolved the rapport near-duplicate, added deterministic quality reporting, separated legacy retired SQLite rows as informational, and documented explicit unfinished-session closure for safe content rollout.
- 👉 Repository source-of-truth posture — docs now track the post-QA content baseline and glossary audit posture; future work should be narrow, source-backed, and should not change runtime behavior without a focused task.

## Current product/runtime posture
- `/quiz` remains the default classic Telegram chat entry point.
- Production classic chat UX: `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=true` remains the recommended implementation; the cleaner bottom reply keyboard UX is preferred for answers and `Далее`.
- Classic inline callback mode remains available only as legacy/fallback (`CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=false`).
- `/ui` / `🚀 В окне` remains opt-in Mini App runner; Mini App does not become the default UX.
- Mini App setup entrypoint now offers two contours: `Тесты по темам` and `Глоссарий`; chat `📚 Глоссарий` remains the separate Telegram chat glossary quiz.
- Mini App setup data is hydrated through authenticated `/miniapp/setup-options` instead of being embedded in launch URLs, so all eight glossary topics and active categories remain available while `/ui` stays within the configured URL-size limit.
- Production app runtime service set is `psych_quiz_bot` + `psych_quiz_miniapp_api`; static Mini App frontend hosting remains separate/operator-managed.
- Long polling remains the default runtime mode; webhook is optional/config-gated infrastructure.
- Standalone Web UI/PWA remains out of scope.
- SQLite remains current runtime store; `content/topics.json` plus active question files remain the canonical question-bank source of truth, and SQLite parity is auditable with a read-only script.
- Docs-only changes do not require runtime sync.

## Current content baseline

| Module | Active topic/category | Approved questions | Current content state |
|---|---|---:|---|
| Module 1 | `Физиология ВНД` | 57 | Stable baseline; answer positions balanced; flagged long stems shortened; repo-local source_ref hygiene reviewed. |
| Module 1 | `Общая психология` | 56 | Stable baseline; answer positions balanced; flagged long stem shortened; repo-local source_ref hygiene reviewed. |
| Module 1 | `Психофизиология` | 71 | Stable baseline; answer positions balanced; repo-local source_ref hygiene reviewed. |
| Module 1 | `Физиология человека` | 55 | Stable baseline; answer positions balanced; repo-local source_ref hygiene reviewed. |
| Module 1 | `Введение в профессию` | 57 | Stable baseline; answer positions balanced; repo-local source_ref hygiene reviewed; `m1-q3` kept stable as legacy ID. |
| Module 2 | `Основы экспериментальной психологии` | 118 | Active limited scope; answer positions balanced; repo-local source_ref hygiene reviewed; difficulty/onboarding review remains optional future work. |
| Module 2 | `Качественные методы исследования` | 53 | Active limited scope; answer positions balanced; `m2_qual_023` / `m2_qual_041` intentionally retained as scaffolding; repo-local source_ref hygiene reviewed. |
| Module 3 | `Психологическое консультирование` | 108 | First active Module 3 scope; practical/case/checklist questions embedded in the topic category. |
| **Total** | 8 active topics | **575** | Current approved JSON question-bank baseline; structurally validated, covered by JSON → SQLite parity and deterministic quality audit tooling, with remaining high-severity length-cue follow-up retained in the compact actionable queue rather than hidden by artificial padding. |

## Next recommended item
1. For question-bank content replacement while unfinished sessions exist, follow `docs/question_bank_content_rollout.md`; unfinished-session closure is explicit operator action only and never automatic.
2. Run future glossary source-pack / SME alignment only if original local/Drive source packs or SME review are available; the current baseline is repository-evidence aligned but not externally source-certified.
3. Do not schedule another small glossary polish PR by default; only open glossary content work for source/SME alignment or a concrete runtime/data-integrity issue.
4. Treat future glossary source/SME review as an optional quality layer for semantic correctness; the runtime distractor engine already prefers curated same-topic relationships before fallback.
5. Consider the optional no-build static frontend split from PR 6 in `docs/proposals/refactor-plan-miniapp-bot.md` only if review risk justifies it; otherwise prefer source-backed content alignment work.
6. Keep Module 2 experimental difficulty/onboarding review as optional future work only if new experimental-psychology content work is planned.
7. Keep future Module 3 expansion in separate focused source-backed batches; do not create a separate practice category unless explicitly decided.
8. Keep `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=true` enabled for classic production UX.
9. Run focused classic `/quiz` and Mini App opt-in smoke checks after restarts/deploys when runtime sync/deployment matters.

## Near backlog
- Glossary content follow-up: source-pack / SME alignment only when original materials or expert review are available; otherwise limit future glossary work to concrete runtime/data-integrity issues.
- Full Module 1/2 source-backed alignment against original local/Drive source packs if those materials are available; Module 2 qualitative methods now has a provenance-limited tracking report, but source_ref alignment risks, weakly supported items, and human-review-needed items remain.
- Module 2 experimental difficulty/onboarding review if future experimental-psychology content work is planned.
- Keep `m1-q3` stable as an intentional legacy ID unless a future explicit migration repeats downstream-reference checks and reviews downstream ID stability risks.
- Future Module 3 source-backed batches only after a focused content decision.

## Archived completed delivery groups
Historical completed delivery groups are archived in `docs/delivery-plan-archive.md`.

Do not use the archive as active implementation authority; use this file for current operational state and `docs/project-spec.md` for durable product scope.
