# Delivery Plan

## Current Goal — PLATFORM-STABILIZATION-001

**Поручение:** пользователь 2026-09-19 одобрил предложенную stabilization Goal и отдельно подтвердил приоритет перехода на PWA. Goal активирована встроенным инструментом. Результат — безопасный существующий quiz/backend как основа общего PWA backend; расширение Telegram-only UX не входит в работу.

**Scope:** F-016/017/019/020/021/028; необходимые test discovery/Windows fixtures (F-022), behavioral CI и минимальные delivery preconditions (затронутая часть F-003/004/014). Область AC: QUIZ-01/02/07, GLO-01, LEG-03, OPS-02/03/05, части FND-06/07 и PROG-04. Целые platform/progress epics и все OPS AC не считаются автоматически завершёнными.

**Non-goals:** PWA/React и PostgreSQL migration, accounts, repetition/knowledge/search, новые учебные контуры, массовая правка content, полное persistence глоссария F-018, dependency/security modernization всего проекта и broad refactor. После Goal остановиться; следующий приоритет для выбора — PWA/platform foundation.

**Baseline:** `df383200fd0e6c389038f5b080ec23310a26be07`, fresh origin/main 2026-09-19. Main чистый, один worktree, open PR нет. Первый PR branch `codex/stabilization-delivery-foundation`, base тот же SHA; PR ID до push UNSET. Audit PR #283 merged; последняя аудиторская готовность ниже остаётся snapshot c914793 и не пересчитывается.

### Решения и порядок PR

- История: фиксировать неизменяемую редакцию вопроса/вариантов при включении в попытку; хранение независимо от Telegram-клиента. Существующие попытки backfill только доступным содержимым, без выдумывания утраченных редакций; migration additive/idempotent, оригинальные answers/score/user data сохраняются. Детальный контракт закрепить в spec перед соответствующим PR (Q-02).
- Lifecycle: non-approved/removed derivative исключается из новых selections, прежняя attempt revision остаётся читаемой. Physical delete user/history rows не нужен.
- Recovery: перед stateful changes согласованный pipeline создаёт SQLite backup и проверяет восстановление в отдельный временный файл. Production restore/volume cleanup не выполняются автоматически. При post-check failure остановка и forward-fix в scope; rollback только после доказательства совместимости.
- Delivery: существующий trusted VPS target из Repository Secrets + pinned host verification; exact validated main SHA, allowlisted directory/services, build before init/seed, runtime image/source identity, internal health и read-only business smoke. Никакого bootstrap/reset --hard/remove-orphans; неизвестный или изменившийся target останавливает поставку.
- GitHub-wide approval/access policy не изменять попутно. Настроить необходимый CI→CD gate в workflows; оставшиеся protections/supply-chain gaps сохранять findings.

| PR / связная задача | DoD / результат | Состояние |
| --- | --- | --- |
| 1. Validation/delivery foundation | Canonical pytest обнаруживает все tests; Windows fixtures и explicit DB closing исправлены; behavioral CI, exact revision delivery/build-before-migration, verified backup/recovery precheck, image/version/health/readonly smoke; targeted procedures обновлены | IN_PROGRESS, branch выше |
| 2. API input/privacy/destination | F-020/021/028 закрыты regression tests; 4xx без state mutation, отсутствие raw user IDs/initData в logs и невозможность отправки auth на arbitrary origin; совместимые clients | BACKLOG |
| 3. Glossary retry | F-019: stable step/options, answer/next idempotency и concurrent/retry tests; legacy compatibility; без нового durable learning subsystem | BACKLOG |
| 4. Content history/publication | F-016/017: immutable attempt content + safe backfill/lifecycle sync, retired-serving gate, regression/migration/preservation tests и stateful delivery | BACKLOG |

Каждый следующий PR — после merge/applicable delivery предыдущего и fresh main. Разбиение может уточняться по связанности без расширения согласованного scope.

### Validation Plan

