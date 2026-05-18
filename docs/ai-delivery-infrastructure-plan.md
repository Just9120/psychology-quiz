# AI Delivery Infrastructure Plan

## Purpose
Этот документ отслеживает внедрение AI delivery-инфраструктуры в репозитории:
- docs-first adoption процесса AI Coding Workflow;
- миграцию проектного ТЗ в канонический `docs/project-spec.md`;
- последующее создание продуктового `docs/delivery-plan.md`;
- опциональное дальнейшее решение о внедрении Context Bundle Builder (если будет явно принято).

Этот документ **не** заменяет будущий продуктовый `docs/delivery-plan.md`.

## Progress dashboard
- ✅ Done: `docs/ai-coding-workflow.md` добавлен (PR #96)
- 🔄 Current: миграция `docs/TZ_psychology_quiz.md` → `docs/project-spec.md`
- 🗓 Planned: создать продуктовый `docs/delivery-plan.md`
- 🗓 Planned/optional: принять решение о внедрении Context Bundle Builder
- ⛔ Not adopted: Context Bundle Builder не является частью текущего workflow репозитория

## Current position
- Текущий режим: **AI Coding Workflow only**
- Context Bundle Builder: **not adopted**
- Текущий фокус: миграция project-spec и cleanup source-of-truth
- Следующий рекомендованный шаг после этого PR: создать `docs/delivery-plan.md` для продуктового/content/runtime планирования

## Track status
- **Track A — AI Coding Workflow:** active
- **Track B — Context Bundle Builder:** not adopted
- **Track C — Integration:** not applicable until Builder adoption

## Requirement coverage matrix
| Requirement | Status | Evidence |
| :-- | :-- | :-- |
| `docs/ai-coding-workflow.md` exists | Done | PR #96 |
| `docs/project-spec.md` canonical spec | In this PR | Added in this PR |
| Old TZ no longer active source of truth | In this PR | `docs/TZ_psychology_quiz.md` converted to obsolete pointer |
| `docs/delivery-plan.md` product backlog | Planned next | Next checkpoint after this PR |
| README docs navigation | In this PR | README updated with docs links |
| GitHub Issues optional, not main backlog | Done | Defined in `docs/ai-coding-workflow.md` |
| Context Bundle Builder adoption | Not adopted / out of current scope | Explicitly not adopted in this file |
| Generated bundles not committed | Not applicable until Builder adoption | N/A in current mode |

## Delivery checkpoints / backlog
- ✅ **AI-D1-01** — Add AI Coding Workflow spec (done in PR #96)
- ✅ **AI-D1-02** — Migrate project spec to `docs/project-spec.md` (current PR)
- 🗓 **AI-D1-03** — Add product delivery plan (`docs/delivery-plan.md`)
- ✅ **AI-D1-04** — Add README documentation navigation (current PR)
- 🗓 **AI-D1-05** — Decide on Context Bundle Builder adoption

## Validation and evidence
- Этот PR — **docs-only** (без изменений runtime/app/content/db-schema/deploy behavior).
- Валидация: ручной review измененных markdown-файлов.
- При наличии дешевых проверок допустимы стандартные проверки репозитория, но отдельная runtime-валидация не требуется, так как runtime-файлы не изменялись.
