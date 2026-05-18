# AI Coding Workflow — техническое задание для репозитория

**Унифицированное название документа:** AI Coding Workflow.  
**Основной режим:** docs-first AI-assisted development.  
**Совместимость:** документ может использоваться автономно или вместе с repo-local утилитой Universal LLM Context Bundle Builder.

## 1. Назначение документа

Документ описывает рабочий процесс AI-assisted development для проекта, где основной контекст, ТЗ, backlog и текущее состояние разработки должны жить внутри репозитория.

Документ предназначен для внедрения в программный проект / репозиторий и должен помочь ChatGPT, Codex, Claude Code, Cursor, Copilot Workspace или другому coding-agent работать без постоянного обращения к старым чатам, внешним Google Docs и GitHub Issues как основному backlog.

Главный принцип:

```text
Репозиторий должен быть самодостаточным.
```

После внедрения новая модель или новый участник проекта должен открыть репозиторий и понять:

- что является актуальным ТЗ проекта;
- где находится текущий delivery plan;
- какой спринт или checkpoint активен сейчас;
- какие backlog items уже сделаны;
- что в работе;
- что делать следующим шагом;
- какие правила должен соблюдать Codex;
- как PR должен обновлять проектное состояние;
- когда GitHub Issues нужны, а когда нет.

## 2. Цель внедрения

Цель внедрения — снизить потерю контекста между обсуждением, задачами, PR, review, merge и следующим шагом разработки.

После внедрения:

- полное ТЗ проекта хранится в репозитории;
- текущие спринты / checkpoints и backlog хранятся в репозитории;
- каждый PR связан с конкретным item из delivery plan;
- если PR завершает, меняет, блокирует, делит или отменяет item, соответствующий документ обновляется в этом же PR;
- если меняется scope проекта, обновляется общее ТЗ проекта;
- GitHub Issues не являются обязательным backlog;
- connector к GitHub Issues не используется для ежедневного ведения статусов;
- ChatGPT проверяет PR против документов репозитория, diff, tests, CI и constraints.

## 3. Основная модель workflow

Базовая схема:

```text
project-spec.md → delivery-plan.md → Codex prompt → PR → review → merge → updated repository state
```

Роли документов:

```text
/docs/project-spec.md
    Единый canonical source of truth по scope, требованиям, бизнес-логике и ограничениям проекта.

/docs/delivery-plan.md
    Операционный backlog: спринты, checkpoints, текущий статус, следующий шаг.

/docs/ai-coding-workflow.md
    Правила работы GPT / Codex / PR / docs в этом репозитории.
```

Правило унификации имён:

```text
/docs/project-spec.md — обязательное финальное имя для проектного ТЗ.
```

Если в репозитории уже есть похожий документ (`product_spec.md`, `prd.md`, `PRODUCT_SPEC.md`, `requirements.md`, `master-spec.md` или другой аналог), его нужно не дублировать, а мигрировать в единый файл `/docs/project-spec.md`: переименовать, перенести содержимое, обновить ссылки и убрать конкурирующий active source of truth.

Рабочий цикл:

1. ChatGPT читает `project-spec.md`, `delivery-plan.md` и релевантные документы.
2. ChatGPT определяет текущую позицию проекта и следующий backlog item.
3. ChatGPT готовит Codex prompt по конкретному item.
4. Codex реализует item через focused PR.
5. Codex обновляет `delivery-plan.md` в этом же PR, если меняется статус item.
6. Codex обновляет `project-spec.md`, если меняется scope, бизнес-логика, ограничения или критерии готовности.
7. ChatGPT review проверяет PR против `project-spec.md`, `delivery-plan.md`, diff, tests, CI и constraints.
8. После merge актуальное состояние проекта уже находится в main branch.

## 4. Что является source of truth

### 4.1. Project source of truth

Главный source of truth по проекту:

```text
/docs/project-spec.md
```

Этот файл отвечает на вопросы:

- что строим;
- зачем строим;
- что входит в scope;
- что не входит в scope;
- какие роли, сценарии и бизнес-правила актуальны;
- какие архитектурные и технические ограничения важны;
- какие критерии готовности применяются к MVP / релизу / checkpoint.

Если код, delivery plan, старый документ или PR противоречат `project-spec.md`, приоритет по умолчанию у `project-spec.md`, пока пользователь явно не примет scope change.

Если до внедрения workflow в репозитории уже был другой активный проектный документ, после миграции он не должен оставаться вторым активным ТЗ. Допустимые варианты: переименовать его в `project-spec.md`, удалить старый файл после переноса или явно пометить старый файл как obsolete / historical, если его нужно сохранить для истории.

Внешние Google Docs, чаты, экспортированные черновики или локальные drafts могут использоваться как editing inputs до синхронизации с репозиторием, но после sync они не являются runtime source of truth.

Для ChatGPT, Codex, PR review и handoff authoritative источниками остаются Markdown-файлы в репозитории.

### 4.2. Operational source of truth

Главный source of truth по текущему движению:

```text
/docs/delivery-plan.md
```

Этот файл отвечает на вопросы:

- где проект находится сейчас;
- какой sprint / checkpoint активен;
- какие items уже done;
- какие items in progress;
- какие items blocked, deferred, split или superseded;
- что является следующим логичным шагом;
- какие PR закрывали конкретные items.

### 4.3. Workflow source of truth

Главный source of truth по правилам работы:

```text
/docs/ai-coding-workflow.md
```

Этот файл отвечает на вопросы:

- как ChatGPT готовит Codex prompts;
- как Codex должен читать документы;
- как выбирать scope PR;
- как обновлять `delivery-plan.md`;
- когда обновлять `project-spec.md`;
- когда использовать GitHub Issues;
- как проводить PR review.

### 4.4. Devtool source of truth

В некоторых репозиториях могут быть внутренние repo-local devtools со своими техническими спецификациями.

Если в репозитории используется **Universal LLM Context Bundle Builder**, source of truth для самой утилиты находится здесь:

```text
/docs/context-bundle-builder/MASTER_SPEC.md
```

Этот файл является source of truth только для devtool-утилиты Context Bundle Builder.

Он не заменяет:

- `/docs/project-spec.md` как project/product source of truth;
- `/docs/delivery-plan.md` как operational source of truth;
- `/docs/ai-coding-workflow.md` как workflow source of truth.

Правила:

- devtool-спецификации могут быть P1 source of truth для собственного scope утилиты;
- devtool-спецификации не должны переопределять основное проектное ТЗ;
- решения по product/project scope фиксируются в `/docs/project-spec.md`;
- порядок работ и текущее состояние фиксируются в `/docs/delivery-plan.md`;
- правила работы ChatGPT / Codex / PR / docs фиксируются в `/docs/ai-coding-workflow.md`;
- PR по самой devtool-утилите должен проверяться против её собственного devtool source of truth.


### 4.5. Source priority model для LLM и Codex

Когда AI Coding Workflow используется автономно, модель читает файлы напрямую из репозитория. Когда вместе с Context Bundle Builder — модель может получать те же источники в составе bundle/archive. В обоих случаях действует единая логика приоритета источников.

