# Delivery Plan

## Current status dashboard
- ✅ Module 1 content QA — answer-position cleanup completed across the stable baseline topics; remaining Module 1 follow-ups are readability/source-ref/legacy-ID review only.
- ✅ Module 2 content QA — experimental-psychology answer-position balance completed; qualitative-methods light polish completed with `m2_qual_023` / `m2_qual_041` kept as intentional scaffolding.
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
| Module 1 | `Физиология ВНД` | 57 | Stable baseline; answer positions balanced; long-stem/source-ref review remains separate. |
| Module 1 | `Общая психология` | 56 | Stable baseline; answer positions balanced; one long-stem candidate remains separate. |
| Module 1 | `Психофизиология` | 71 | Stable baseline; answer positions balanced; source-ref review remains separate. |
| Module 1 | `Физиология человека` | 55 | Stable baseline; answer positions balanced; source-ref review remains separate. |
| Module 1 | `Введение в профессию` | 57 | Stable baseline; answer positions balanced; legacy `m1-q3` decision/source-ref review remains separate. |
| Module 2 | `Основы экспериментальной психологии` | 118 | Active limited scope; answer positions balanced; source-alignment/difficulty review remains separate. |
| Module 2 | `Качественные методы исследования` | 53 | Active limited scope; answer positions balanced; `m2_qual_023` / `m2_qual_041` intentionally retained as scaffolding. |
| Module 3 | `Психологическое консультирование` | 108 | First active Module 3 scope; practical/case/checklist questions embedded in the topic category. |
| **Total** | 8 active topics | **575** | Current approved JSON question-bank baseline. |

## Next recommended item
1. Run a focused source-alignment/readability review for Module 1/2 before substantive content edits, especially the Module 1 long-stem candidates and the Module 2 experimental source/difficulty notes.
2. Decide whether the legacy `m1-q3` ID should remain stable or be normalized only after downstream reference checks.
3. Keep future Module 3 expansion in separate focused source-backed batches; do not create a separate practice category unless explicitly decided.
4. Keep `CLASSIC_QUIZ_REPLY_KEYBOARD_MODE=true` enabled for classic production UX.
5. Run focused classic `/quiz` and Mini App opt-in smoke checks after restarts/deploys when runtime sync/deployment matters.

## Near backlog
- Module 1 long-stem readability polish candidates from `docs/content_audit_all_topics.md`.
- Module 1/2 source-ref/source-alignment review against local source packs.
- Module 2 experimental difficulty/onboarding review if future experimental-psychology content work is planned.
- Legacy `m1-q3` ID hygiene decision after downstream-reference checks.
- Future Module 3 source-backed batches only after a focused content decision.

## Archived completed delivery groups
Historical completed delivery groups are archived in `docs/delivery-plan-archive.md`.

Do not use the archive as active implementation authority; use this file for current operational state and `docs/project-spec.md` for durable product scope.
