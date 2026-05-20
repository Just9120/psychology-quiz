# Delivery Plan

## Purpose
`docs/delivery-plan.md` — это операционный delivery-dashboard проекта: текущая продуктовая позиция, активный фокус, completed checkpoints и приоритизированный backlog.

Документ **не дублирует** полный `docs/project-spec.md`, а фиксирует статус выполнения и следующий практический шаг.

## Source-of-truth model
- `docs/project-spec.md` — **каноническая** продуктовая/проектная спецификация (scope, требования, ограничения).
- `docs/delivery-plan.md` — **операционное состояние delivery** (что сделано, что в фокусе, что дальше).
- `docs/ai-coding-workflow.md` — правила workflow для ChatGPT / Codex / PR / docs.
- `docs/ai-delivery-infrastructure-plan.md` — трекинг внедрения AI workflow/infrastructure, **не** замена продуктового delivery plan.

Данные и контент:
- JSON-файлы в репозитории — source of truth для банка вопросов.
- SQLite — runtime layer хранения/выдачи данных, а не source of truth.
- Ручное редактирование SQLite — нештатный путь и не нормальный контентный workflow.

## Current product position
- **Module 1**: стабильный baseline.
- **Module 2**: активный ограниченный рабочий scope с двумя активными категориями:
  - `Основы экспериментальной психологии`
  - `Качественные методы исследования`
- `/stats` — скрытая owner-only агрегированная аналитика.
- Context Bundle Builder — **not adopted** и не требуется для текущего workflow.

## Done / completed checkpoints

| PR | Checkpoint | Status |
| :-- | :-- | :-- |
| #90 | CI validation + DB smoke tests | ✅ Done |
| #91 | Module 2 content growth (iter. 1) | ✅ Done |
| #92 | Module 2 content growth (iter. 2) | ✅ Done |
| #93 | Module 2 qualitative category growth | ✅ Done |
| #95 | Hidden owner-only `/stats` analytics | ✅ Done |
| #96 | Add `docs/ai-coding-workflow.md` | ✅ Done |
| #97 | Migrate canonical `docs/project-spec.md` + add `docs/ai-delivery-infrastructure-plan.md` | ✅ Done |
| #100 | Module 2 qualitative methods content growth (batch 2) | ✅ Done |
| #101 | Module 2 experimental psychology content growth (next batch) | ✅ Done |
| #102 | Module 1 baseline content QA cleanup | ✅ Done |
| #103 | Module 1 general psychology and intro content QA cleanup | ✅ Done |
| #104 | Module 2 existing categories content QA revision | ✅ Done |
| #106 | Module 2 qualitative methods content growth (batch 3) | ✅ Done |
| #107 | Module 2 qualitative batch 3 content QA | ✅ Done |
| #108 | Module 2 experimental batch content QA | ✅ Done |
| #109 | Module 2 coverage audit | ✅ Done |
| #110 | Module 2 qualitative applied case questions | ✅ Done |
| #111 | Module 2 qualitative applied-case batch QA | ✅ Done |
| #112 | Module 2 experimental design interpretation questions | ✅ Done |
| #115 | Module 2 experimental design interpretation batch QA | ✅ Done |
| #116 | Define experimental Telegram Mini App mode | ✅ Done |
| This PR | Implement /ui command and Mini App setup-screen MVP | ✅ Done |

## Active focus
- Поддерживать docs-first AI-assisted workflow.
- Продолжать контролируемый рост Module 2 **в рамках уже активных категорий**.
- Синхронизировать документы при изменении продуктового состояния.

## Next recommended item
После технического MVP Mini App setup-screen:
1. Провести manual QA и deployment-валидацию статического Mini App hosting URL (`MINI_APP_URL`) в Telegram.
2. Classic Telegram chat UX сохранять дефолтным до отдельного явного product-решения по смене default UX.
3. Задачу `QA Module 2 duplicate and source_ref balance` держать в backlog как отдельный content QA шаг без удаления из delivery-фокуса.

## Product/content backlog
- [ ] Расширить `Основы экспериментальной психологии` новыми `approved` вопросами с корректным `source_ref`.
- [ ] Расширить `Качественные методы исследования` новыми `approved` вопросами с корректным `source_ref`.
- [ ] Следующую категорию Module 2 определять отдельным решением перед её открытием.

## Runtime / UX / analytics backlog
- [x] Implement `/ui` command and Mini App setup-screen MVP.
- [ ] Keep classic Telegram chat UX as default until a separate decision is made.
- [ ] Сохранять owner-only и агрегированный характер `/stats`.

## Docs / workflow maintenance backlog
- [ ] Держать `README.md`, `docs/project-spec.md`, `docs/delivery-plan.md` и `docs/ai-coding-workflow.md` синхронизированными при изменениях продукта/категорий/runtime-поведения.
- [ ] Продолжать использовать `docs/ai-delivery-infrastructure-plan.md` только для AI workflow adoption-трека.
- [ ] Поддерживать явную фиксацию того, что Context Bundle Builder не adopted, пока отдельное решение не принято.

## Deferred / out-of-scope items
- Внедрение Context Bundle Builder (deferred, not adopted).
- Попытки сделать `docs/delivery-plan.md` заменой полного product spec (out-of-scope).
- Возврат или пересоздание `docs/TZ_psychology_quiz.md` как active source of truth запрещены; файл удалён после миграции в `docs/project-spec.md`.

## Update rules
1. Обновлять этот документ в каждом PR, который меняет delivery-state (done/in-progress/deferred/next).
2. Не переносить в этот файл полный нормативный scope из `docs/project-spec.md`; хранить здесь только operational state.
3. Если меняется product scope, сначала обновлять `docs/project-spec.md`, затем синхронизировать `docs/delivery-plan.md`.
4. Для контентных изменений source of truth остаются JSON в репозитории; SQLite меняется только через штатный seed workflow.
5. Поддерживать согласованность с `docs/ai-coding-workflow.md`; AI infrastructure-трек вести отдельно в `docs/ai-delivery-infrastructure-plan.md`.