| Layer | Source | Meaning |
| :---- | :---- | :---- |
| P1 product | `/docs/project-spec.md` | Главный источник project/product scope, требований, бизнес-логики, ограничений и intended behavior. |
| P1 operational | `/docs/delivery-plan.md` | Текущий delivery state: sprint/checkpoint, backlog item, статус, next recommended item. |
| P1 workflow | `/docs/ai-coding-workflow.md` | Правила работы ChatGPT, Codex, PR, docs и review. |
| P1 devtool | `/docs/context-bundle-builder/MASTER_SPEC.md`, если используется Context Bundle Builder | Source of truth только для devtool-утилиты, не для product scope. |
| P2 | source code, configs, scripts, workflows | Current actual behavior / implementation evidence. |
| P3 | tests, CI, QA checklists, validation docs | Verification evidence, если тесты актуальны и проходят. |
| P4/P5 | supporting docs, legacy notes, generated snapshots | Вспомогательный или низкодоверенный контекст. Не переопределяет P1. |

Правила:

- P1 product requirements нельзя молча переписывать под текущее P2-поведение кода.
- Если P1 и P2 конфликтуют, это docs/code drift или scope decision, а не повод автоматически выбрать код.
- Если P3 тесты конфликтуют с P1 или P2, нужно явно отметить риск устаревшего теста, дефекта или неполного покрытия.
- `delivery-plan.md` объясняет текущую позицию и порядок работ, но не является самостоятельной заменой product requirements.
- `ai-coding-workflow.md` задаёт процесс, но не меняет product scope.
- Generated bundles/archives от Context Bundle Builder являются snapshots, а не source of truth.

## 5. Обязательные файлы в репозитории

Минимальный набор файлов после внедрения:

```text
/docs/project-spec.md
/docs/delivery-plan.md
/docs/ai-coding-workflow.md
README.md
```

Опциональные, но рекомендуемые файлы для более сложных проектов:

```text
/docs/architecture.md
/docs/decisions.md
/docs/testing.md
/docs/operations.md
```

Опциональный отдельный план для AI delivery-инфраструктуры:

```text
/docs/ai-delivery-infrastructure-plan.md
```

Этот файл используется, если внедрение или апгрейд AI Coding Workflow и Context Bundle Builder становится отдельным рабочим контуром. Он не заменяет основной `/docs/delivery-plan.md`.

Корневой `README.md` должен содержать навигацию к ключевым документам:

```md
## Documentation

- [Project Specification](docs/project-spec.md) — актуальное ТЗ проекта и source of truth по scope.
- [Delivery Plan](docs/delivery-plan.md) — спринты, checkpoints, backlog и текущее состояние работ.
- [AI Coding Workflow](docs/ai-coding-workflow.md) — правила работы через ChatGPT, Codex, PR и документацию.
- [AI Delivery Infrastructure Plan](docs/ai-delivery-infrastructure-plan.md) — опциональный план внедрения / апгрейда AI workflow и Context Bundle Builder.
```

Если в проекте уже есть `docs/README.md` или другой индекс документации, туда также нужно добавить ссылки на эти документы.

### 5.1. Унификация существующего ТЗ

Если в репозитории уже существует документ, который фактически выполняет роль проектного ТЗ или product spec, например:

```text
/docs/product_spec.md
/docs/PRODUCT_SPEC.md
/docs/prd.md
/docs/requirements.md
/docs/master-spec.md
```

то при внедрении workflow нужно привести его к единому стандарту:

```text
/docs/project-spec.md
```

Правила миграции:

- не создавать второй конкурирующий source of truth;
- не сжимать существующее ТЗ до summary без явной команды пользователя;
- сохранить актуальные требования, scope, ограничения и решения;
- убрать или явно отделить устаревшие части;
- обновить ссылки в `README.md`, `AGENTS.md`, `delivery-plan.md`, `ai-coding-workflow.md` и других индексах документации;
- если старый файл сохраняется исторически, в начале файла должен быть явный статус `Obsolete / Historical` и ссылка на `/docs/project-spec.md`;
- если объём старого ТЗ слишком большой для безопасной автоматической миграции, coding-agent должен создать `/docs/project-spec.md` с понятной структурой и маркерами для ручной вставки, а не придумывать сокращённую версию.

Исключение для repo-local devtools:

Файл вида:

```text
/docs/context-bundle-builder/MASTER_SPEC.md
```

не должен автоматически мигрироваться, переименовываться или объединяться с:

```text
/docs/project-spec.md
```

если он является технической спецификацией внутренней devtool-утилиты, а не проектным/product ТЗ.

Для Universal LLM Context Bundle Builder действуют отдельные правила:

- `/docs/context-bundle-builder/MASTER_SPEC.md` — source of truth для самой утилиты Context Bundle Builder;
- `/docs/project-spec.md` — source of truth для основного проекта/product scope;
- если оба файла существуют, они не являются конкурирующими source of truth, потому что описывают разные scopes;
- Codex не должен “исправлять” это объединением devtool-спецификации с основным проектным ТЗ;
- если весь репозиторий посвящён только самой утилите Context Bundle Builder, пользователь может отдельно принять решение использовать `/docs/project-spec.md` как проектное ТЗ для этого продукта, но это не должно происходить автоматически.

Цель унификации — чтобы после внедрения у проекта был один очевидный project spec, а не несколько похожих документов с разными именами и разной степенью актуальности.

## 6. Требования к `/docs/project-spec.md`

`project-spec.md` — это полное актуальное ТЗ проекта, а не summary, не краткий handoff и не обзорная концепция.

Файл должен быть самостоятельным документом, который можно читать без старого чата, внешних Google Docs и устных пояснений.

Допустимо и ожидаемо, что `project-spec.md` может быть большим документом, включая 4500+ строк, если именно такой объём нужен для полного и точного описания проекта.

Размер сам по себе не является причиной:

- сокращать ТЗ до summary;
- выносить обязательные требования в неочевидные документы;
- заменять полное ТЗ обзорным описанием;
- оставлять несколько конкурирующих версий ТЗ;
- считать старый `product_spec.md`, `prd.md`, `requirements.md` или `master-spec.md` равноправным active source of truth.

Если часть требований вынесена в дополнительные документы, `project-spec.md` всё равно остаётся canonical entry point и должен явно ссылаться на эти разделы.

Если файл был создан через миграцию из существующего `product_spec.md`, `prd.md`, `requirements.md` или другого аналога, миграция должна сохранять актуальное содержание, а не превращать документ в краткую концепцию. Сокращать, удалять или переинтерпретировать требования можно только если пользователь явно согласовал актуализацию scope.

Рекомендуемая структура:

```md
# Project Specification

## 1. Product goal

## 2. Current scope

## 3. Out of scope

## 4. User roles

## 5. Core scenarios

## 6. Functional requirements

## 7. Business rules

## 8. Data and state model

## 9. Integrations

## 10. Non-functional requirements

## 11. Architecture constraints

## 12. Security and safety constraints

## 13. Observability, logging and diagnostics

## 14. Testing and validation requirements

## 15. MVP / release readiness criteria

## 16. Open questions
```

Правила:

