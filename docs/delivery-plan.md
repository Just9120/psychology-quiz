# Delivery Plan

## Current status dashboard
- ✅ Module 1 content QA — answer-position cleanup completed; flagged long-stem readability candidates shortened; repo-local source_ref hygiene reviewed; `m1-q3` kept stable as an intentional legacy ID.
- ✅ Module 2 content QA — experimental-psychology answer-position balance completed; qualitative-methods light polish completed with `m2_qual_023` / `m2_qual_041` kept as intentional scaffolding; repo-local source_ref hygiene reviewed; qualitative-methods provenance-limited tracking report added without changing question JSON.
- ✅ Module 3 first active scope — `Психологическое консультирование` contains 108 approved source-backed questions after the consulting content and polish sequence.
- 👉 Repository source-of-truth posture — docs now track the post-QA content baseline; future work should be narrow, source-backed, and should not change runtime behavior without a focused task.

## Current product/runtime posture
- `/quiz` remains the default classic Telegram chat entry point.
- Production classic chat UX: `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=true` remains the recommended implementation; the cleaner bottom reply keyboard UX is preferred for answers and `Далее`.
- Classic inline callback mode remains available only as legacy/fallback (`CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=false`).
- `/ui` / `🚀 В окне` remains opt-in Mini App runner; Mini App does not become the default UX.
- Long polling remains the default runtime mode; webhook is optional/config-gated infrastructure.
- Standalone Web UI/PWA remains out of scope.
- SQLite remains current runtime store; JSON files in `content/questions/**/*.json` remain the question-bank source of truth.
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
| **Total** | 8 active topics | **575** | Current approved JSON question-bank baseline. |

## Next recommended item
1. If original local/Drive source packs are available, continue source-backed Module 1/2 alignment before substantive content edits; repo-local source_ref hygiene and the Module 2 qualitative provenance-limited tracking report should not be overclaimed as full alignment or final source-backed certification.
2. Keep Module 2 experimental difficulty/onboarding review as optional future work only if new experimental-psychology content work is planned.
3. Keep future Module 3 expansion in separate focused source-backed batches; do not create a separate practice category unless explicitly decided.
4. Keep `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=true` enabled for classic production UX.
5. Run focused classic `/quiz` and Mini App opt-in smoke checks after restarts/deploys when runtime sync/deployment matters.

## Near backlog
- LEARN-CONTOURS-PHASE1-001 follow-up completed: `docs/topic_registry_schema_phase1.md` proposes a docs-only topic registry and schema validation approach; active runtime scope remains unchanged until a separate focused implementation task.
- LEARN-CONTOURS-PHASE1B-001 completed: added static `content/topics.json` for the 8 active question-backed topics and `scripts/validate_topics.py` for repository-local validation against `content/questions/**/*.json`; runtime scope remains unchanged and future glossary/literature contours require separate focused tasks.
- LEARN-CONTOURS-CI-001 completed: standard CI now runs `python scripts/validate_topics.py` alongside question-bank validation; topic registry scope remains static validation-only with no runtime, CD/deploy, database, glossary, or literature behavior changes.
- LEARN-CONTOURS-GLOSSARY-MVP-001 completed: added the first static qualitative-methods glossary MVP and `python scripts/validate_glossary.py`; scope remains content/validation-only with no Telegram UI, runtime loading, database, seed, CI/CD, deploy, or source-certification changes. Follow-up: expand only from supplied or available source excerpts and wire CI in a separate focused task if desired.
- Full Module 1/2 source-backed alignment against original local/Drive source packs if those materials are available; Module 2 qualitative methods now has a provenance-limited tracking report, but source_ref alignment risks, weakly supported items, and human-review-needed items remain.
- Module 2 experimental difficulty/onboarding review if future experimental-psychology content work is planned.
- Keep `m1-q3` stable as an intentional legacy ID unless a future explicit migration repeats downstream-reference checks and reviews downstream ID stability risks.
- Future Module 3 source-backed batches only after a focused content decision.

## Archived completed delivery groups
Historical completed delivery groups are archived in `docs/delivery-plan-archive.md`.

Do not use the archive as active implementation authority; use this file for current operational state and `docs/project-spec.md` for durable product scope.