Рабочий каталог — root repository. Canonical commands — [README](../README.md#быстрый-старт-и-проверки); environment — isolated Python 3.12 и отдельная test SQLite. Production credentials/user data в fixtures не используются.

| AC/риск | Проверка / ожидаемый результат | Tool/команда и environment | Этап / обязательность |
| --- | --- | --- | --- |
| F-022 / baseline | Existing suite обнаруживает unittest и pytest functions, переносимые SQLite fixtures; no skipped required behavior | Canonical pytest из README, Windows локально + Linux CI; Docker contract check в CI | PR1 local/CI, REQUIRED |
| Delivery revision/trust/failure | Success gate только trusted main CI; stale/unknown revision не доставляется; script не меняет чужой worktree/config; image build перед seed, failure останавливает flow | Unit/contract + shell syntax и fake-command deployment scenarios; GitHub records на merge | PR1 local/CI + применимый CD, REQUIRED |
| Stateful recovery | SQLite backup/restore в отдельный файл, integrity/FK и user-state invariants; original file не меняется; failure не запускает migrations | Automated temporary DB tests; candidate image preflight на проверенном VPS target | Перед stateful delivery, REQUIRED |
| F-020/021/028 | Invalid types/enums/IDs → 4xx без session changes; privacy negative tests; arbitrary URL не получает initData | API tests + pure frontend configuration/behavior checks и relevant browser smoke | PR2 local/CI; unsafe production cases N/A, REQUIRED synthetic coverage |
| F-019 | Duplicate/concurrent answer/next/retry сохраняют options/score и owner isolation | Glossary domain/API tests, controlled network/retry fixtures | PR3 local/CI, REQUIRED |
| F-016/017 | Content edits/demotion/remove/seed retry сохраняют original attempt semantics и users/literature; inactive content не попадает в новые attempts | DB/API/migration/parity fixtures; validators/init/seed | PR4 local/CI и stateful post-check, REQUIRED |
| Compatible legacy/UI | Выбранные handler/API/frontend contracts, readable feedback/setup/answer; expanded core при общем DB/config impact | Existing suites; browser при изменении UI/network flow | Каждый PR по impact, REQUIRED |
| Docs/diff | Links, stable AC/finding IDs, scope и git diff --check; readiness snapshot неизменен | Git/readback + docs validation | Перед каждым push, REQUIRED |
| Delivery completion | Required checks/reviews текущей revision, merge; exact version/image, internal health, read-only business smoke и applicable migration records | GitHub CI/CD + deployed service probes | Каждый runtime PR, REQUIRED; недоступность не N/A |

Не вводить load/E2E infrastructure целиком; конкретные regression и safety gates обязательны. Не повторять полный suite без нового влияющего изменения/failure. Findings outside scope сохраняются.

## Аудиторский baseline и готовность

Полный аудит: **2026-09-19**, проверенный `origin/main = c914793946c25de78ac5d966969663639cc61b90`. GitHub/source metadata и диагностика проверены примерно 12:46–13:10 UTC; точные primary record timestamps сохранены в Evidence. Это snapshot кода, не обещание текущего LIVE состояния.

**Обязательный согласованный scope: 6 READY / 67 AC = 9,0%.** Полный каталог с девятью условными AC: **6 / 76 = 7,9%**. Условные AC перечислены в [spec](project-spec.md#граница-обязательного-и-условного-scope), сохранены в registry и не активируют implementation. Нулевой процент эпика означает отсутствие полностью доказанного AC, а не отсутствие полезного кода.

Mandatory statuses: **6 READY, 28 IN_PROGRESS, 32 BACKLOG, 1 BLOCKED**. Каталог: **6 READY, 29 IN_PROGRESS, 40 BACKLOG, 1 BLOCKED**. Partial progress не получает дробного веса. Technical AC учитываются наравне с product AC; проценты эпиков не усредняются.

Предыдущей сопоставимой AC-based аудиторской оценки нет: RESUME и PR #282 явно оставляли readiness UNSET. Исторические «completed/ready» относятся к узким Telegram delivery items, не ко всему сентябрьскому PsychologyAtlas scope. Падение/рост в процентных пунктах относительно них вычислять нельзя.

| Эпик | READY / mandatory AC | Готовность | Conditional AC вне primary denominator |
| --- | ---: | ---: | ---: |
| E01 — Platform/data и клиенты | 0 / 10 | 0,0% | 0 |
| E02 — Sources/provenance | 1 / 8 | 12,5% | 0 |
| E03 — Quiz и качество | 0 / 7 | 0,0% | 0 |
| E04 — Повторение/прогресс | 0 / 5 | 0,0% | 1 |
| E05 — Глоссарий | 0 / 2 | 0,0% | 1 |
| E06 — Knowledge/Obsidian | 0 / 5 | 0,0% | 0 |
| E07 — Поиск/optional RAG | 0 / 2 | 0,0% | 3 |
| E08 — Задания | 0 / 3 | 0,0% | 0 |
| E09 — Литература | 0 / 3 | 0,0% | 2 |
| E10 — Практика | 0 / 4 | 0,0% | 1 |
| E11 — Аккаунты/права | 0 / 4 | 0,0% | 1 |
| E12 — Owner dashboard | 0 / 3 | 0,0% | 0 |
| E13 — Deployment/security/recovery | 0 / 5 | 0,0% | 0 |
| E14 — Telegram compatibility | 5 / 6 | 83,3% | 0 |

## Evidence

Все локальные поведенческие данные ниже — на baseline, неизменённые code/content. Диагностические scripts/logs/SQLite/venv находятся вне repo; в план включены результаты и воспроизводимые сценарии, не raw logs.

| ID | Результат | Источник/revision/environment и ограничения |
| --- | --- | --- |
| E-SOURCE | PASS/PARTIAL | SRC-01 полностью прочитан ранее 19.09, modifiedTime повторно подтверждён `2026-09-16T11:07:25.174Z`. Drive search/list подтвердил root ID из spec и 8 непосредственных folders (выдача 8 при лимите 100, next page не возвращена); содержимое всех вложенных sources не проверялось. |
| E-CODE | PASS inspection | Все tracked app/scripts/tests/SQL/manifests/workflows и doc inventory; Python bot/FastAPI/SQLite + static HTML; target subsystems сопоставлены с AC. Нет vendored tree или hidden implemented PWA в tracked files. Dynamic wiring/entrypoints учтены. |
| E-TEST | PARTIAL | Python 3.12 isolated venv с requirements + audit-only pytest: **264 passed, 16 failed, 1 skipped, 24 subtests passed**, 14,33s. 14 teardown WinError32 (SQLite handles), 2 NamedTemporaryFile reopen failures. Docker CLI отсутствует — 1 compose test skipped. Global dependency mismatch не повторяется в venv. |
| E-FIXTURE | PASS diagnostic / ограниченно | Только 16 failed tests повторены с внешней Windows fixture adaptation: GC перед teardown и closed temporary file; **16/16 PASS**, assertions и product code не менялись. Synthetic /stats matrix: non-owner private/group owner не читают DB, private owner читает. Это не green исходного suite и не Linux/container test. |
| E-CONTENT | PASS structural / PARTIAL semantic | Compileall, questions/topics/glossary/literature validators, fresh DB init/seed, question-bank parity PASS; 575 approved questions/8 topics, 99 approved glossary entries/8 files, 42 review literature entries/4 непустых из 5 files. Fresh DB integrity/FK/parity clean. Quality: 487 uniquely-longest-correct, 21 severe cues. Full source certification отсутствует. |
| E-REPRO | FAIL behavior | Synthetic SQLite/API: mutable content меняет historic option semantics; approved→draft не снимает DB approval; glossary duplicate next меняет correct index и score; malformed payload → 500 / bool category → 200; raw synthetic Telegram ID попадает в logger. Positive quiz setup matrix single/mix/all × 5/10/15/all — 12 PASS. Чужие/неаутентифицированные API requests в suite отклоняются. |
| E-DEPS | FAIL advisory scan / PARTIAL reachability | pip-audit по requirements: 16 выдаваемых записей, **8 unique advisory IDs** в python-dotenv 1.0.1 и Starlette 0.46.2. Primary upstream advisories просмотрены; duplicate records не посчитаны как отдельные уязвимости. Runtime exploitability не доказана; F-023. |
| E-GH | PASS observation | GitHub CLI Just9120, admin; PR #282 merged. Main protected=false, rulesets=[]; один Environment production без protection/branch rules. Default workflow permission read, approve-PR=false. CI baseline 35443743110 success; PR CI 35443715500 success. Первые 20 recent runs просмотрены (не вся история), attempts=1 в выборке. |
| E-CD | PARTIAL | CD 35443743123/job 105899008788 success: checkout c914793, build/seed/restart=0; это docs sync. Последний проверенный runtime restart: CD 28649314034/job 84963244875, bed2283, 03.07, Running обеих служб. Нет доказанного current image digest/version или restore rehearsal. |
| E-HTTP | PASS/PARTIAL | 19.09: published Mini App HTTP 200 и text совпадает с baseline (SHA256 bytes `32fef6fb0b809844f74e579a61d554fb5a8ee29241ba4d791452e79250457896`); API /miniapp/state без initData → 401; public /healthz → Nginx 404. IAB без Telegram показывает понятное требование /ui, console errors/warnings не замечены. Authenticated/mobile Telegram E2E, backend SHA и internal health не подтверждены. |
| E-STAB-01 | PASS local / delivery PENDING | PR1 worktree от df38320: 303 passed, 1 skipped (Docker отсутствует), 24 subtests passed; behavior tests включают 12 real-shell/fake-boundary deployment paths, exact CI selection, SQLite backup/isolated restore/preservation. 71 affected legacy tests PASS. Эти результаты не подтверждают VPS до post-merge CD. |
| E-DOCS | PASS local | Итоговый spec/plan diff: 76 unique AC/spec-plan parity, 67+9 scope split, 28 unique findings, counts/readiness, relative links/anchors и whitespace PASS; только два разрешённых Markdown files. Source/READY/findings self-review выполнен. CI/merge определять по PR head branch и primary records, не по будущему обещанию в snapshot. |

### Окружения и delivery facts

| Поверхность | Установлено / UNSET / N/A |
| --- | --- |
| Local diagnostic runtime | Windows/Python 3.12/isolated venv, synthetic SQLite; Docker отсутствует, WSL не установлен. Не GitHub Environment. |
| CI | PR main, push main, manual; ubuntu-latest/Python 3.12; contents:read; concurrency workflow/ref с cancel. PR checkout default merge ref; head_sha записи run отличать от фактического test-merge tree. Required GitHub checks/reviews не настроены; published checks ожидаются по AGENTS. |
| production Environment | CD Deploy production job; SSH к VPS checkout /opt/psychology-quiz, services psych_quiz_bot + psych_quiz_miniapp_api. Host/user values и compose project/config owner UNSET, secrets не извлекались. Нет environment protections. |
| Application production | Compose loopback ports и ./data bind; source content read-only mount; .env + explicit Compose overrides. Известны имена secrets/vars из procedures, не их values. API через Nginx; фактические firewall/internal health/image UNSET. |
| Static deployment | Отдельный Cloudflare Worker psychology-quiz-miniapp, assets ./miniapp, current published HTML подтверждён. Это deployment unit, отдельный GitHub Environment не обнаружен. |
| Product variants | Classic, Mini App и будущая PWA — клиенты; не три автоматически существующих environments. PWA deployment N/A пока клиент не реализован. |
| Queue/artifact/stateful | CD push/manual, concurrency без cancel, mutable main + local flock; immutable artifact/checked migration revision/recovery не доказаны (F-014). Backup/restore policy UNSET, не N/A. |
| Длительность/стоимость | Baseline CI job 11s, CD job 13s; PR CI workflow ~19s. PR+main CI повторяют validators/install, docs push запускает CD. Billing/остаток minutes UNSET; выборка недостаточна для бюджета/latency SLO. Speculative reruns не запускались. |

## Состояние AC

READY относится к выполненному критерию на baseline. E-FIXTURE подтверждает behavior с явно описанным ограничением; raw suite failures сохранены. Для BLOCKED указывается конкретное решение. Conditional scope помечен отдельно и не превращается в обязательный из-за наличия строки.

| AC | Статус | Scope | Evidence / оставшаяся работа |
| --- | --- | --- | --- |
| AC-FND-01 | IN_PROGRESS | MANDATORY | Topic registry, 8 категорий и module metadata есть; source/lesson graph и навигация всей платформы отсутствуют (F-026). |
| AC-FND-02 | IN_PROGRESS | MANDATORY | SQLite отделяет quiz/literature state по user_id; repetitions, bookmarks, assignments и platform identity отсутствуют (F-026). |
| AC-FND-03 | IN_PROGRESS | MANDATORY | FastAPI, Python bot и analytics существуют; общего backend для целевых контуров ещё нет (E-CODE, F-026). |
| AC-FND-04 | BACKLOG | MANDATORY | Нет React/TypeScript/Vite manifests/build и общего PWA клиента; E-CODE, F-026. |
| AC-FND-05 | BACKLOG | MANDATORY | Runtime — SQLite; PostgreSQL migration/recovery fixtures отсутствуют; Q-02, F-026. |
| AC-FND-06 | IN_PROGRESS | MANDATORY | Seed не меняет Drive, но mutable questions и user answers связаны без версий; E-REPRO, F-016/017. |
| AC-FND-07 | IN_PROGRESS | MANDATORY | Quiz duplicate guard/API feedback проверены; glossary не имеет idempotent step/answer recovery; F-019, E-TEST. |
| AC-FND-08 | IN_PROGRESS | MANDATORY | Quiz/literature сохраняются в SQLite; glossary state теряется при restart и не разделяется между процессами; F-018. |
| AC-FND-09 | BACKLOG | MANDATORY | Нет независимого PWA; опубликованная статика без Telegram показывает инструкцию /ui; E-HTTP, F-026. |
| AC-FND-10 | IN_PROGRESS | MANDATORY | Bot/Mini App используют quiz DB; PWA и общее состояние всех контуров отсутствуют; F-026. |
| AC-SRC-01 | BACKLOG | MANDATORY | Корень Drive установлен, 8 непосредственных подпапок; recursive ingestion/inventory pipeline отсутствует; E-SOURCE, F-007. |
| AC-SRC-02 | IN_PROGRESS | MANDATORY | Module/topic поля и source_ref есть; форматы одного занятия не связаны lesson metadata; F-007/026. |
| AC-SRC-03 | BACKLOG | MANDATORY | Нет ledger Drive file ID + processed revision и incremental processing tests; F-007/026. |
| AC-SRC-04 | IN_PROGRESS | MANDATORY | 575 questions/99 glossary approved не имеют проверенного per-item Drive revision mapping; validator этого не требует; F-007. |
| AC-SRC-05 | BACKLOG | MANDATORY | Автоматизированного source conflict/review состояния нет; source review полного corpus не выполнен; F-007/026. |
| AC-SRC-06 | IN_PROGRESS | MANDATORY | Литература содержит metadata, но происхождение всего учебного derivative не сертифицировано; F-007/012. |
| AC-SRC-07 | IN_PROGRESS | MANDATORY | Публикация через repository/approved seed есть; полного source review/publication trail нет, demotion не синхронизируется; F-017. |
| AC-SRC-08 | READY | MANDATORY | Нет runtime LLM/editor routes; entrypoints/dependencies и seed filtering/parity tests PASS (E-CODE/E-TEST/E-CONTENT). Ошибка снятия approval отдельно нарушает SRC-07/QUIZ-01. |
| AC-QUIZ-01 | IN_PROGRESS | MANDATORY | Категории из backend, выборка status=approved; демотированный JSON остаётся approved в DB; E-REPRO, F-017. |
| AC-QUIZ-02 | IN_PROGRESS | MANDATORY | 12 положительных setup комбинаций PASS; invalid/empty category → 400, но boolean ID принимается, list payload → 500; E-REPRO, F-020. |
| AC-QUIZ-03 | BACKLOG | MANDATORY | Random выборка есть; history-aware adaptive sampling не реализован; Q-03, F-026. |
| AC-QUIZ-04 | IN_PROGRESS | MANDATORY | Difficulty metadata/any есть; текущий classic требует отдельный шаг, целевой необязательный UX и late calibration ещё не согласованы/проверены; Q-03. |
| AC-QUIZ-05 | IN_PROGRESS | MANDATORY | Feedback/explanation и duplicate recovery проходят API tests; links knowledge/source отсутствуют; F-026. |
| AC-QUIZ-06 | IN_PROGRESS | MANDATORY | Structural/quality audit PASS; 21 сильный length cue, полного source-backed review нет; E-CONTENT, F-007/008. |
| AC-QUIZ-07 | IN_PROGRESS | MANDATORY | Legacy 575 вопросов сохранены и fresh DB parity PASS; исправление options меняет смысл старых ответов; F-016. |
| AC-PROG-01 | BACKLOG | MANDATORY | Нет persisted schedule/due-list для questions и terms; Q-03, F-026. |
| AC-PROG-02 | BACKLOG | MANDATORY | Нет API/UI личных ошибок и today queue; F-026. |
| AC-PROG-03 | BACKLOG | MANDATORY | Есть итог quiz и owner aggregates; нет личной истории/weak themes/dynamics/mastery distinction UI; F-026. |
| AC-PROG-04 | IN_PROGRESS | MANDATORY | quiz_answers хранит score flag, но question/options mutable; E-REPRO демонстрирует искажение истории; F-016. |
| AC-PROG-05 | BACKLOG | MANDATORY | Нет подтверждаемого selective learning reset с user-data invariants; F-026. |
| AC-PROG-06 | BACKLOG | CONDITIONAL | Условный scope; mastery policy Q-03 и temporal fixtures отсутствуют. |
| AC-GLO-01 | IN_PROGRESS | MANDATORY | Topic quiz/owner check/feedback есть; повторный next меняет текущую верную позицию, возможна неверная оценка показанного ответа; E-REPRO, F-019. |
| AC-GLO-02 | BACKLOG | MANDATORY | Нет knowledge links и общей persisted repetition history; F-018/026. |
| AC-GLO-03 | BACKLOG | CONDITIONAL | Условный scope; самостоятельных PWA term cards нет. |
| AC-KNW-01 | BACKLOG | MANDATORY | Нет source-backed summaries/atomic-note pipeline и validators; F-007/026. |
| AC-KNW-02 | BACKLOG | MANDATORY | Нет knowledge PWA/API/link graph; E-CODE, F-026. |
| AC-KNW-03 | BACKLOG | MANDATORY | Нет Obsidian Markdown export/link validation; F-026. |
| AC-KNW-04 | BACKLOG | MANDATORY | Нет обновления Vault с сохранением personal files; F-026. |
| AC-KNW-05 | BACKLOG | MANDATORY | Knowledge backend/PWA отсутствуют; независимость действующего bot от Obsidian не закрывает весь AC; F-026. |
| AC-SRH-01 | BACKLOG | MANDATORY | Нет keyword/semantic retrieval API и curated evaluation set; F-026. |
| AC-SRH-02 | BACKLOG | MANDATORY | Нет PostgreSQL/pgvector/index rebuild; F-026. |
| AC-SRH-03 | BACKLOG | CONDITIONAL | Условный architecture decision; иная vector DB не вводилась, но это не выполнение будущего decision AC. |
| AC-SRH-04 | BACKLOG | CONDITIONAL | Условный scope; RAG отсутствует, Q-05. |
| AC-SRH-05 | BACKLOG | CONDITIONAL | Условный scope; evaluation/tokenomics/production inclusion decision отсутствуют, Q-05. |
| AC-HWK-01 | BACKLOG | MANDATORY | Нет отдельного assignments ingestion/API/UI; F-026. |
| AC-HWK-02 | BACKLOG | MANDATORY | Нет per-user assignment state/schema/authorization tests; F-026. |
| AC-HWK-03 | BACKLOG | MANDATORY | Нет assignments/knowledge/source link graph; F-026. |
| AC-LIT-01 | IN_PROGRESS | MANDATORY | 42 review entries, 4 непустых списка Module 1; нет corpus-wide ingestion/dedup; E-CONTENT, F-012. |
| AC-LIT-02 | BLOCKED | MANDATORY | Legacy per-user API/schema/UI и isolation tests PASS; mapping «отложено» ↔ revisit/skipped и target progress требует Q-04. F-005 больше не блокирует tests. |
| AC-LIT-03 | IN_PROGRESS | MANDATORY | Metadata catalog работает; audio format и легальные outbound references не представлены текущим контрактом; F-012/026. |
| AC-LIT-04 | IN_PROGRESS | CONDITIONAL | Условный scope; legacy priority/reading_level есть, taxonomy target не выбрана (Q-04). |
| AC-LIT-05 | BACKLOG | CONDITIONAL | Условный scope; knowledge/author links и reader отсутствуют. |
| AC-PRC-01 | BACKLOG | MANDATORY | Нет case schema с разделением student/client context и corpus criteria; F-026. |
| AC-PRC-02 | BACKLOG | MANDATORY | Нет structured case export; F-026. |
| AC-PRC-03 | BACKLOG | MANDATORY | Нет role package с ограничениями подсказок; F-026. |
| AC-PRC-04 | BACKLOG | MANDATORY | Нет отдельного transcript-analysis package и checks учебной формулировки; F-026. |
| AC-PRC-05 | BACKLOG | CONDITIONAL | Условный scope; direct API/voice не выбраны, Q-05. |
| AC-AUTH-01 | BACKLOG | MANDATORY | Identity только Telegram; e-mail/password account отсутствует; F-026. |
| AC-AUTH-02 | BACKLOG | MANDATORY | Нет verification/recovery mail через Яндекс 360; Q-06, F-026. |
| AC-AUTH-03 | IN_PROGRESS | MANDATORY | /stats и Mini App ownership gates проверены; platform roles/sharing matrix отсутствует; Q-01, F-026. |
| AC-AUTH-04 | BACKLOG | CONDITIONAL | Условный scope; Google OAuth/linking не выбран и не реализован, Q-01. |
| AC-AUTH-05 | BACKLOG | MANDATORY | Нет Telegram ↔ platform identity linking/migration; Q-01/Q-02, F-026. |
| AC-OWN-01 | BACKLOG | MANDATORY | Есть скрытая агрегированная /stats; нет source coverage/pipeline dashboard; F-026. |
| AC-OWN-02 | BACKLOG | MANDATORY | Нет source-to-derivative inventory/gap detection; Q-07, F-026. |
| AC-OWN-03 | BACKLOG | MANDATORY | Нового owner dashboard нет; существующий /stats gate READY только в AC-LEG-04; F-026. |
| AC-OPS-01 | IN_PROGRESS | MANDATORY | Compose binds API на loopback; Nginx API доступен, static служит Cloudflare; target PWA/PG/Nginx topology и actual firewall не проверены; E-HTTP, F-006. |
| AC-OPS-02 | IN_PROGRESS | MANDATORY | CI/CD зелёные на baseline, но CD независим от CI и использует mutable main; F-003/004/014/015. |
| AC-OPS-03 | IN_PROGRESS | MANDATORY | Init helpers idempotent, rollout doc есть; versioned content/validated image/recovery gates не завершены; F-014/016/017. |
| AC-OPS-04 | IN_PROGRESS | MANDATORY | В repo нет подтверждённого restore rehearsal и разделённого user-data backup; VPS policy UNSET; F-014, Q-08. |
| AC-OPS-05 | IN_PROGRESS | MANDATORY | Auth/access tests PASS, token-URL redaction есть; raw Telegram IDs логируются, api_base_url из недоверенного context; F-021/028. |
| AC-LEG-01 | READY | MANDATORY | Classic single/selected_mix/all, counts 5/10/15/all, feedback: E-TEST + 12-case E-REPRO matrix; русские content fixtures/validators PASS. |
| AC-LEG-02 | READY | MANDATORY | Start/help/menu/reading/fallback handlers: E-TEST PASS по поведению; 14 Windows teardown failures изолированы E-FIXTURE. Новый live Telegram smoke не выполнялся. |
| AC-LEG-03 | IN_PROGRESS | MANDATORY | Fresh /ui/bootstrap/hydration/entrypoint contracts подтверждены E-TEST/E-FIXTURE; malformed setup не валидируется безопасно и API destination недоверен: F-020/028. |
| AC-LEG-04 | READY | MANDATORY | Code gate private+owner, aggregate renderer/menu review; E-TEST и synthetic owner/non-owner/group matrix E-FIXTURE PASS. |
| AC-LEG-05 | READY | MANDATORY | Polling default, explicit webhook, classic без Mini App, legacy API switch/dedicated runtime: config/update-mode/runner tests PASS (E-TEST). |
| AC-LEG-06 | READY | MANDATORY | JSON IDs/topic registry и m1-q3 сохранены; validators и existing parity fixtures PASS (E-CONTENT/E-TEST). Target PG migration относится к FND-05. |

## Полный реестр findings и blockers

Приоритеты: P1 — integrity/security/delivery foundation или обязательный платформенный gap; P2 — локальный дефект/verification/maintainability; P3 — отложенное улучшение. Finding не разрешает FIX и не добавляет требования. HIGH относится к конкретно указанному evidence, а не ко всему production.

| ID / состояние | Проблема / область | Evidence, влияние, приоритет, confidence | Действие / основание / зависимости |
| --- | --- | --- | --- |
| F-001 / CLOSED | Прежний spec расходился с SRC-01. | PR #282 merged c914793; E-SOURCE/E-GH. P1; HIGH. | DOCUMENT выполнено: E01–E14/76 AC. Остаточные открытые решения — F-010, не скрытое завершение продукта. |
| F-002 / CLOSED | Старые workflow/router и duplicate CI rules. | PR #282, AGENTS/root ci-cd-rules, удалён docs/ai-coding-workflow.md. P1; HIGH. | CONSOLIDATE выполнено; дальнейшие stale supporting sections — F-009/027. |
| F-003 / OPEN | CD не зависит от CI; main и production без protections. | E-GH: protected=false, rulesets=[]; production rules=[], branch policy=null. CD push/manual независимо от CI. P1; HIGH. | FIX в выбранной pipeline Goal: exact revision/gates/protections. Не изменено аудитом. |
| F-004 / OPEN | CI не запускает behavioral suite; whitespace step без comparison base малоинформативен. | ci.yml: validators/compile/init/seed, нет tests; checkout + git diff --check проверяет чистое дерево, не PR diff. E-GH. P1; HIGH. | FIX risk-based behavioral gate и явный diff range; discovery gap — F-022. Требуется pipeline scope. |
| F-005 / CLOSED — audit blocker снят | Глобальные Python packages несовместимы с requirements. | E-TEST: isolated Python 3.12 venv по requirements запускает API suite; глобальные FastAPI/pydantic не менялись. P2; HIGH. | DOCUMENT: использовать isolated env из README. Старый import failure не считать runtime-дефектом и не оставлять blocker AC-LIT-02. |
| F-006 / OPEN | Backend version/health/recovery и прямой VPS доступ не подтверждены. | E-HTTP: static=main, API unauth 401; public /healthz Nginx 404. E-CD checkout sync не доказывает образ. P2; HIGH для ограничения. | DOCUMENT после проверки exact running version, внутреннего health и safe business smoke в runtime Goal; 404 не доказывает outage API. Target host/config owner UNSET. |
| F-007 / OPEN | Нет source certification/Drive revision mapping всего банка и glossary. | E-CONTENT: 575/99 approved; source_ref(s) не обеспечивают per-item revision. E-SOURCE root inventory только первый уровень. AC-SRC-01–07/QUIZ-06. P1; HIGH. | IMPLEMENT recursive inventory/provenance validator и source-backed review; не переутверждать content по старым repository-evidence reports. |
| F-008 / OPEN | Length cues и содержательное качество банка требуют review. | E-CONTENT: 487/575 (84,70%) correct options uniquely longest; 21 severe cue; exact duplicate question/answer pairs проверены report. P2; HIGH для метрики, MEDIUM для педагогического дефекта. | FIX после source review, без искусственного padding; historical queue остаётся актуальной; E02/E03. |
| F-009 / DEFER | Подробные старые audit reports/RFC уже лежат в repo. | Inventory ниже; banners PR #282 снизили stale authority, raw snapshots всё ещё дублируют evidence. P2; HIGH. | CONSOLIDATE/архивировать в отдельной docs Goal по карте; сохранять unresolved IDs. Audit PR меняет только spec/plan. |
| F-010 / OPEN | Q-01–Q-08: продуктовые/технические решения ещё открыты. | Spec: account/linking, versioning, algorithms, literature mapping, optional scope, mail, source coverage/recovery. P1; HIGH. | DOCUMENT решения до соответствующей реализации; root ID уже установлен. Не трактовать неизвестный алгоритм как разрешение придумать policy. |
| F-011 / DEFER | Legacy m1-q3 и прежние optional content follow-ups. | E-CONTENT/tests, сохранённое решение старого плана. P3; HIGH. | DEFER переименование/новые batches/experimental difficulty до выбора scope; stable ID не является мусором. |
| F-012 / OPEN | Reading Tracker охватывает неполную библиографию и legacy statuses. | 42 review entries в 4 непустых Module 1 списках; пятый literature JSON пуст. Нет audio/outbound-reference полей; E-CONTENT. AC-LIT-01–03. P2; HIGH. | IMPLEMENT corpus-wide inventory + bibliographic verification; DOCUMENT mapping Q-04 до замены legacy states. |
| F-013 / OPEN — переаудирован | Незакрытые риски прежнего runner audit и browser coverage. | AUDIT-001–008 reconciled ниже; frontend tests — 32 source-string contracts; E-HTTP browser только без Telegram. P2; HIGH для test gap, MEDIUM для непроверенных UX failures. | FIX runtime DOM/network/concurrency tests в выбранном scope; не объявлять каждый старый риск воспроизведённым багом. |
| F-014 / OPEN | Поставка mutable main, слабые post-checks и stateful/recovery gaps. | deploy.sh: fetch/ff origin/main, lock может выйти 0 без доставки, проверка Running/logs; seed вызывается до rebuild при app/sql изменениях и может использовать старый image. Bootstrap reset --hard/remove-orphans. E-CD. P1; HIGH для кода, runtime applicability PARTIAL. | FIX exact candidate/artifact и build-before-migration, явные preconditions, recovery/restore и post-checks. Actual backup policy UNSET; не запускать bootstrap/restore аудитом. |
| F-015 / OPEN | Невоспроизводимые transitive deps/build tooling. | requirements без lock; Actions tags, python:3.12-slim и npx wrangler без pinned version; CD permissions наследует repo default read. E-CODE/E-GH. P2; HIGH. | FIX pin/lock inputs и explicit least permissions в tooling Goal; не объявлять фактический CD token write-capable без evidence. |
| F-016 / OPEN | Исправление question/options искажает историю ответов. | E-REPRO: после upsert OLD CORRECT → NEW WRONG, recorded_correct=1/current_correct=0. schema references mutable content, snapshot/version отсутствует. AC-PROG-04/FND-06/QUIZ-07. P1; HIGH. | FIX versioned content/attempt snapshot + migration/regression; Q-02. Abandon active sessions не сохраняет семантику completed history. |
| F-017 / OPEN | Снятие approval не исключает ранее seeded вопрос из выдачи; parity может пропустить проблему. | E-REPRO: approved → draft seed оставляет DB approved. db.upsert_approved_questions фильтрует вход; audit_question_bank относит canonical retired rows к informational без проверки DB status; existing test закрепляет это. AC-QUIZ-01/SRC-07. P1; HIGH. | FIX explicit lifecycle sync и gate для retired-but-serving; сохранять rows/history, не удалять user data; зависит от F-016/Q-02. |
| F-018 / OPEN | Glossary state только в памяти без retention policy. | miniapp_glossary._SESSIONS, classic context.user_data; пять restart увеличивают registry 1→6, cleanup/TTL нет. Ответы теряются при process restart, workers не делят state. AC-FND-08/GLO-02. P1; HIGH. | IMPLEMENT persistent personal term state и безопасный lifecycle по общей data model; до этого не масштабировать glossary несколькими workers. |
| F-019 / OPEN | Повторный glossary next меняет варианты уже показанного вопроса. | E-REPRO: тот же term/order, correct index 3→1; прежний отображённый правильный ответ оценивается false. _safe_question вызывается вновь без stable step. AC-GLO-01/FND-07. P1; HIGH. | FIX stable question instance/step token и idempotent answer/next; regression duplicate/retry/cross-request tests. Учесть shared in-memory concurrency. |
| F-020 / OPEN | Malformed quiz/glossary payloads вызывают 500; boolean category ID принимается. | E-REPRO: list в question_count/quiz_mode/difficulty и glossary count → 500; category_ids=[true] → 200 для category 1. set-membership до type guard, isinstance(bool,int). AC-QUIZ-02/LEG-03. P2; HIGH. | FIX strict types/finite enums и structured 4xx; negative/API tests и отсутствие изменения session после invalid payload. Auth bypass не обнаружен. |
| F-021 / OPEN | Логи содержат raw Telegram user IDs вопреки AC-OPS-05. | miniapp_fastapi._log_request, handler_latency, classic handlers; synthetic log check TRUE. Реальные user IDs не извлекались. P2; HIGH. | FIX убрать или согласованно псевдонимизировать IDs; negative logging tests. Token URL redaction уже есть и не решает эту проблему. |
| F-022 / IN_PROGRESS | Canonical unittest command неполон; tests непереносимы на Windows. | E-TEST: 281 pytest cases, 264 pass/16 fail/1 skip; 11 pytest-style tests не запускаются unittest (pytest отсутствует requirements). E-FIXTURE: 16/16 после временной fixture adaptation проходят. P2; HIGH. | FIX реализован в PR1 worktree: requirements-dev/pytest, explicit closing и portable fixtures. E-STAB-01: локальная suite PASS с одним Docker skip; Linux Docker/CI и merge ещё PENDING. После gates закрыть discovery/fixtures finding. |
| F-023 / OPEN | Известные advisories в resolved requirements. | E-DEPS: 16 записей = 8 уникальных advisory IDs: python-dotenv 1.0.1 (1), Starlette 0.46.2 (7). FastAPI 0.115.12 ограничивает Starlette <0.47.0. P2; HIGH для installed versions, MEDIUM для применимости. | FIX совместимый dependency upgrade/lock после reachability review; set_key, FileResponse/StaticFiles, form parsing/HTTPEndpoint не используются в app, остальные случаи проверить. Exploit production не доказан. |
| F-024 / OPEN | Coupling и точный dead duplicate повышают риск локальных изменений. | classic_quiz_handlers 1778 строк с dynamic _main_attr; main 1125, miniapp_api 1069, index.html 2542. _get_classic_reply_state определён идентично на 107/1266, первая binding замещена. Schema helpers дублированы в init_db/db/schema. P2; HIGH. | REFACTOR по границам domain/transport и одному migration owner; REMOVE только подтверждённый shadowed duplicate отдельным scope. Legacy HTTP adapter имеет consumers/tests/flag и не считается dead. |
| F-025 / OPEN | SQLite connection lifecycle и масштабирование не доказаны. | Classic handlers/main используют with get_connection без close (SQLite context завершает transaction); E-FIXTURE показывает Windows file handles до GC. ORDER BY RANDOM; API GET создаёт/обновляет user; JSON читается с диска на запрос. P2; HIGH для lifecycle, MEDIUM для нагрузки. | Explicit closing в handlers/main/entrypoint исправлен PR1 (E-STAB-01); performance/load измерять перед scale/PG migration, не придумывать SLO. Нет доказанного production bottleneck; duplicate indexes оценить перед удалением. |
| F-026 / OPEN | Большая часть целевой платформы не реализована. | E-CODE + AC registry: нет React/PWA, PG/pgvector, e-mail accounts/linking, repetition/personal analytics, knowledge/Obsidian/search, assignments, practice export, owner source dashboard; Reading Tracker частичен. P1; HIGH. | IMPLEMENT выбранными Goals по roadmap и зависимостям. Это agreed scope, не новые features из findings; optional 9 AC отдельно. |
| F-027 / OPEN | Supporting docs/config examples содержат stale детали. | README считает только unittest suite; .env.example не показывает dedicated API settings; runbook sections 9/12 всё ещё требуют MINIAPP_API_ENABLED для dedicated API, хотя flag относится к legacy in-bot server. Glossary coverage говорит 96 entries, actual 99. P2; HIGH. | DOCUMENT/CONSOLIDATE по карте ниже; ссылки README/AGENTS/spec/plan и cross-links runbook/RFC проверить. Не исправляется audit PR. |
| F-028 / OPEN | Frontend доверяет api_base_url из unsigned URL context и отправляет туда initData. | index.html: context из query/hash → apiBase без origin allowlist → Authorization/simple_body initData. Backend сам проверяет initData, но destination не закреплён. AC-OPS-05/LEG-03. P1; HIGH для dataflow, MEDIUM для exploitability. | FIX trusted endpoint configuration/allowlist и credential non-disclosure test. Для эксплуатации нужен modified launch context в Telegram с valid initData; на production не воспроизводилось и secrets не отправлялись. |

### Reconciliation прежних AUDIT-001–008 (F-013)

| Старый ID | Результат текущей сверки / действие |
| --- | --- |
| AUDIT-001 | PARTIAL: fresh compact setup/backend hydration теперь есть и проверены contracts; legacy runner fallback/context и stale/network DOM scenario полностью не проверены. DEFER closure до runtime tests, не считать старую permanent-setup гипотезу воспроизведённым bug. |
| AUDIT-002 | DEFER UX: при потере API и cache остаётся инструкция повторить /ui; fallback предусмотрен. Recovery без переоткрытия требует отдельного UX решения, не новый обязательный feature. |
| AUDIT-003 | PARTIAL: try/catch/finally/guards появились, но exception/button recovery не проверяется реальным DOM suite. FIX validation gap совместно с AUDIT-005. |
| AUDIT-004 | OPEN: backend frontend_version=ui-polish-v2, HTML ui-polish-v6-visual-cleanup; build_miniapp_url не добавляет обязательный asset version. Published asset сейчас совпал, cache policy не гарантирована. FIX единый version identity при frontend Goal. |
| AUDIT-005 | OPEN: 32 frontend tests проверяют substrings, runtime DOM/Telegram event wiring suite нет. FIX минимальными сценариями по риску. |
| AUDIT-006 | PARTIAL: PR #282 добавил authority banners/canonical routing, но contradictory operational sections остаются (F-027). CONSOLIDATE по карте. |
| AUDIT-007 | Частично закрыто: exact-origin positive/negative FastAPI tests и origin_allowed diagnostics есть. Exact equality сама по себе не дефект и wildcard не нужен; startup config validation/real alternate-origin matrix остаются в F-027. |
| AUDIT-008 | OPEN risk: setup повторно abandons/создаёт session; server idempotency key и concurrent-setup regression отсутствуют. Не доказана потеря answer data; FIX/проверить при stabilization scope. |

### Документы, generated/legacy области и консолидация

Текущий audit PR не меняет перечисленные ниже supporting files. Canonical destination: intent/AC → spec, findings/state → этот план, workflow → AGENTS, pipeline setup rules → root ci-cd-rules, executable commands → existing scripts/README. Все 27 Markdown документов включены в inventory; дополнительных development-rules не создавать.

| Область | Предлагаемое решение, основание, destination и затронутые ссылки |
| --- | --- |
| README, AGENTS, root ci-cd-rules | KEEP routing; README исправить test runner/config pointers в выбранной docs/tooling Goal (F-022/027). AGENTS/ci-cd не переписывать ради wording. Затронуты README commands и ссылки на tests/runbook. |
| spec/plan | KEEP canonical; только эти два файла обновляет audit PR. Все стабильные requirement/AC/finding IDs сохраняются. |
| delivery-plan-archive, ai-delivery-infrastructure-plan | KEEP history/provenance, не второй roadmap. Ссылки README/plan/AGENTS сохранять. |
| miniapp-deployment-qa, question_bank_content_rollout | CONSOLIDATE текущие операции: устранить legacy API enablement ambiguity, не обещать сохранение смысла history простым abandon; destination те же файлы + executable scripts. Затронуты README/AGENTS, runner design, hydration, question-bank docs. |
| miniapp-quiz-runner-design, miniapp_setup_hydration | KEEP current contracts; MERGE stale duplicate state/launch описания в актуальный hydration/API reference, historical части ARCHIVE отдельно. Затронуты README/spec/AGENTS/runbook и frontend contract docs check. |
| literature_runtime_rfc, glossary_literature_contours_rfc, topic_registry_schema_phase1, proposals/refactor-plan-miniapp-bot | KEEP до решения соответствующих Goals; MERGE подтверждённые current contracts в spec/supporting reference, завершённые предложения ARCHIVE. Затронуты cross-links RFC, runbook и plan; не переносить /next/reminders в scope автоматически. |
| literature_source_inventory | KEEP source-list IDs/limitations; обновить corpus coverage после source Goal, статус только в плане. Затронуты literature RFC и plan. |
| content_audit_all_topics, content_audit_fiziologiya_cheloveka, content_audit_module2, content_source_alignment_module2_qualitative | ARCHIVE полные старые reports вне active docs после переноса всех obligations в plan; source review evidence сохранить по revision. Затронуты quality/docs cross-links, spec/plan supporting references. |
| glossary_content_audit, glossary_coverage, glossary_global_quality_alignment | CONSOLIDATE inventory/provenance в один supporting reference после source review; 96 vs 99 исправить по actual JSON. Detailed historical reports ARCHIVE; затронуты glossary engine/RFC/coverage cross-links. |
| glossary_distractor_engine | KEEP algorithm/reference; linked source obligations и tests обновлять в content Goal. Не source certification. |
| question_bank_quality_and_db_parity, question_bank_quality_calibration | KEEP tooling usage/threshold meaning; state/readiness → plan. Исправить retired lifecycle gate по F-017. Ссылки rollout/scripts/tests/quality reports затронуты. |
| audits/2026-05-24-miniapp-runner-audit и 4 audit JSON | Historical outputs, не runtime assets. Quality/parity reports генерируются существующими scripts; calibration changelog/review queue — curated records, полного воспроизводимого generator для queue нет. KEEP до reconciliation; затем ARCHIVE snapshots, оставить нужные fixtures/queue по tooling decision. На queue/calibration JSON ссылаются tests, удаление без consumer check запрещено. |
| Runtime/legacy/code | Legacy HTTP adapter реально gated/configured/tested, не dead. Dynamic _main_attr и bot handler registration проверены. Подтверждённый shadowed duplicate — F-024. Vendored/generated production code отсутствует; .gitkeep без влияния, оснований для отдельной cleanup Goal нет. |

## Roadmap и предлагаемые Goals

Это предложения для выбора пользователя, не активная implementation Goal.

| Приоритет / scope | Результат и критерии закрытия | Зависимости / non-goals |
| --- | --- | --- |
| 1 — PLATFORM-STABILIZATION-001 (активна) | Устранить F-016/017/019/020/021/028: stable history и glossary steps, strict API input, trusted API destination, privacy-safe logs; добавить regression cases и переносимый behavioral gate для затронутого кода. Runtime delivery — только после применимых условий F-003/014. | Q-02 versioning/snapshot решение; F-022 test runner; при runtime delivery нужен проверенный target/config/recovery. Non-goals: массовая переработка content, PWA/PG migration, новые учебные контуры и optional AI. Можно разделить на связанные PR. |
| 1a — DELIVERY-FOUNDATION-001 | F-003/004/014/015/023: CI→merge→CD exact revision, behavioral suite, воспроизводимые deps/build, controlled migration, version+health/business post-checks и безопасный recovery rehearsal. | Явный pipeline/settings scope и config owner/target; Q-08. Non-goals: продакт-функции и необязательный redesign инфраструктуры. Может быть подготовительным PR в выбранной foundation Goal. |
| 2 — PLATFORM-FOUNDATION-001 | Общие account/content/user-state boundaries, versioned migration design, минимальный безопасный PWA/backend/PG срез по выбранным AC E01/E11. | Q-01/Q-02/Q-06, stabilization/delivery gates. Не брать сразу все E01–E14. |
| 3 — PROGRESS-001 | E04 и adaptive E03: personal history/errors/due-list и сохранение semantics. | Identity/versioning, Q-03; mastery conditional отдельно. |
| 4 — SOURCE-KNOWLEDGE-001 | E02/E06/E07 + glossary links: recursive source inventory, revision provenance, notes/export/retrieval. | Q-07, source access/review и минимальная PWA; массовый content approval не выполнять автоматически. |
| 5 — LEARNING-CONTOURS | E08/E09/E12: assignments, полный Reading Tracker, owner coverage dashboard. | Foundation/provenance/PWA; Q-04. Разделить на проверяемые feature Goals. |
| 6 — PRACTICE-EXPORT | E10 structured external-model packages и учебный analysis package. | Source-backed criteria; API/voice/RAG не обязательны. |
| Отдельное решение | 9 conditional AC и прочие optional исторические предложения | Не включать только по наличию в каталоге или findings. |

### Audit quality review

Охват: требования всех 14 эпиков, 76 AC и scope conditions; tracked source/tests/config, schema/content tooling, auth/logging, docs, GitHub/settings/records и безопасный live smoke. Все прежние F-001–015 сохранены/обновлены; AUDIT-001–008 reconciled без потери неизвестных closures. Current Goal восстановлена по merge, а не старому checkpoint.

READY присвоен только 6 узким AC с code+automatic evidence. Наличие FastAPI или UI не закрывает target PWA/platform AC. 0% не означает «ничего нет». Seed fresh DB PASS не исключает update bugs (F-016/017); зелёный CI не заменяет behavioral tests; строковые frontend contracts не равны E2E.

False-positive review: 16 test failures — Windows fixture/lifecycle, не 16 доказанных бизнес-регрессий; dependency scan 8 unique advisories, не 16 независимых exploit; public health 404 не означает неработающий API; strict CORS и intentional legacy fallback не названы security defects; m1-q3/legacy adapter не удаляются как orphan code.

Ограничения/false negatives: нет authenticated Telegram/mobile E2E, VPS shell/образа/restore evidence, нагрузочного измерения, полного recursive Drive corpus semantic review, private provider settings и billing. HIGH confidence — repo inventory и воспроизведённые defects; MEDIUM — полнота UX/security/external integration assessment; current backend artifact и recovery — UNSET. Ни непроверенное, ни отсутствие найденных secrets в узком pattern scan не выдаются за доказанную безопасность.

## Checkpoint и следующий шаг

PLATFORM-STABILIZATION-001 активна по поручению пользователя; PWA остаётся следующим приоритетом. PR1 branch `codex/stabilization-delivery-foundation`, base `df383200fd0e6c389038f5b080ec23310a26be07`. Commit `80185ef`: Goal/portable fixtures/explicit closing, 71 focused tests PASS. Candidate delivery/CI/backup/health implementation и регрессии подготовлены; полный local suite 303 PASS, 1 Docker CLI skip, 24 subtests PASS (Windows/Python 3.12, 19.09); После итогового изменения: 53 focused tests/8 subtests PASS; actionlint 1.7.12, Bash syntax, compileall и whitespace PASS. Self-review trust/revision/failure/data boundaries выполнен. Docker contract обязателен в Linux CI. Остаток F-003/014/015/025/027 за границами исправленной части сохраняется.

Audit PR #283 merged в baseline; CI 35445120304 и post-merge 35445143654 PASS, docs CD 35445143646 PASS без restart. Прошлая audit branch безопасно удалена. Это не evidence новой runtime версии.

Следующий шаг PR1: initial push/PR (local validation/self-review завершены), дождаться CI/provider checks, merge, получить exact merge SHA и подтвердить gated CD с backup rehearsal, user preservation, health/revision и image IDs. До этого runtime delivery PENDING. После поставки — очистить только свою merged branch, fresh main и PR2 input/privacy/trusted destination; далее PR3 glossary и PR4 history/lifecycle. Не пересчитывать readiness snapshot и не начинать PWA в этой Goal.