- документ должен описывать актуальный scope, а не историю обсуждений;
- не нужно хранить changelog внутри `project-spec.md`;
- если требование удалено из актуального scope, оно не должно выглядеть как активное;
- идеи будущего развития должны быть отделены от обязательного scope;
- открытые вопросы должны быть явно отделены от принятых решений;
- `project-spec.md` не должен дублировать весь delivery plan;
- `project-spec.md` должен быть главным источником intended behavior для ChatGPT, Codex, review и Context Bundle Builder;
- если код, README, tests, PR или старые документы противоречат `project-spec.md`, это считается drift или scope decision, а не поводом молча переопределять ТЗ.

## 7. Требования к `/docs/delivery-plan.md`

`delivery-plan.md` — это operational source of truth по реализации ТЗ.

Он не заменяет `project-spec.md` и не должен превращаться во второе полное ТЗ. Его задача — показать текущее состояние реализации, порядок работ, следующий рекомендуемый item и связь delivery items с PR.

Целевая модель:

```text
delivery-plan.md = working dashboard + detailed implementation backlog
```

Документ должен быть удобен для:

- человека;
- ChatGPT / reasoning LLM;
- Codex / coding-agent;
- PR review;
- handoff в новый чат, другую модель или другому участнику.

### 7.1. Dashboard-first структура

Верх документа должен работать как dashboard, а не как длинный backlog.

Рекомендуемая структура:

```md
# Delivery Plan

## Progress dashboard

- ✅ D1 — Docs-first stabilization — Done / merged into main
- 👉 R1-S02-D3-01 — <current recommended item> — Current recommended next item
- 📋 R1-S02-D3-02 — <planned item> — Planned
- ⛔ R1-S02-D3-03 — <blocked item> — Blocked: <reason>

## Current position

Current release: <release name>
Current sprint / checkpoint: <name>
Current focus: <short description>
Last completed PR: <PR number or none>
Next recommended item: <item id> — <item title>
Current constraints:
- ...

## Delivery checkpoints / backlog

### Checkpoint D2 — <name>

#### Goal

#### Non-goals

#### Backlog items

##### R1-S01-D2-01 — <item name>

Status: Done
PR: #<number>
Scope:
- ...
Acceptance criteria:
- ...
Result:
- ...

### Checkpoint D3 — <name>
```

Обязательные элементы:

- top Progress dashboard;
- `Current position` block;
- `Next recommended item`;
- деление на sprint / checkpoint / delivery phase;
- цель у каждого checkpoint;
- стабильные delivery item IDs;
- краткий scope у каждого item;
- non-goals для risky или широких items;
- acceptance criteria или ссылка на место, где они описаны;
- validation notes, если item требует проверки;
- completed items содержат ссылку на PR или явно указанный result;
- blocked / deferred / split / superseded items содержат короткую причину;
- internal links / anchors, если документ большой.

### 7.2. Status markers для Progress dashboard

Для верхнего Progress dashboard используются status markers:

```text
✅ Done / merged into main
👉 Current recommended next item
📋 Planned / backlog
⛔ Blocked / conditional
```

Markdown task-list checkbox syntax (`[x]`, `[ ]`) не используется для верхнего Progress dashboard, потому что в GitHub это хуже читается визуально для dashboard-style reading.

Strikethrough не используется для completed items.

Зачёркивание допустимо только для:

- cancelled;
- superseded;
- obsolete;
- removed.

### 7.3. Dashboard не должен дублировать подробный backlog

Верхний dashboard должен быть коротким навигационным слоем.

Он показывает:

- что уже сделано;
- что сейчас рекомендуется делать;
- что запланировано;
- что заблокировано или conditional;
- где находится подробное описание item-а.

Подробный scope, acceptance criteria, validation и result живут ниже в detailed backlog section.


### 7.4. Отдельный план для AI delivery-инфраструктуры

`/docs/delivery-plan.md` — это основной operational delivery dashboard проекта / продукта.

Он должен трекать реализацию `/docs/project-spec.md`, а не подробную реализацию AI workflow-инфраструктуры, repo-local devtools или утилиты Context Bundle Builder.

Если AI Coding Workflow и Context Bundle Builder внедряются, апгрейдятся или стабилизируются внутри того же репозитория как отдельный рабочий контур, их operational work SHOULD трекаться в отдельном файле:

```text
/docs/ai-delivery-infrastructure-plan.md
```

Этот файл может покрывать:

- внедрение AI Coding Workflow;
- обновления `/docs/ai-coding-workflow.md`;
- внедрение, апгрейд и hardening Context Bundle Builder;
- GitHub Actions Run workflow UX;
- `context_bundles.toml`;
- project-specific component scopes;
- split/chunk behavior для больших P1-документов;
- tests и документацию для utility/workflow layer;
- PR templates, docs indexes и вспомогательные правила, если они относятся к AI workflow.

Правила разделения:

- `/docs/delivery-plan.md` остаётся единственным основным delivery plan для product/project scope.
- `/docs/ai-delivery-infrastructure-plan.md` трекает AI workflow + utility implementation / upgrade work.
- Основной `/docs/delivery-plan.md` MAY содержать короткую ссылку на AI infrastructure plan, но SHOULD NOT дублировать его detailed backlog.
- Product delivery items и AI infrastructure delivery items SHOULD NOT смешиваться в одном checkpoint, если PR специально не затрагивает оба scopes.
- Если один PR меняет и product behavior, и AI delivery infrastructure, PR MUST явно указать оба affected delivery items и обновить оба relevant plans.
- Если весь репозиторий посвящён только AI workflow / Context Bundle Builder, основной `/docs/delivery-plan.md` MAY использоваться как primary delivery plan для этого devtool/product repository.

Decision table для создания `/docs/ai-delivery-infrastructure-plan.md`:

| Repository mode | Create infrastructure plan? | Reason |
| :---- | :---- | :---- |
| Workflow only, small project | Optional | Workflow can operate through project docs, PR diff, tests and CI. |
| Workflow only, many workflow changes over PRs | Recommended | Needed to track adoption, prompt rules, PR rules and documentation guardrails. |
| Builder only, dedicated Builder repository | Optional / use main delivery plan | The whole repository may already be the devtool product. |
| Builder inside larger product repository | Recommended | Utility work should not pollute product delivery plan. |
| Workflow + Builder integrated | Recommended / usually required | Needed to track Workflow, Builder and Integration coverage separately. |

Рекомендуемая короткая ссылка в основном delivery plan:

```md
## AI delivery infrastructure

AI Coding Workflow and Context Bundle Builder implementation are tracked separately:

- [AI Delivery Infrastructure Plan](docs/ai-delivery-infrastructure-plan.md)
```

## 8. Delivery item, ID convention и checkpoint-модель

Backlog item — это единица работы внутри sprint / checkpoint / delivery phase.

Item не обязан равняться одному PR. Один item может закрываться несколькими PR, если это явно отражено в `delivery-plan.md`.

### 8.1. Delivery item ID convention

Каждый проект должен иметь стабильную convention для delivery item IDs.

IDs нужны для:

- ссылок в PR;
- Codex prompts;
- review comments;
- синхронизации `delivery-plan.md`;
- handoff между чатами / моделями.

IDs не являются:

- GitHub Issue numbers;
- priorities;
- estimates;
- доказательством реализации;
- заменой human-readable title.

Human-readable title остаётся authoritative для смысла item-а.

Пример project-specific convention:

```text
CB-D1-*        = legacy docs-first stabilization items
R1-S01-D2-NN   = Release 1 / Sprint 01 / Delivery checkpoint 2 / item number
R1-S01-D2-NNa  = sub-item under a major item
R1-S02-D3-NN   = Release 1 / Sprint 02 / Delivery checkpoint 3 / item number
```

Расшифровка примера:

- `R1` = Release 1;
- `S01` / `S02` = sprint / planning or implementation iteration;
- `D2` / `D3` = delivery checkpoint;
- `NN` = item number inside checkpoint;
- letter suffixes `a`, `b`, `c` = sub-items under a major item.

Этот формат является примером, а не обязательным универсальным стандартом для всех проектов.

### 8.2. Planning checkpoints vs implementation checkpoints

Delivery plan может разделять planning / normalization checkpoints и implementation / hardening checkpoints.

Planning / normalization checkpoint нужен, чтобы:

- разложить scope из `project-spec.md` в implementation-ready backlog items;
- уточнить acceptance criteria;
- разделить слишком крупные items;
- нормализовать backlog;
- не менять runtime / product behavior без явного scope.

Implementation / hardening checkpoint нужен, чтобы:

- реализовывать выбранные scoped items;
- harden existing behavior;
- обновлять tests/docs;
- сохранять safety boundaries;
- не расширять product scope без явного решения.

Каждый checkpoint должен явно описывать:

- goal;
- non-goals;
- safety / scope boundaries;
- planned items;
- current / next item.

### 8.3. Шаблон delivery item

```md
##### R1-S02-D3-01 — Add minimal CI

Status: Ready for Codex
Scope:
- Add GitHub Actions workflow for PR checks.
- Run tests without real external API calls.
- Document CI behavior in README or docs/testing.md.
Non-goals:
- Do not add deployment automation.
- Do not introduce new external services.
Acceptance criteria:
- CI runs on pull requests.
- Test command is documented.
- CI does not require production secrets.
Validation:
- Run local tests if possible.
- Check GitHub Actions result after PR is opened.
```

После полного завершения:

```md
##### R1-S02-D3-01 — Add minimal CI

Status: Done
PR: #15
Result:
- GitHub Actions workflow added.
- Test command documented.
- CI runs on PR without production secrets.
```

Если item завершён частично:

```md
##### R1-S02-D3-01 — Add minimal CI

Status: Partially done
PRs:
- #15 — added workflow skeleton
Remaining:
- Fix test command.
- Document CI behavior.
```

Если item разделён:

```md
##### R1-S02-D3-01 — Add minimal CI

Status: Split
Reason: item was too broad for one focused PR.
Split into:
- R1-S02-D3-01a — Add CI workflow skeleton
- R1-S02-D3-01b — Add test command and docs
```

## 9. Статусы backlog items

Минимальный набор статусов:

```text
Backlog
Ready for Codex
In PR
Done
Blocked
Partially done
Deferred
Split
Superseded
Removed
```

Правила:

- `Backlog` — item запланирован, но ещё не готов или не выбран.
- `Ready for Codex` — item достаточно понятен для подготовки Codex prompt.
- `In PR` — по item открыт PR.
- `Done` — acceptance criteria выполнены и PR смержен или готов к merge по решению пользователя.
- `Blocked` — есть внешний или технический blocker.
- `Partially done` — часть scope реализована, но item не закрыт.
- `Deferred` — item отложен, но не удалён из возможного будущего scope.
- `Split` — item разделён на несколько новых items.
- `Superseded` — item заменён другим item или решением.
- `Removed` — item больше не нужен и не должен рассматриваться как будущая работа.

Не нужно вводить сложную status-систему, если этих статусов достаточно.

## 10. Правила связи PR и delivery plan

Каждый PR должен указывать, к какому item из `delivery-plan.md` он относится.

PR body должен содержать:

```md
## Delivery item

Sprint / checkpoint: <name>
Item: <item id> — <item name>

## Summary

## Scope status

- [ ] Code updated
- [ ] Tests updated
- [ ] Docs updated
- [ ] delivery-plan.md updated

## Project spec impact

- [ ] No project-spec.md changes needed
- [ ] project-spec.md updated
- [ ] Scope decision required

## AI delivery infrastructure impact

- [ ] No AI workflow / Context Bundle Builder changes needed
- [ ] ai-delivery-infrastructure-plan.md updated
- [ ] ai-coding-workflow.md updated
- [ ] Context Bundle Builder spec/config/docs/tests updated
- [ ] Cross-document sync checked

## Cross-document sync check

Check if this PR affects:

- [ ] source-of-truth document paths
- [ ] baseline P1 files
- [ ] Analysis Profiles / scenarios / presets
- [ ] component scopes
- [ ] split/chunk policy for large P1 documents
- [ ] generated archive/bundle contract
- [ ] PR / review workflow assumptions
- [ ] AI delivery infrastructure plan coverage

Result:

- [ ] No cross-document changes needed
- [ ] `/docs/ai-coding-workflow.md` updated
- [ ] `/docs/context-bundle-builder/MASTER_SPEC.md` updated
- [ ] `/docs/ai-delivery-infrastructure-plan.md` updated
- [ ] README / docs navigation updated

## Validation

## Risks / notes
```

Правила:

- если PR полностью завершает item, `delivery-plan.md` должен отметить item как `Done` или готовый к `Done` по решению пользователя;
- если PR делает item частично, `delivery-plan.md` должен показать remaining work;
- если PR меняет порядок работ, `delivery-plan.md` должен быть обновлён;
- если PR меняет scope проекта, `project-spec.md` должен быть обновлён;
- если PR меняет AI workflow / Context Bundle Builder delivery state, `/docs/ai-delivery-infrastructure-plan.md` должен быть обновлён, если этот файл используется в репозитории;
- если scope decision требуется, PR не должен молча менять поведение только в коде;
- PR может ссылаться на delivery-plan item без GitHub Issue.

### 10.1. Delivery-plan synchronization rule

Любой PR, который меняет статус, scope, result или next-step position delivery item-а, обязан синхронизировать все затронутые части `docs/delivery-plan.md`.

Минимально обновляются:

- top Progress dashboard;
- `Current position` block;
- detailed backlog section for affected item;
- `Next recommended item`;
- explicit anchors / internal links, если они есть.

Недопустимо:

- обновить detailed item, но оставить stale dashboard;
- обновить dashboard, но оставить stale detailed section;
- закрыть PR без актуализации next recommended item;
- поменять статус item-а только в PR body, но не в `delivery-plan.md`;
- оставить PR/result внизу, но не показать его в верхнем dashboard, если item виден в dashboard.

## 11. Обновление документов в PR

Обновление документов — часть реализации, а не отдельная ручная операция после merge.

Codex должен обновить документы в том же PR, если:

- item завершён;
- item частично завершён;
- item заблокирован;
- item разделён;
- item отменён;
- item заменён другим item;
- изменился порядок работ;
- изменился scope проекта;
- изменились бизнес-правила;
- изменились архитектурные ограничения;
- изменились критерии готовности.

Не нужно обновлять документы ради каждого микрошагa, если состояние проекта не изменилось.

### 11.1. Large source-of-truth document edit guardrail

`/docs/project-spec.md` может быть большим полным ТЗ. Размер сам по себе не является причиной сокращать, переписывать, суммаризировать или заменять этот файл.

