# Delivery Plan

## Current Goal — DOCS-WORKFLOW-SPEC-001

**Поручение:** пользователь 2026-09-19 попросил немедленно заменить инструкции, удалить отдельный AI coding workflow и проверить остальные документы; отдельным ответом включил весь продуктовый scope/AC из Google Doc. Это docs-only работа, не полный product/code audit.

**Результат:** один согласованный набор правил, canonical spec полного PsychologyAtlas scope, трассируемый AC registry, findings и roadmap для выбора следующей implementation Goal.

**Scope:** корневые AGENTS/CI-CD rules, README, spec/plan, необходимые правки ссылок/статуса supporting docs, сохранение завершённой истории в существующем архиве.
**Non-goals:** code/content changes, migrations, установка dependencies, workflows/GitHub settings, secrets, deployment, полный аудит готовности и пересчёт процентов.
**Dependencies:** SRC-01 modifiedTime `2026-09-16T11:07:25.174Z`; workflow templates пользователя; подтверждённый GitHub baseline.
**Git:** branch `codex/adopt-repository-workflow`; base SHA `ddc661172b50f549a8e1ef4ef8ff5ab54152ae64`; рабочая папка — root repository, отдельного worktree нет. PR ID до initial push — UNSET; искать по этой head branch.

### DoD и задачи

| Критерий | Состояние checkpoint |
| --- | --- |
| DOC-01: оба новых правила приняты; CI/CD файл только в root; старый workflow удалён | PASS локально: copy/readback и итоговый diff |
| DOC-02: действующие ссылки ведут в существующие документы; нет новых внешних ссылок | PASS локально |
| DOC-03: все разделы SRC-01 покрыты requirements/AC либо явным SPEC gap; optional scope сохранён | PASS: 14 эпиков / 76 AC, source coverage и optional scope проверены |
| DOC-04: статусы, Evidence, findings и следующий scope восстановимы из repository/records | PASS: AC/spec parity, Evidence и registry сверены |
| DOC-05: документация не обещает реализованный target stack; старые IDs/история сохранены | PASS локально |
| DOC-06: local validation, self-review, CI/review gates и merge одного docs PR | PENDING до первичных records |

### Validation Plan

