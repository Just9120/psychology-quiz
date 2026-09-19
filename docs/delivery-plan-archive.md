# Delivery Plan Archive

## Purpose

This file stores historical delivery checkpoints and completed PR groups that no longer need to live in the active delivery plan.

It is not active delivery authority. Current active delivery state remains in `docs/delivery-plan.md`, and archived items do not authorize new implementation by themselves.

## Archived completed PRs

### Operational diagnostics and classic reply keyboard baseline (#199–#204)

- #199: webhook/logging/security cleanup and safer operational diagnostics.
- #200: classic inline callback diagnostics for update ingress and callback latency investigation.
- #201: Mini App telemetry for answer/setup state, retries, and safe diagnostics.
- #202: Mini App production diagnostics/operational follow-up for stalled answer reports.
- #203: Mini App hedge mitigation for answer stalls, reducing hedged-case wait time.
- #204: classic reply keyboard mode for `/quiz`, moving answer/`Далее` controls to bottom Telegram reply keyboard text updates.

### UX polish loop (#207–#211)

- #207: main menu, `/start`, `/help`, `/ping`, and `/ui` UX cleanup.
- #208: Reading Mode UX polish.
- #209: classic chat quiz feedback and final screen polish.
- #210: Mini App P1 UX polish for setup/question/result flow.
- #211: Mini App P2 visual cleanup for product-facing setup/result screens.

Completed outcome:
- Classic `/quiz` with reply keyboard mode remained stable after the polish loop.
- UX-polish smoke passed with no current bugs reported after manual Telegram/Mini App checks.
- Mini App opt-in flow gained product-facing setup, question, and result screens after P1/P2 polish.


### Learning contours, Mini App glossary, contour entrypoint, and CD service-set fixes

- LEARN-CONTOURS-PHASE1-001 follow-up: docs-only topic registry/schema validation proposal.
- LEARN-CONTOURS-PHASE1B-001: static `content/topics.json` registry and `scripts/validate_topics.py`.
- LEARN-CONTOURS-CI-001: CI validation for topic registry.
- LEARN-CONTOURS-LITERATURE-MVP-001: first static literature reading-tracker scaffold and validator.
- LEARN-CONTOURS-LITERATURE-CI-001: CI validation for literature scaffold.
- LEARN-CONTOURS-GLOSSARY-MVP-001 and LEARN-CONTOURS-GLOSSARY-BATCH2-001: first static glossary content batches.
- LEARN-CONTOURS-GLOSSARY-CI-001: CI validation for glossary content.
- LEARN-CONTOURS-GLOSSARY-RUNTIME-MVP-001: read-only Telegram chat glossary MVP backed by static glossary JSON.
- LEARN-CONTOURS-GLOSSARY-QUIZ-MVP-001: Telegram glossary converted to quiz mode.
- LEARN-CONTOURS-GLOSSARY-V2-EXPERIMENTAL-PSYCHOLOGY-001: second glossary topic and chat quiz UX alignment.
- LEARN-CONTOURS-GLOSSARY-MINIAPP-MVP-001: Mini App glossary quiz contour.
- LEARN-CONTOURS-GLOSSARY-MINIAPP-OPEN-HOTFIX-001, SETUP-FALLBACK-HOTFIX-001, EXISTING-ENDPOINTS-HOTFIX-001, CONTEXT-HOTFIX-001, and START-HOTFIX-001: production hotfix chain that made Mini App glossary open/start reliably through existing Mini App endpoints while keeping source_refs internal.
- INFRA-CD-MINIAPP-API-DEPLOY-001: production CD/deploy rebuilds and recreates the runtime service set `psych_quiz_bot` + `psych_quiz_miniapp_api`.
- MINIAPP-CONTOUR-ENTRYPOINT-RESTORE-001: `/ui` and `🚀 В окне` restored as setup/contour chooser entrypoints even when a normal quiz runner is active.

## Завершённый dashboard на 2026-07-03

Перенесено 2026-09-19 из delivery-plan.md на revision `ddc661172b50f549a8e1ef4ef8ff5ab54152ae64`. Это исторические delivery claims со старым scope; они не присваивают READY новым AC. Незаполненные обязательства сохранены в текущем [плане](delivery-plan.md).

- ✅ `LITERATURE-MINIAPP-UI-008` — Mini App Literature contour added with authenticated topics/items/state reads and progress status writes; no `/next`, recommendation logic, reminders, reading plans, private notes, literature JSON, question bank, glossary data, DB/schema, Telegram chat UX, Docker, deploy, or CI/CD changes.
- ✅ `LITERATURE-API-PROGRESS-WRITE-007` — Authenticated Mini App Literature progress write endpoint added for `user_literature_progress`; no recommendation logic, Mini App UI, Telegram bot UX, reminders, reading plans, private notes, literature JSON, questions, glossary, Docker, deploy, or CI/CD changes.
- ✅ `LITERATURE-API-READONLY-006` — Read-only Mini App Literature API added for topics/items/existing user state; no progress mutation, recommendation logic, Mini App UI, Telegram bot UX, reminders, literature JSON, questions, glossary, Docker, deploy, or CI/CD changes.
- ✅ `LITERATURE-RUNTIME-STATE-MODEL-005` — SQLite-backed user literature progress state model/migration added for future Reading Tracker; no API, UI, bot UX, recommendation logic, reminders, literature JSON, questions, glossary, deploy, Docker, or CI/CD changes.
- ✅ `LITERATURE-RUNTIME-RFC-004` — Documentation-only runtime contour RFC added for future Literature / Reading Tracker product flow, user state, API candidates, Mini App UX, next-reading logic, privacy, and staged rollout; no runtime, UI/API, DB, deploy, questions, glossary, or literature JSON content changes.
- ✅ `LITERATURE-MODULE1-METADATA-NORMALIZATION-003` — All seeded Module 1 literature entries now include pedagogical ordering and learner-facing metadata; no runtime, user-progress, UI/API, DB, deploy, questions, glossary, Docker, or migration changes.
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