Если `project-spec.md` или другой крупный source-of-truth документ слишком большой для безопасной полной перезаписи агентом, Codex не должен заменять весь файл целиком.

Разрешённые варианты:

1. Сделать минимальную точечную правку через безопасный patch/diff mechanism.
2. Изменить только релевантный раздел, если инструмент редактирования гарантированно сохраняет остальной файл.
3. Если безопасная точечная правка невозможна, создать proposal-файл:

```text
docs/proposals/scope-update-PR-<PR_NUMBER_OR_ITEM_ID>.md
```

Proposal должен содержать:

- целевой документ;
- целевой раздел;
- предлагаемую вставку или замену;
- причину изменения;
- связанный delivery item;
- является ли изменение scope change или уточнением документации.

Codex не должен молча сокращать, обрезать, перегенерировать или заменять большой source-of-truth документ summary-версией.

## 12. Правила scope change

Scope change — это изменение того, что проект должен делать или не должен делать.

Scope change требует обновления `project-spec.md`, если изменяются:

- функциональные требования;
- бизнес-правила;
- роли пользователей;
- ключевые сценарии;
- интеграции;
- данные или состояния;
- архитектурные constraints;
- security / safety constraints;
- MVP или release readiness criteria.

Если изменение влияет только на порядок выполнения работ, но не меняет требования проекта, достаточно обновить `delivery-plan.md`.

Если Codex обнаружил, что реализация требует scope decision, он должен остановиться и явно написать это в PR / отчёте, а не принимать продуктовые решения самостоятельно.

## 13. GitHub Issues policy

GitHub Issues не являются основным backlog для этого workflow.

Основной backlog живёт в:

```text
/docs/delivery-plan.md
```

Основное ТЗ живёт в:

```text
/docs/project-spec.md
```

GitHub Issues можно использовать только как optional-инструмент для случаев, где они реально полезны:

- long-lived bug;
- blocker;
- внешняя дискуссия;
- крупная задача, которую неудобно держать только в delivery plan;
- follow-up, который нельзя потерять, но он не входит в текущий sprint / checkpoint;
- задача, к которой нужно привязать несколько PR и отдельное обсуждение.

Не нужно создавать GitHub Issues для каждого sprint backlog item.

Не нужно требовать, чтобы каждый PR закрывал issue.

Не нужно использовать GitHub Issues как Jira-like tracker.

Если Issue создана, она должна ссылаться на релевантный item из `delivery-plan.md` или объяснять, почему item пока не добавлен в delivery plan.

## 14. Connector usage policy

Connector к GitHub Issues не должен быть обязательной частью ежедневного workflow.

ChatGPT не должен использовать connector для:

- создания issue на каждый item;
- обновления каждого checklist item;
- закрытия задач после каждого merge;
- косметических label changes;
- промежуточных статусов без управленческой пользы.

Connector можно использовать для:

- чтения PR;
- чтения diff / CI, если доступно;
- редких blocker issues;
- крупных bugs;
- внешних issues, которые действительно нужны;
- контрольных действий по явной команде пользователя.

Главный принцип:

```text
Project state should be recoverable from repository documents, not from connector history.
```

## 15. Context Bundle Builder integration policy

**Universal LLM Context Bundle Builder** — это опциональная repo-local devtool-утилита для сбора структурированного контекста репозитория для reasoning LLM и coding-agent workflows.

Утилита особенно полезна для крупных, фрагментированных или high-context проектов, где ручной сбор контекста становится дорогим, рискованным или неполным.

Context Bundle Builder не является обязательной зависимостью AI Coding Workflow. Отсутствие утилиты в проекте — нормальный автономный режим, а не degraded mode.

Утилита может реализовываться и поддерживаться через тот же PR workflow, что и остальные артефакты репозитория. При этом после внедрения и стабилизации она не является обязательным gate для каждого обычного product/project PR.

### 15.1. Автономность и режимы работы

AI Coding Workflow и Context Bundle Builder совместимы, но независимы.

Короткий принцип:

```text
Workflow must not depend on Builder.
Builder must not depend on Workflow.
Integration rules apply only when both are present.
```

#### Mode A — AI Coding Workflow only

Репозиторий может использовать этот AI Coding Workflow без Context Bundle Builder.

В этом режиме ChatGPT, reasoning LLM и Codex работают напрямую с:

- `/docs/project-spec.md`;
- `/docs/delivery-plan.md`;
- `/docs/ai-coding-workflow.md`;
- `README.md`;
- релевантными architecture/testing/operations docs;
- PR diff, tests и CI.

Context Bundle Builder не требуется для обычных focused PR, небольших репозиториев или проектов, где ручного сбора контекста достаточно.

#### Mode B — Context Bundle Builder only

Репозиторий может использовать Context Bundle Builder даже если AI Coding Workflow не внедрён.

В этом режиме утилита собирает лучший доступный безопасный контекст по собственной конфигурации:

- `context_bundles.toml`;
- scenarios;
- presets;
- source-priority rules;
- exclusions;
- safety checks;
- output manifest.

Если файлов AI Coding Workflow нет, утилита не должна требовать их наличия. Отсутствие `/docs/project-spec.md`, `/docs/delivery-plan.md` или `/docs/ai-coding-workflow.md` не должно делать standalone bundle generation incomplete, если выбранный scenario явно не требует эти файлы.

#### Mode C — Integrated AI Coding Workflow + Context Bundle Builder

Если в репозитории есть оба слоя, Context Bundle Builder помогает AI Coding Workflow собирать большой или структурированный контекст.

В этом режиме:

- AI Coding Workflow определяет, как ChatGPT, Codex, PR и repository docs используются в delivery process;
- Context Bundle Builder собирает и маркирует context snapshot;
- generated bundles и archives остаются временными snapshots, а не source of truth;
- repository source-of-truth files остаются authoritative;
- cross-document sync нужен только для изменений, которые затрагивают оба слоя.

Для ключевых integrated profiles (`complete_project_context_archive`, `docs_vs_code_audit`, `component_review`) baseline-файлы `/docs/project-spec.md`, `/docs/delivery-plan.md` и `/docs/ai-coding-workflow.md` должны включаться или явно попадать в manifest как missing / skipped / incomplete с причиной.

Для `business_documentation_review` `/docs/project-spec.md` должен включаться, если доступен; `/docs/delivery-plan.md` и `/docs/ai-coding-workflow.md` желательно включать, если профиль не настроен как product-only.

Для `cleanup_audit` baseline P1-документы используются как intended behavior context, но не являются cleanup target.

Большой `/docs/project-spec.md` нельзя молча пропускать, обрезать или заменять summary. Если файл слишком большой для обычного bundle, утилита должна использовать split/chunk/archive strategy или явно пометить контекст как incomplete.

Интегрированный поток:

```text
/docs/project-spec.md + /docs/delivery-plan.md + /docs/ai-coding-workflow.md
→ Context Bundle Builder archive/bundle
→ reasoning LLM analysis
→ focused Codex prompt
→ focused PR
→ review
→ merge
→ updated repository state
```

### 15.2. Когда использовать Context Bundle Builder

Используй Context Bundle Builder, когда контекст репозитория слишком большой, фрагментированный или рискованный для ручного сбора, например:

- старт нового чата или передача состояния проекта другой модели;
- глубокий аудит репозитория;
- сверка документации, кода, конфигов и тестов;
- ревью конкретного компонента, модуля, эпика, папки или feature area;
- cleanup audit;
- внешний model review;
- подготовка качественного Codex prompt, которому нужен широкий контекст репозитория.

Для маленьких focused PR запуск Context Bundle Builder опционален.

### 15.3. Матрица выбора Analysis Profile

Если Context Bundle Builder есть в проекте, выбирай профиль по текущей задаче:

| Ситуация | Recommended profile | Комментарий |
| :---- | :---- | :---- |
| Старт нового чата / handoff другой модели | `complete_project_context_archive` | Для глубокого восстановления контекста проекта. |
| Бизнес-анализ, проверка идеи, ревью документации без тяжёлого кода | `business_documentation_review` | Основной фокус на P1/P4 документации. |
| Проверка соответствия реализации ТЗ | `docs_vs_code_audit` | Для docs/code/test drift. |
| Планирование нового epic / feature area | `component_review` без `target_scope` | Модель строит карту компонентов и предлагает decomposition. |
| Подготовка крупного focused Codex task | `component_review` с `target_scope` | Например: `auth`, `billing`, `trainer-app`, `notifications`. |
| Cleanup / поиск устаревшего технического хвоста | `cleanup_audit` | Report-only; документация используется как intended behavior, а не cleanup target. |

### 15.4. Когда обновлять Context Bundle Builder

Обновляй Context Bundle Builder только если меняется одно из следующего:

- его собственная техническая спецификация;
- CLI behavior;
- GitHub Actions workflow;
- `context_bundles.toml` rules;
- presets, scenarios или Analysis Profiles;
- safety exclusions;
- generated archive/bundle contract;
- документация или тесты самой утилиты;
- структура репозитория так, что это влияет на сбор контекста.

Обычное изменение product/project scope не требует автоматического изменения Context Bundle Builder, если оно не влияет на то, какие файлы, директории, документы, тесты, конфиги или exclusions должны попадать в контекст.

### 15.5. AI delivery infrastructure decomposition plan

Большие базовые ТЗ по AI-assisted delivery layer также должны иметь операционную декомпозицию по той же логике, что и большое проектное ТЗ декомпозируется в `/docs/delivery-plan.md`.

Для AI Coding Workflow и опционального Context Bundle Builder такой декомпозированный операционный слой называется:

```text
/docs/ai-delivery-infrastructure-plan.md
```

Это **не сам workflow**, **не ТЗ утилиты** и **не сокращённая версия больших спецификаций**. Это отдельный operational decomposition / coverage plan, который показывает, как требования из базовых ТЗ внедряются, проверяются и поддерживаются в конкретном репозитории.

#### Purpose

`/docs/ai-delivery-infrastructure-plan.md` SHOULD be created when AI workflow / utility adoption becomes a meaningful workstream, especially when:

- `/docs/ai-coding-workflow.md` is large enough that implementation details can be missed;
- Context Bundle Builder is planned, partially implemented or already used;
- AI workflow, PR rules, Codex prompts, templates, context collection or generated artifacts evolve over several PRs;
- there is a need to track coverage of workflow/utility requirements separately from product delivery;
- a project uses Mode C — integrated AI Coding Workflow + Context Bundle Builder.

For very small repositories that only copy a simple workflow document and do not maintain a separate AI infrastructure workstream, this file MAY be omitted. In that case, AI Coding Workflow still works autonomously through repository docs, PR diff, tests and CI.

#### Creation decision table

| Repository mode | Create infrastructure plan? | Reason |
| :---- | :---- | :---- |
| Workflow only, small project | Optional | Workflow can operate through project docs, PR diff, tests and CI. |
| Workflow only, many workflow changes over PRs | Recommended | Needed to track adoption, prompt rules, PR rules and documentation guardrails. |
| Builder only, dedicated Builder repository | Optional / use main delivery plan | The whole repository may already be the devtool product. |
| Builder inside larger product repository | Recommended | Utility work should not pollute product delivery plan. |
| Workflow + Builder integrated | Recommended / usually required | Needed to track Workflow, Builder and Integration coverage separately. |

#### Required role

The file MUST track operational decomposition for AI delivery infrastructure, not product features.

It may cover:

- AI Coding Workflow adoption and updates;
- synchronization of `/docs/ai-coding-workflow.md`;
- reusable Codex prompt blocks;
- PR template / PR body rules;
- source priority rules and docs/code/test drift rules;
- large source-of-truth edit guardrails;
- Context Bundle Builder implementation, upgrades, tests, configuration and GitHub Actions UX, if the utility is used;
- `context_bundles.toml` updates;
- project-specific component scopes;
- split/chunk behavior for large P1 documents;
- utility/workflow documentation and tests;
- integration rules between Workflow and Builder.

It MUST NOT replace:

- `/docs/delivery-plan.md` as the main product/project delivery dashboard;
- `/docs/project-spec.md` as the product/project source of truth;
- `/docs/ai-coding-workflow.md` as the workflow rules source of truth;
- `/docs/context-bundle-builder/MASTER_SPEC.md` as the utility technical specification;
- PR review, tests or CI.

The main `/docs/delivery-plan.md` MAY link to this file but SHOULD NOT duplicate the full AI infrastructure backlog.

#### Required structure

The infrastructure plan SHOULD follow the same dashboard-first style as `/docs/delivery-plan.md`:

```md
# AI Delivery Infrastructure Plan

## Progress dashboard

## Current position

## Track status

## Requirement coverage matrix

## Delivery checkpoints / backlog

## Validation and evidence
```

Minimum required sections:

1. **Progress dashboard** — short top-level view of done/current/planned/blocked AI infrastructure work.
2. **Current position** — current mode, active track, next recommended item and relevant constraints.
3. **Track status** — explicit state of Workflow, Builder and Integration tracks.
4. **Requirement coverage matrix** — mapping from source specification sections/requirement areas to delivery items, status and evidence.
5. **Delivery checkpoints / backlog** — implementation-ready work items with stable IDs, scope, non-goals and acceptance criteria.
6. **Validation and evidence** — PRs, tests, docs updates, manual checks or reasons why validation is not available.

#### Track model

The file SHOULD use three independent tracks:

| Track | Applies when | Purpose |
| :---- | :---- | :---- |
| Track A — AI Coding Workflow | AI Coding Workflow is adopted or maintained | Docs-first process, source priority, Codex prompts, PR rules, review rules, large-doc guardrails. |
| Track B — Context Bundle Builder | Builder is planned, adopted or maintained | CLI, TOML, scenarios, presets, profiles, GitHub Actions, split/chunk, tests, docs. |
| Track C — Integration | Workflow and Builder are both present | Mode C behavior, baseline P1 inclusion, profile selection matrix, cross-document sync. |

If only AI Coding Workflow is present, Track A is active and Tracks B/C MAY be marked `Not adopted` / `Not applicable`.

If Context Bundle Builder is absent, this MUST NOT be treated as incomplete workflow adoption.

If Context Bundle Builder is added later, Track B and then Track C can be activated in the same file without creating a competing operational plan.

#### Coverage rule