Рабочий каталог всех локальных команд — root repository. Canonical команды — [README](../README.md#быстрый-старт-и-проверки); задача не добавляет постоянный validation framework.

| AC/риск | Проверка / ожидаемый результат | Tool/команда, environment | Этап / обязательность |
| --- | --- | --- | --- |
| DOC-01/02 | Copy comparison с исходными файлами; AGENTS отличается только действующим routing, CI/CD совпадает; удалённые файлы/старые ссылки отсутствуют | Filesystem/readback, локальная docs branch | До PR, REQUIRED |
| DOC-02/03/04 | Relative links/anchors существуют; AC ID уникальны и совпадают spec ↔ plan; весь SRC-01 покрыт; новые external links отсутствуют | Разовая Python диагностика + source review, локальная branch | До PR, REQUIRED |
| DOC-05 | Только Markdown diff; история delivery IDs сохранена; product/runtime/settings не изменены | Git diff, self-review | До PR, REQUIRED |
| DOC-02/05 | `git diff --check`; существующий frontend contract suite с docs-heading check | Canonical README команды; Python 3.12 | До PR, REQUIRED |
| DOC-06 | CI `validate-and-smoke-test` и опубликованные checks текущей PR revision успешны; review по фактическим settings | GitHub CLI/records | После push, REQUIRED для этой docs задачи |
| Runtime regression | Код/dependencies не меняются; API suite не нужна для docs diff | N/A по scope; F-005 сохраняется | Без повторного API запуска |
| Product/browser/source certification | Нужны будущим implementation/content AC, не этому docs PR | Future Goal Validation Plan | N/A для текущей задачи |
| Deployment/stateful operations | Runtime/schema/content не меняются, class NONE | N/A по scope; автоматический CD может запуститься из существующей конфигурации | После merge не инициировать deploy |

## Baseline и Evidence

Проверка состояния — 2026-09-19; code baseline `ddc661172b50f549a8e1ef4ef8ff5ab54152ae64`. На старте local main совпал с свежим origin/main и GitHub, дерево чистое, один worktree, открытых PR нет. Полная оценка проекта по новой спецификации не проводилась; проценты и READY totals — UNSET. 76 — число сформированных AC, не знаменатель выполненного аудита.

| ID | Тип / результат | Источник, revision/environment, время и ограничения |
| --- | --- | --- |
| E-SOURCE | Requirements / PASS | Google Drive SRC-01 полностью прочитан 2026-09-19; file ID/revision timestamp в spec; учебный corpus целиком не проверялся. |
| E-CODE | Inspection / PARTIAL | Git-tracked tree, entrypoints app/main.py и app/miniapp_fastapi_runtime.py, sql/schema.sql, miniapp/index.html, requirements.txt, Docker/CI configs на baseline. Python/FastAPI + SQLite + статический Mini App; React/Vite/PostgreSQL target не реализуется этой задачей. Не полный поведенческий аудит. |
| E-CONTENT | Historical/content inventory / PARTIAL | Предыдущий delivery baseline: 575 approved questions в 8 темах; static glossary/literature. Содержательная сверка с Drive не выполнена. Старые reports — доказательства только своих scope/revision. |
| E-LIT | PR/inspection / PARTIAL | PR #278 (schema), #279 (read API), #280 (write API), #281 (UI) merged; baseline включает эти изменения. Не подтверждает полный новый Reading Tracker scope, audio/status mapping или текущий production UX. |
| E-TEST | Local / PASS и FAIL | 2026-09-19 на baseline: 37 frontend/schema tests PASS, literature validator PASS, diff check PASS. API/FastAPI suite FAIL на import из-за local pydantic-core mismatch; это F-005, не подтверждённый runtime bug. |
| E-GH | Settings/CI / PASS в указанном scope | 2026-09-19: main protected=false, rulesets отсутствуют; Environment production без protection rules/branch policy. CI run 28652240208 на baseline success: compile/content validators/DB init+seed; behavioral suite не запускалась. |
| E-CD | Historical deploy / PARTIAL | production deployment 5297661057 / CD 28652240249, 2026-07-03: checkout обновлён до baseline, build/seed/restart пропущены. Предыдущий CD 28649314034 на bed22836b86d6a644d45d6e4ebf3b25f640fc369 пересоздал bot/API и подтвердил running containers. Текущий health/version на VPS — UNSET. |
| E-STATIC | Build record / PARTIAL | Cloudflare Workers check `psychology-quiz-miniapp` на baseline success 2026-07-03; build ID fac07c7b-d59d-4c3d-9e54-98247d80d9ca. Текущий published asset/runtime smoke не проверен. |
| E-DOCS | Local / PASS | 2026-09-19, docs diff branch codex/adopt-repository-workflow относительно baseline: 27 Markdown documents/link anchors, 76 уникальных AC/spec-plan parity, copy/source coverage review, сохранение 22 delivery IDs и отсутствие новых external links/non-doc changes — PASS. 32 frontend/docs contract tests PASS; git diff --check PASS. Full product audit/API suite не выполнялись; CI/merge до push PENDING. |

## Сохранённый content baseline

Источник: прежний план на code baseline; таблица не является новой source certification или пересчётом quality metrics.

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
| **Total** | 8 active topics | **575** | Current approved JSON question-bank baseline; structurally validated, covered by JSON → SQLite parity and deterministic quality audit tooling, with remaining high-severity length-cue follow-up retained in the compact actionable queue rather than hidden by artificial padding. |

## Roadmap и зависимости

Приоритет отражает SRC-01, не разрешение на реализацию.

| Порядок | Предлагаемый scope | Зависимости / условие начала |
| --- | --- | --- |
| 0 | Завершить DOCS-WORKFLOW-SPEC-001 | Пользователь уже поручил; docs PR и gates |
| 1 | Выбрать PLATFORM-FOUNDATION-001: account/content/user-state boundaries, migration design, минимальный безопасный срез общего backend | Q-01/Q-02/Q-06/Q-08; baseline tests, F-003/004/005/014 учитывать перед runtime delivery |
| 2 | E04 + adaptive E03: личный прогресс, ошибки, повторение | Identity/content versioning; Q-03 |
| 3 | E02/E06/E07 и E05: source-backed pipeline, knowledge/search и связи | Provenance; минимальная PWA из E01 должна быть доступна для зависимых экранов |
| 4 | E08/E09/E12: задания, полный Reading Tracker, owner dashboard и развитие PWA | E01/E02/E11; Q-04/Q-07 |
| 5 | E10: structured practice export | Source-backed criteria; внешняя модель без обязательного API |
| По отдельному решению | OAuth, RAG/direct API/voice, reader и прочие optional AC | Решение пользователя и соответствующая оценка; не автоматическое продолжение |

## Состояние AC

Статусы относятся к новым формулировкам [spec](project-spec.md), не к старым галочкам delivery. IN_PROGRESS означает имеющийся частичный baseline без полного доказательства нового AC. BACKLOG означает, что работа по новому AC не начата/не подтверждена, а не заключение полного аудита об отсутствии любого прототипа. READY не присваивается по одному старому PR или наличию кода. Optional/future условия определены в spec и сохраняются для соответствующих строк.

| AC | Статус | Evidence / оставшаяся проверка или зависимость |
| --- | --- | --- |
| AC-FND-01 | IN_PROGRESS | E-CODE; platform/data foundation, Q-01/Q-02 |
| AC-FND-02 | IN_PROGRESS | E-CODE; platform/data foundation, Q-01/Q-02 |
| AC-FND-03 | IN_PROGRESS | E-CODE; platform/data foundation, Q-01/Q-02 |
| AC-FND-04 | BACKLOG | E-CODE; platform/data foundation, Q-01/Q-02 |
| AC-FND-05 | BACKLOG | E-CODE; platform/data foundation, Q-01/Q-02 |
| AC-FND-06 | IN_PROGRESS | E-CODE; platform/data foundation, Q-01/Q-02 |
| AC-FND-07 | IN_PROGRESS | E-CODE; platform/data foundation, Q-01/Q-02 |
| AC-FND-08 | IN_PROGRESS | E-CODE; platform/data foundation, Q-01/Q-02 |
| AC-FND-09 | BACKLOG | E-CODE; platform/data foundation, Q-01/Q-02 |
| AC-FND-10 | IN_PROGRESS | E-CODE; platform/data foundation, Q-01/Q-02 |
| AC-SRC-01 | BACKLOG | E-CONTENT; source inventory/provenance по SRC-01 |
| AC-SRC-02 | IN_PROGRESS | E-CONTENT; source inventory/provenance по SRC-01 |
| AC-SRC-03 | BACKLOG | E-CONTENT; source inventory/provenance по SRC-01 |
| AC-SRC-04 | IN_PROGRESS | E-CONTENT; source inventory/provenance по SRC-01 |
| AC-SRC-05 | BACKLOG | E-CONTENT; source inventory/provenance по SRC-01 |
| AC-SRC-06 | IN_PROGRESS | E-CONTENT; source inventory/provenance по SRC-01 |
| AC-SRC-07 | IN_PROGRESS | E-CONTENT; source inventory/provenance по SRC-01 |
| AC-SRC-08 | IN_PROGRESS | E-CONTENT; source inventory/provenance по SRC-01 |
| AC-QUIZ-01 | IN_PROGRESS | E-CODE/E-CONTENT; source-backed и behavioral validation |
| AC-QUIZ-02 | IN_PROGRESS | E-CODE/E-CONTENT; source-backed и behavioral validation |
| AC-QUIZ-03 | BACKLOG | E-CODE/E-CONTENT; source-backed и behavioral validation |
| AC-QUIZ-04 | IN_PROGRESS | E-CODE/E-CONTENT; source-backed и behavioral validation |
| AC-QUIZ-05 | IN_PROGRESS | E-CODE/E-CONTENT; source-backed и behavioral validation |
| AC-QUIZ-06 | IN_PROGRESS | E-CODE/E-CONTENT; source-backed и behavioral validation |
| AC-QUIZ-07 | IN_PROGRESS | E-CODE/E-CONTENT; source-backed и behavioral validation |
| AC-PROG-01 | BACKLOG | E-CODE; versioning/history policy Q-02/Q-03 |
| AC-PROG-02 | BACKLOG | E-CODE; versioning/history policy Q-02/Q-03 |
| AC-PROG-03 | BACKLOG | E-CODE; versioning/history policy Q-02/Q-03 |
| AC-PROG-04 | IN_PROGRESS | E-CODE; versioning/history policy Q-02/Q-03 |
| AC-PROG-05 | BACKLOG | E-CODE; versioning/history policy Q-02/Q-03 |
| AC-PROG-06 | BACKLOG | E-CODE; versioning/history policy Q-02/Q-03 |
| AC-GLO-01 | IN_PROGRESS | E-CODE/E-CONTENT; glossary и связи с E04/E06 |
| AC-GLO-02 | BACKLOG | E-CODE/E-CONTENT; glossary и связи с E04/E06 |
| AC-GLO-03 | BACKLOG | E-CODE/E-CONTENT; glossary и связи с E04/E06 |
| AC-KNW-01 | BACKLOG | E-CODE; knowledge/export implementation scope |
| AC-KNW-02 | BACKLOG | E-CODE; knowledge/export implementation scope |
| AC-KNW-03 | BACKLOG | E-CODE; knowledge/export implementation scope |
| AC-KNW-04 | BACKLOG | E-CODE; knowledge/export implementation scope |
| AC-KNW-05 | BACKLOG | E-CODE; knowledge/export implementation scope |
| AC-SRH-01 | BACKLOG | E-CODE; retrieval; optional RAG только по Q-05 |
| AC-SRH-02 | BACKLOG | E-CODE; retrieval; optional RAG только по Q-05 |
| AC-SRH-03 | BACKLOG | E-CODE; retrieval; optional RAG только по Q-05 |
| AC-SRH-04 | BACKLOG | E-CODE; retrieval; optional RAG только по Q-05 |
| AC-SRH-05 | BACKLOG | E-CODE; retrieval; optional RAG только по Q-05 |
| AC-HWK-01 | BACKLOG | E-CODE; assignments contour и E11 |
| AC-HWK-02 | BACKLOG | E-CODE; assignments contour и E11 |
| AC-HWK-03 | BACKLOG | E-CODE; assignments contour и E11 |
| AC-LIT-01 | IN_PROGRESS | E-LIT; полный catalogue/state scope, Q-04 |
| AC-LIT-02 | BLOCKED | E-LIT: legacy API есть; Q-04 mapping и F-005 мешают закрытию нового AC |
| AC-LIT-03 | IN_PROGRESS | E-LIT; полный catalogue/state scope, Q-04 |
| AC-LIT-04 | IN_PROGRESS | E-LIT; полный catalogue/state scope, Q-04 |
| AC-LIT-05 | BACKLOG | E-LIT; полный catalogue/state scope, Q-04 |
| AC-PRC-01 | BACKLOG | E-CODE; structured export первым срезом |
| AC-PRC-02 | BACKLOG | E-CODE; structured export первым срезом |
| AC-PRC-03 | BACKLOG | E-CODE; structured export первым срезом |
| AC-PRC-04 | BACKLOG | E-CODE; structured export первым срезом |
| AC-PRC-05 | BACKLOG | E-CODE; structured export первым срезом |
| AC-AUTH-01 | BACKLOG | E-CODE; account/access решения Q-01/Q-06 |
| AC-AUTH-02 | BACKLOG | E-CODE; account/access решения Q-01/Q-06 |
| AC-AUTH-03 | IN_PROGRESS | E-CODE; account/access решения Q-01/Q-06 |
| AC-AUTH-04 | BACKLOG | E-CODE; account/access решения Q-01/Q-06 |
| AC-AUTH-05 | BACKLOG | E-CODE; account/access решения Q-01/Q-06 |
| AC-OWN-01 | BACKLOG | E-CODE; owner inventory/coverage, Q-07 |
| AC-OWN-02 | BACKLOG | E-CODE; owner inventory/coverage, Q-07 |
| AC-OWN-03 | BACKLOG | E-CODE; owner inventory/coverage, Q-07 |
| AC-OPS-01 | IN_PROGRESS | E-GH/E-CD; delivery/recovery gaps F-003/F-006/F-014 |
| AC-OPS-02 | IN_PROGRESS | E-GH/E-CD; delivery/recovery gaps F-003/F-006/F-014 |
| AC-OPS-03 | IN_PROGRESS | E-GH/E-CD; delivery/recovery gaps F-003/F-006/F-014 |
| AC-OPS-04 | IN_PROGRESS | E-GH/E-CD; delivery/recovery gaps F-003/F-006/F-014 |
| AC-OPS-05 | IN_PROGRESS | E-GH/E-CD; delivery/recovery gaps F-003/F-006/F-014 |
| AC-LEG-01 | IN_PROGRESS | E-CODE/E-TEST; legacy behavioral suite, F-005 |
| AC-LEG-02 | IN_PROGRESS | E-CODE/E-TEST; legacy behavioral suite, F-005 |
| AC-LEG-03 | IN_PROGRESS | E-CODE/E-TEST; legacy behavioral suite, F-005 |
| AC-LEG-04 | IN_PROGRESS | E-CODE/E-TEST; legacy behavioral suite, F-005 |
| AC-LEG-05 | IN_PROGRESS | E-CODE/E-TEST; legacy behavioral suite, F-005 |
| AC-LEG-06 | IN_PROGRESS | E-CODE/E-TEST; legacy behavioral suite, F-005 |

## Реестр findings и blockers

Реестр сохраняет все findings текущего RESUME и этой документационной сверки, включая унаследованные незакрытые content items. Старые полные отчёты не переаудированы: неизвестное исправление не считается закрытием. Приоритеты ниже — порядок рассмотрения, не автоматическое разрешение FIX.

| ID / состояние | Область и проблема | Evidence / влияние / приоритет / confidence | Действие, основание и зависимости |
| --- | --- | --- | --- |
| F-001 / исправляется текущим PR | Spec расходился с SRC-01: Telegram-only, запрет PWA, SQLite, запрет RAG, нет полных AC | E-SOURCE + base spec; неверный scope; P1; HIGH | DOCUMENT: E01–E14, decisions D-01–07; закрыть после source/AC review и merge |
| F-002 / исправляется текущим PR | Старый router/workflow, duplicate CI rules, нет Goal/AC/Evidence checkpoint | Base docs, новый template; невосстановимый процесс; P1; HIGH | CONSOLIDATE: root rules + этот план; удалить старый workflow, заменить ссылки; merge gate |
| F-003 / OPEN | CD стартует независимо от CI; main/rulesets/production protections не обеспечивают новые gates | E-GH, .github/workflows/deploy-production.yml; CD #281 завершился раньше CI; P1; HIGH | FIX в отдельной pipeline Goal: revision/gate/protection model до runtime delivery; настройки не менять этой задачей |
| F-004 / OPEN | CI не запускает имеющуюся unit/integration suite | E-GH, .github/workflows/ci.yml; green CI не подтверждает behavioral AC; P2; HIGH | FIX: risk-based suite selection в отдельной pipeline Goal |
| F-005 / OPEN | Local Python не соответствует requirements; pydantic-core 2.49.0 против требуемого 2.46.5, FastAPI 0.141.1 вместо 0.115.12 | E-TEST 2026-09-19; API validation blocked; P2; HIGH | FIX изолированное окружение по requirements в следующей code/validation Goal; глобальные packages сейчас не менять |
| F-006 / OPEN | Свежая production версия, health/business smoke и доступ к VPS не установлены | E-CD/E-STATIC только 03.07; нынешнее состояние UNSET; P2; HIGH | DOCUMENT/VERIFY в применимом runtime scope; нужен проверенный target/access, не повторный deploy ради статуса |
| F-007 / OPEN | Source certification банка/glossary не завершена; repository-derived evidence не заменяет Drive ID/revision и содержательную сверку | E-CONTENT, source-alignment/content/glossary reports; AC-SRC-04/QUIZ-06; P1; HIGH | IMPLEMENT source-backed inventory/review; зависит от Drive corpus и revision mapping |
| F-008 / OPEN | 21 high-severity length-cue item в исторической quality queue; distractor plausibility требует source review | question_bank_quality_calibration.md и JSON queue; учебное качество; P2; MEDIUM: метрики не пересчитаны | FIX содержательно в отдельной content Goal, без padding ради метрики; E02/E03 |
| F-009 / DEFER | Старые audit/RFC/adoption документы могли выглядеть текущими правилами/roadmap; подробные reports уже находились в repository | Inventory ниже; риск stale authority; P2; HIGH | DOCUMENT boundaries сейчас; CONSOLIDATE/архивировать подробные reports отдельно после проверки их незакрытых findings; новые полные audit reports не добавлять |
| F-010 / OPEN | Q-01–Q-08: часть account, algorithms, source/version, литература и recovery решений отсутствует | Spec questions; зависимые AC нельзя закрыть предположением; P1; HIGH | DOCUMENT решения в соответствующих Goals; не блокирует независимую работу |
| F-011 / DEFER | Legacy m1-q3 нестандартен, но stable; experimental difficulty/onboarding и дальнейшие Module 3 batches — необязательные follow-ups | Старый план и content_audit_all_topics.md; P3; HIGH для сохранённого решения | DEFER: не переименовывать ID без downstream check; новые batches только по выбранному scope/source review |
| F-012 / OPEN | Literature metadata seeded только по доступным Module 1 спискам; review metadata требует библиографической проверки | literature_source_inventory.md; E09 не завершён; P2; HIGH | IMPLEMENT corpus-wide inventory, human verification; Q-04 |
| F-013 / OPEN | Historical runner audit содержит собственные findings, их полное закрытие не сверено | audits/2026-05-24-miniapp-runner-audit.md; P2; MEDIUM | DOCUMENT/VERIFY при полном аудите или relevant Goal; отсутствие нового упоминания не закрывает старые IDs |
| F-014 / OPEN | CD следует mutable origin/main, post-check в основном running containers; workflow bootstrap содержит reset --hard/remove-orphans; artifact/restore guarantees не подтверждены | deploy.sh + deploy-production.yml + E-CD; AC-OPS-02–04; P1; HIGH для config, runtime applicability PARTIAL | FIX/CONSOLIDATE в pipeline/recovery Goal по новым ci-cd-rules; не использовать bootstrap как разрешённую routine процедуру |
| F-015 / OPEN | Неполная reproducibility: pip requirements без transitive lock; Actions закреплены tags, CD permissions не заданы явно | requirements.txt и workflows baseline; supply-chain gap; P2; HIGH | FIX по ci-cd-rules в отдельной tooling/pipeline Goal, не обновлять dependencies попутно |

### Карта остальных документов и консолидация

Canonical destinations: требования → spec, состояние/решения о работах → этот план, workflow → AGENTS, CI setup policy → root ci-cd-rules. Existing operational commands остаются в scripts/runbooks.

| Документы | Решение и затронутые упоминания |
| --- | --- |
| README, AGENTS, spec, plan | Обновить routing/scope; README различает actual stack и target stack; status только здесь |
| Старые workflow и CI rules в docs | Удалить; README/adoption/router направить к root файлам |
| ai-delivery-infrastructure-plan.md | Сохранить как компактный adoption/provenance record, убрать второй активный plan |
| delivery-plan-archive.md | Сохранить; перенести завершённый dashboard с baseline provenance и прежними delivery IDs; README/plan ссылки сохраняются |
| miniapp-deployment-qa.md, question_bank_content_rollout.md | Сохранить действующие операции; добавить проверенный delivery snapshot и явную границу historical/target; исправить chooser до трёх контуров |
| miniapp-quiz-runner-design.md, miniapp_setup_hydration.md | Сохранить historical design и актуальный hydration contract; не выдавать за target architecture |
| literature_runtime_rfc.md, glossary_literature_contours_rfc.md, topic_registry_schema_phase1.md, proposals/refactor-plan-miniapp-bot.md | Сохранить supporting proposals с ограничением authority; старые next phases не активируют scope; у литературы уточнить implemented phases B–E |
| literature_source_inventory.md | Сохранить source IDs/ограничения; исправить future-only статус runtime |
| content_audit_all_topics.md, content_audit_fiziologiya_cheloveka.md, content_audit_module2.md, content_source_alignment_module2_qualitative.md | Сохранить как прежнее source/quality Evidence, не как разрешение публикации новых материалов; F-007/008/011 остаются |
| glossary_content_audit.md, glossary_coverage.md, glossary_global_quality_alignment.md, glossary_distractor_engine.md | Сохранить evidence/engine detail; прежняя repository-evidence certification не закрывает новый provenance AC |
| question_bank_quality_and_db_parity.md, question_bank_quality_calibration.md | Сохранить parity/quality tooling и unresolved queue; не пересчитывать метрики в docs задаче |
| audits/2026-05-24-miniapp-runner-audit.md и существующие audit JSON | Сохранить historical evidence/IDs; отдельная консолидация F-009/F-013 без массового удаления и потери незакрытых obligations |

## Checkpoint и следующий шаг

- Current Goal: local docs scope и self-review выполнены; initial push/PR, checks и merge ещё PENDING. Неизвестные product/runtime результаты не объявлены READY.
- DOC-01–05 validation завершена (E-DOCS). После initial push дождаться checks текущей revision, подтвердить merge по primary records. Эти gates не предсказываются локальным PASS.
- После merge: синхронизировать main, проверить свой diff/branch и безопасно удалить только созданную ветку; production deployment для docs scope N/A.
- Следующая implementation Goal ещё не выбрана. Предложение PLATFORM-FOUNDATION-001 требует отдельного поручения и согласования зависимых решений.
- Старый recommendation «следующий glossary polish/optional frontend split» не имеет приоритета над SRC-01. Content replacement с unfinished sessions по-прежнему требует [явной процедуры](question_bank_content_rollout.md); glossary/source review не считается выполненным.
