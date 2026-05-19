# Delivery Plan

## Purpose
`docs/delivery-plan.md` фиксирует **операционное состояние доставки продукта**: текущую позицию, активный фокус, ближайший рекомендуемый шаг и компактный backlog для ежедневных решений по delivery.

Этот документ:
- не дублирует полный `docs/project-spec.md`;
- не заменяет `docs/ai-delivery-infrastructure-plan.md`;
- используется как рабочий dashboard по продукту/контенту/runtime/документации.

## Source-of-truth model
- `docs/project-spec.md` — **канонический product/project spec** (scope, требования, ограничения).
- `docs/delivery-plan.md` — **операционное delivery-state** (где мы сейчас, что дальше, какой backlog активен).
- `docs/ai-coding-workflow.md` — **workflow-правила** работы ChatGPT/Codex/PR/docs.
- `docs/ai-delivery-infrastructure-plan.md` — трекает только **adoption AI workflow/infrastructure**, не заменяет product delivery plan.

Данные и контент:
- JSON-файлы в репозитории — source of truth банка вопросов.
- SQLite — только runtime layer.
- Ручное редактирование SQLite — нештатный путь и не является нормальным workflow обновления контента.

## Current product position
- Module 1 — стабильный baseline.
- Module 2 — активен в ограниченном scope.
- Активные категории Module 2 на текущий момент:
  - `Основы экспериментальной психологии`
  - `Качественные методы исследования`
- `/stats` — скрытая owner-only агрегированная аналитика.
- Context Bundle Builder — **not adopted** и не требуется для текущего workflow.

## Completed checkpoints (recent)

| PR | Checkpoint | Status |
| :-- | :-- | :-- |
| #90 | CI validation + DB smoke tests | Done |
| #91 | Module 2 content growth | Done |
| #92 | Module 2 content growth | Done |
| #93 | Module 2 qualitative category growth | Done |
| #95 | Hidden owner-only `/stats` analytics | Done |
| #96 | `docs/ai-coding-workflow.md` added | Done |
| #97 | `docs/project-spec.md` migration + `docs/ai-delivery-infrastructure-plan.md` | Done |

## Active focus
- Поддерживать docs-first AI-assisted delivery в текущем рабочем scope.
- Продолжать контентный рост Module 2 малыми целевыми PR в уже открытых активных категориях.
- Держать документацию синхронизированной с фактическим состоянием продукта.

## Next recommended item
После этого PR: продолжить рост контента Module 2 **внутри уже активных категорий**,
или сначала явно принять отдельное решение о следующей категории Module 2 и только затем открывать её.

## Product/content backlog (compact)
- Expand `Основы экспериментальной психологии`.
- Expand `Качественные методы исследования`.
- Отдельно зафиксировать решение по следующей категории Module 2 до её открытия.

## Runtime / UX / analytics backlog (guardrails)
- Сохранить owner-only агрегированный характер `/stats`.
- Сохранить текущий quiz UX по режимам и меню, если UX-изменение не согласовано отдельно.

## Docs / workflow maintenance backlog
- Обновлять docs при изменениях продуктового состояния, категорий или runtime-поведения.
- Поддерживать согласованность между `README.md`, `docs/project-spec.md`, `docs/delivery-plan.md` и `docs/ai-coding-workflow.md`.
- Context Bundle Builder остаётся не внедрённым до отдельного явного решения.

## Deferred / out-of-scope items
- Внедрение Context Bundle Builder (deferred; not adopted).
- Расширение Module 2 на новые категории без отдельного решения.
- Любые изменения, делающие `/stats` публичной командой.
- Изменения текущего quiz UX без отдельного согласованного scope.

## Update rules
- Обновлять `docs/delivery-plan.md`, когда PR меняет delivery status, current focus, next item или backlog state.
- Обновлять `docs/project-spec.md` только при изменении product scope, требований, business rules или ограничений.
- Обновлять `docs/ai-delivery-infrastructure-plan.md` только при изменениях AI workflow adoption, решения по Context Bundle Builder или workflow infrastructure.