The infrastructure plan MUST NOT copy the full text of `/docs/ai-coding-workflow.md` or `/docs/context-bundle-builder/MASTER_SPEC.md`.

Instead, it SHOULD provide traceability:

```text
source spec area → delivery item → status → PR/evidence → validation
```

Every significant implementation/adoption requirement from the AI workflow and, when used, the Builder specification SHOULD have one of these states:

- `Done`;
- `Partial`;
- `Ready for Codex`;
- `Backlog`;
- `Blocked`;
- `Deferred`;
- `Not applicable`;
- `Out of scope`.

No large section of the workflow or utility specification should be silently uncovered when that layer is active in the repository.

#### PR update rule

Any PR that changes AI workflow / Context Bundle Builder delivery state SHOULD update `/docs/ai-delivery-infrastructure-plan.md` when this file is used.

This includes PRs that:

- add, remove or change workflow rules;
- change reusable Codex prompts;
- change PR templates or documentation update rules;
- add or upgrade Context Bundle Builder;
- change `context_bundles.toml`;
- change scenarios, presets, Analysis Profiles or component scopes;
- change generated archive/bundle contract;
- change split/chunk behavior for large P1 documents;
- change integration assumptions between Workflow and Builder.

### 15.6. Cross-document synchronization rule

Если оба слоя присутствуют в репозитории, изменения одного слоя должны проверяться на влияние на другой слой.

Integration-related sections in `/docs/ai-coding-workflow.md` and `/docs/context-bundle-builder/MASTER_SPEC.md` are intentionally synchronized. When changing autonomy modes, baseline P1 files, Analysis Profiles, source priority, split/chunk policy, generated archive contract, PR workflow assumptions or AI delivery infrastructure rules, both documents MUST be checked in the same PR.

Если меняется `/docs/ai-coding-workflow.md`, проверь, нужны ли изменения в:

- `/docs/context-bundle-builder/MASTER_SPEC.md`;
- `context_bundles.toml`;
- `.github/workflows/context-bundles.yml`;
- `docs/CONTEXT_BUNDLES.md`;
- `/docs/ai-delivery-infrastructure-plan.md`.

Проверяй особенно:

- source-of-truth document paths;
- baseline P1 documents;
- Analysis Profiles / scenarios;
- component scopes;
- split/chunk policy for large P1 documents;
- generated archive/bundle contract;
- PR/review workflow assumptions.

Если меняется `/docs/context-bundle-builder/MASTER_SPEC.md`, проверь, нужны ли изменения в:

- `/docs/ai-coding-workflow.md`;
- `/docs/ai-delivery-infrastructure-plan.md`;
- README documentation links;
- PR templates or reusable Codex prompt blocks.

Normal product scope changes do not require Context Bundle Builder changes unless they affect context collection rules, source-of-truth paths, repository structure, safety exclusions, generated output contract, scenarios, presets or Analysis Profiles.

### 15.7. Что Context Bundle Builder не заменяет

Context Bundle Builder не заменяет:

- `/docs/project-spec.md` как project/product source of truth;
- `/docs/delivery-plan.md` как operational backlog и current project position;
- `/docs/ai-coding-workflow.md` как правила ChatGPT / Codex / PR / docs;
- reasoning LLM analysis;
- PR review;
- tests и CI;
- решение пользователя по scope changes.

Generated bundles и archives не должны коммититься в репозиторий, если это явно не требуется проектом.


## 16. Правила для ChatGPT / аналитической модели

Перед подготовкой Codex prompt ChatGPT должен прочитать или запросить актуальное состояние:

```text
/docs/project-spec.md
/docs/delivery-plan.md
/docs/ai-coding-workflow.md
```

Если доступны дополнительные релевантные документы, ChatGPT учитывает их:

```text
/docs/architecture.md
/docs/decisions.md
/docs/testing.md
README.md
```

ChatGPT должен:

- определить текущий sprint / checkpoint;
- определить следующий item или подтвердить выбранный пользователем item;
- проверить, что item достаточно конкретен для Codex;
- подготовить prompt с указанием файлов, scope, non-goals, constraints и validation;
- не добавлять требования, которых нет в `project-spec.md` или явно принятом scope change;
- при review проверять PR против project-spec, delivery-plan, diff, tests, CI и constraints;
- если PR не готов, дать follow-up prompt для Codex.

## 17. Правила для Codex / coding-agent

Codex должен работать по конкретному item из `delivery-plan.md`.

Перед изменениями Codex должен прочитать:

```text
/docs/project-spec.md
/docs/delivery-plan.md
/docs/ai-coding-workflow.md
```

Codex должен соблюдать правила:

- не расширять scope за пределы выбранного item;
- не менять project scope без обновления `project-spec.md` или явного scope decision;
- не добавлять новые внешние зависимости без явного требования и обоснования;
- не делать unrelated refactoring;
- не коммитить generated artifacts, если они не нужны проекту;
- не выполнять реальные внешние API/network calls в tests, если это не разрешено;
- обновлять `delivery-plan.md` в том же PR, если меняется статус item;
- обновлять `project-spec.md`, если меняется scope проекта;
- перед PR запускать релевантные проверки или объяснять, почему это невозможно.

## 18. Reusable Codex prompt block

Этот блок можно добавлять в конкретные Codex prompts:

```text
Before making changes, read:

- /docs/project-spec.md
- /docs/delivery-plan.md
- /docs/ai-coding-workflow.md
- README.md
- any relevant architecture/testing docs

If Context Bundle Builder is present and the task requires broad or structured context, use the generated bundle/archive as additional context snapshot, not as source of truth.

Source priority:
- Use P1 /docs/project-spec.md as the ultimate source of truth for project scope, requirements, business logic and intended behavior.
- Use P1 operational /docs/delivery-plan.md as the source of truth for sprint/checkpoint backlog, current project position and selected delivery item.
- Use P1 workflow /docs/ai-coding-workflow.md as the source of truth for ChatGPT/Codex/PR/docs rules.
- Treat existing source code and configuration as P2 current actual behavior.
- Treat tests, CI and QA materials as P3 verification evidence.
- Never override P1 product documentation merely to match P2 code. If P1 documentation and P2 implementation conflict, report docs/code drift or scope decision required.

Work only on the selected delivery item unless explicitly instructed otherwise.

Selected item:
<insert sprint/checkpoint and item id>

Rules:
- Do not expand scope beyond the selected item.
- Do not silently change project scope in code.
- If project scope, business rules, architecture constraints or release criteria change, update /docs/project-spec.md or report that a scope decision is required.
- If /docs/project-spec.md is too large for safe full-file editing, use a targeted patch or create docs/proposals/scope-update-PR-<ID>.md instead of rewriting the whole file.
- If this PR completes, changes, blocks, splits, supersedes or defers the selected item, update /docs/delivery-plan.md in the same PR.
- If this PR changes AI workflow / Context Bundle Builder delivery state, update /docs/ai-delivery-infrastructure-plan.md when that file is used.
- Do not mark an item as Done unless acceptance criteria are satisfied.
- If the item is only partially done, keep it unchecked and document remaining work.
- Avoid unrelated refactoring.
- Do not add external dependencies unless explicitly required and justified.
- Run relevant validation before opening PR, or explain why validation could not be run.

PR body must include:
- Sprint/checkpoint name
- Delivery item ID and name
- Summary
- Validation
- Docs updated
- Project spec impact
- AI delivery infrastructure impact
- Risks / notes
```

