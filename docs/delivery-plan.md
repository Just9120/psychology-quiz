# Delivery Plan

## Purpose
`docs/delivery-plan.md` фиксирует операционное состояние delivery: что уже завершено, что в текущем фокусе и что делать следующим шагом.

## Current product position
- **Module 1**: стабильный baseline.
- **Module 2**: активный scope в двух категориях:
  - `Основы экспериментальной психологии`
  - `Качественные методы исследования`
- Source of truth банка вопросов: JSON в репозитории.
- SQLite: runtime layer, наполняется через штатный seed workflow.
- Context Bundle Builder: **not adopted**.

## Completed checkpoints

| PR | Checkpoint | Status |
| :-- | :-- | :-- |
| #90 | CI validation + DB smoke tests | ✅ Done |
| #91 | Module 2 content growth (iter. 1) | ✅ Done |
| #92 | Module 2 content growth (iter. 2) | ✅ Done |
| #93 | Module 2 qualitative category growth | ✅ Done |
| #95 | Hidden owner-only `/stats` analytics | ✅ Done |
| #96 | Add `docs/ai-coding-workflow.md` | ✅ Done |
| #97 | Migrate canonical `docs/project-spec.md` + add `docs/ai-delivery-infrastructure-plan.md` | ✅ Done |
| This PR | Module 2 qualitative methods content growth (batch 2) | ✅ Done |

## Active focus
- Поддерживать docs-first workflow.
- Продолжать контролируемый рост Module 2 **в рамках уже активных категорий**.

## Next recommended item
1. Продолжить расширение Module 2 в текущих активных категориях (`Основы экспериментальной психологии`, `Качественные методы исследования`).
2. Если нужна новая категория Module 2 — сначала явно зафиксировать решение по следующей категории, затем открывать её отдельным PR.
