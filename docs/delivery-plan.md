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
| #117 | Implement /ui command and Mini App setup-screen MVP | ✅ Done |
| #118 | Add Mini App deployment and manual QA checklist | ✅ Done |
| #119 | Add Cloudflare Workers Static Assets config for Mini App | ✅ Done |
| #120 | Sync environment example with Mini App and admin settings | ✅ Done |
| #122 | Add safe deploy-time .env missing-key sync | ✅ Done |
| #123 | Compact Mini App setup context URL encoding | ✅ Done |
| #124 | Record Mini App deployment/manual QA smoke result | ✅ Done |
| #125 | Design full Mini App quiz runner architecture | ✅ Done |
| #126 | Implement Mini App runner session/transport contract baseline | ✅ Done |
| #127 | Render authoritative current question in Mini App | ✅ Done |
| #128 | Implement Mini App answer submission and next-question transition | ✅ Done |
| #129 | Add Mini App progress and result screen | ✅ Done |
| #130 | Fix `/ui` launch-context URL regression with compact fallback | ✅ Done |
| This PR | Keep Mini App setup completion inside Mini App (no automatic first chat question) | ✅ Done |
| #135 | Harden Mini App reopen/recovery handling and polish opt-in `/ui` runner flow | ✅ Done |
| #132 | Reduce /ui launch context size with adaptive setup/runner/completed profiles | ✅ Done |

## Active focus
- Поддерживать docs-first AI-assisted workflow.
- Продолжать контролируемый рост Module 2 **в рамках уже активных категорий**.
- Синхронизировать документы при изменении продуктового состояния.

## Next recommended item
1. Run production manual QA for the opt-in Mini App runner and document findings before considering default UX changes.

## Product/content backlog
- [ ] Расширить `Основы экспериментальной психологии` новыми `approved` вопросами с корректным `source_ref`.
- [ ] Расширить `Качественные методы исследования` новыми `approved` вопросами с корректным `source_ref`.
- [ ] Следующую категорию Module 2 определять отдельным решением перед её открытием.

## Runtime / UX / analytics backlog
- [x] Implement `/ui` command and Mini App setup-screen MVP.
- [ ] Keep classic Telegram chat UX as default until a separate decision is made.
- [ ] Keep `/stats` owner-only and outside Mini App unless a future explicit decision changes this.
- [ ] Minor setup-screen UI/polish issues remain follow-up backlog items and are not blockers for Mini App runner architecture design.

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

| #133-fix | Compact runner question URL payload for `/ui` active sessions + explicit progress-only message | ✅ Done |

| 2026-05-22 | PR #135/#135-fix | Mini App UX hardening + explicit abandon warning on force-setup path | done |

| 2026-05-23 | follow-up after PR #135 | Mini App setup submit now sends open-first-question button in Mini App and does not auto-post question in chat | done |

| #136-next | Narrow Mini App API for in-window runner progression with Telegram initData auth + sendData fallback retained | ✅ Done |
