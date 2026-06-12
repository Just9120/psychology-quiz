# AI Delivery Infrastructure Plan

## Purpose
Этот документ отслеживает **только** внедрение AI delivery-практик в репозитории:
- docs-first workflow;
- использование `docs/ai-coding-workflow.md` как правил AI-assisted разработки;
- lightweight first-read routing для coding agents;
- фиксацию статуса adoption (что внедрено, что не внедрено).

Документ **не заменяет** `docs/delivery-plan.md`, не является продуктовым backlog-документом и не авторизует runtime/product work сам по себе.

## Current adoption status
- ✅ `docs/ai-coding-workflow.md` — adopted and used as AI-assisted development / PR / docs workflow guidance.
- ✅ `AGENTS.md` — adopted as the lightweight first-read coding-agent guide.
- ✅ `docs/ci-cd-rules.md` — adopted as the CI/CD, deploy, secrets, rollback, and stateful-service boundary document.
- ✅ `docs/project-spec.md` migration — completed; product/project source of truth is in use.
- ✅ `docs/delivery-plan.md` — operational delivery-state document is in use.
- ✅ `docs/delivery-plan-archive.md` — created for historical completed delivery groups; not active delivery authority.
- ✅ README navigation — updated to point agents/humans to the current source-of-truth and supporting workflow documents.
- ✅ AGENTS command shortcuts — filled from the current CI validation commands.
- ✅ `docs/TZ_psychology_quiz.md` — removed after the project-spec migration.
- ⛔ Context Bundle Builder — **not adopted**.

## Track status
- **Track A — AI Coding Workflow:** adopted for current lightweight workflow.
- **Track B — Context Bundle Builder:** not adopted.
- **Track C — Integration with Builder artifacts:** not applicable until Builder adoption.

## Notes
- Этот файл ведёт только AI workflow adoption-трек.
- Продуктовые/content checkpoint-ы фиксируются в `docs/delivery-plan.md`.
- Канонический продуктовый scope хранится в `docs/project-spec.md`.
- CI/CD/deploy/secrets/stateful-service boundaries фиксируются в `docs/ci-cd-rules.md`.