## 19. PR review rules

ChatGPT review должен проверять PR не против GitHub Issue, а против:

```text
project-spec.md + delivery-plan.md + ai-coding-workflow.md + diff + tests + CI
```

Проверить:

- PR указывает конкретный sprint / checkpoint item;
- diff соответствует item scope;
- scope не расползся;
- non-goals соблюдены;
- acceptance criteria выполнены или remaining work явно указан;
- `delivery-plan.md` обновлён корректно;
- `project-spec.md` обновлён, если изменился scope проекта;
- item не отмечен Done преждевременно;
- split / blocked / deferred / superseded items оформлены понятно;
- tests / CI / validation выполнены или исключение явно принято;
- новые зависимости не добавлены неявно;
- нет unrelated refactoring;
- README / docs navigation не сломаны.

Результат review:

```text
Merge-ready
Needs fixes
Blocked
Needs product decision
Needs technical decision
```

Если PR не готов, ChatGPT должен дать конкретный follow-up prompt для Codex.

## 20. Merge rules

Merge допустим, если:

- PR соответствует selected delivery item;
- изменения не выходят за scope;
- acceptance criteria выполнены или remaining work явно отражён;
- `delivery-plan.md` обновлён, если состояние item изменилось;
- `project-spec.md` обновлён, если изменился scope проекта;
- CI зелёный или исключение явно принято пользователем;
- нет критичных blockers;
- нет скрытых внешних зависимостей;
- нет unrelated refactoring, который усложняет review.

После merge дополнительное закрытие GitHub Issue не требуется, если issue не использовалась.

Актуальное состояние проекта должно быть восстановимо из main branch.

## 21. Что не делаем по умолчанию

По умолчанию не внедряем:

- обязательные GitHub Issues для каждого item;
- GitHub Projects;
- Jira-like статусы;
- сложную label taxonomy;
- issue forms;
- автоматическую генерацию prompt files;
- автоматический post-merge update bot;
- обязательный changelog для каждого микрошагa;
- отдельный dashboard, пока `delivery-plan.md` справляется.

Эти элементы можно добавить позже, только если они решают реальную проблему, а не создают дополнительную бюрократию.

## 22. Acceptance criteria для внедрения workflow

Workflow считается внедрённым, если:

- [ ] В репозитории есть `/docs/project-spec.md` как единый project/product source of truth.
- [ ] Если раньше существовал `product_spec.md`, `prd.md`, `requirements.md` или другой аналог, он переименован / перенесён / явно помечен как obsolete, чтобы не оставалось конкурирующего active source of truth.
- [ ] Все ссылки на старое имя проектного ТЗ обновлены на `/docs/project-spec.md`.
- [ ] В репозитории есть `/docs/delivery-plan.md`.
- [ ] В репозитории есть `/docs/ai-coding-workflow.md`.
- [ ] Если в репозитории есть Context Bundle Builder, его `/docs/context-bundle-builder/MASTER_SPEC.md` распознан как devtool source of truth, а не как конкурирующий project spec.
- [ ] Если Context Bundle Builder используется, понятно, когда его запускать, а когда он не нужен для обычного focused PR.
- [ ] `README.md` содержит ссылки на ключевые документы.
- [ ] `project-spec.md` можно читать без старого чата и внешних Google Docs.
- [ ] `delivery-plan.md` показывает текущий sprint / checkpoint, backlog и следующий шаг.
- [ ] У backlog items есть стабильные ID.
- [ ] У backlog items есть понятный status.
- [ ] PR template или workflow rules требуют указывать delivery item.
- [ ] PR rules требуют обновлять `delivery-plan.md`, если item изменился.
- [ ] PR rules требуют обновлять `project-spec.md`, если изменился scope проекта.
- [ ] GitHub Issues описаны как optional, а не как основной backlog.
- [ ] Connector к Issues не требуется для понимания текущего состояния проекта.
- [ ] Новая модель может открыть репозиторий и понять, где проект находится и что делать дальше.

- [ ] Если Context Bundle Builder отсутствует, workflow всё равно автономно работает через repository docs, PR diff, tests и CI.
- [ ] Если Context Bundle Builder присутствует, режимы Mode A/B/C и правила интеграции описаны без превращения утилиты в обязательную зависимость каждого PR.
- [ ] Reusable Codex prompt block содержит P1/P2/P3 source priority rules.
- [ ] PR template / workflow rules содержат AI delivery infrastructure impact block.
- [ ] Для больших source-of-truth документов есть guardrail против полной небезопасной перезаписи.
- [ ] Если оба слоя присутствуют, cross-document sync проверяется при изменениях workflow, Builder spec/config/docs/tests или AI delivery infrastructure plan.
- [ ] Integration-related sections in workflow and Builder specs are kept synchronized when shared assumptions change.
- [ ] Если AI workflow / utility adoption становится отдельным рабочим контуром, `/docs/ai-delivery-infrastructure-plan.md` описан как required/optional operational decomposition plan, а не как сама декомпозиция внутри базового ТЗ.
- [ ] `/docs/ai-delivery-infrastructure-plan.md` имеет ожидаемую структуру: dashboard, current position, track status, requirement coverage matrix, checkpoints/items, validation/evidence.
- [ ] Для активных слоёв Workflow / Builder / Integration задано правило coverage: source spec area → delivery item → status → evidence → validation.

## 23. Анти-паттерны

Нельзя:

- держать актуальный scope только в чате;
- оставлять несколько активных ТЗ с разными именами, например `project-spec.md` и `product_spec.md`, без явного obsolete-статуса одного из них;
- держать актуальный backlog только в GitHub Issues;
- требовать connector для понимания текущего состояния проекта;
- отмечать item как Done только потому, что PR смержен;
- менять project scope только в коде без обновления `project-spec.md`;
- оставлять `delivery-plan.md` устаревшим после PR;
- превращать `delivery-plan.md` в подробный лог каждого микрошагa;
- создавать Issues для каждого backlog item без пользы;
- превращать GitHub Issues в Jira-like tracker;
- смешивать active scope, future ideas и removed scope без явных разделов;
- давать Codex широкие задачи без selected delivery item;
- добавлять внешние зависимости без явного требования и обоснования;
- автоматически объединять `/docs/context-bundle-builder/MASTER_SPEC.md` с `/docs/project-spec.md`;
- делать Context Bundle Builder обязательным gate для каждого PR без управленческой необходимости.

## 24. Критерий качества workflow

Workflow работает хорошо, если новая модель может без старого чата ответить на вопросы:

- что сейчас строится;
- что входит в актуальный scope;
- что явно не входит в scope;
- какой sprint / checkpoint активен;
- какие items уже сделаны;
- какой item следующий;
- какой PR закрыл конкретный item;
- где возник blocker;
- какие изменения scope были приняты;
- какие документы нужно учитывать перед следующим prompt;
- когда достаточно прямого чтения docs/diff/tests, а когда нужно запускать Context Bundle Builder;
- где проходит граница между project source of truth и devtool source of truth.

Главный критерий:

```text
Процесс должен снижать потерю контекста, а не создавать новую бюрократию.
```
