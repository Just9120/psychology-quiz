# Delivery Plan

## Current Goal — PLATFORM-STABILIZATION-001

**Поручение:** пользователь 2026-09-19 одобрил предложенную stabilization Goal и отдельно подтвердил приоритет перехода на PWA. Goal активирована встроенным инструментом. Результат — безопасный существующий quiz/backend как основа общего PWA backend; расширение Telegram-only UX не входит в работу.

**Scope:** F-016/017/019/020/021/028; необходимые test discovery/Windows fixtures (F-022), behavioral CI и минимальные delivery preconditions (затронутая часть F-003/004/014). Область AC: QUIZ-01/02/07, GLO-01, LEG-03, OPS-02/03/05, части FND-06/07 и PROG-04. Целые platform/progress epics и все OPS AC не считаются автоматически завершёнными.

**Non-goals:** PWA/React и PostgreSQL migration, accounts, repetition/knowledge/search, новые учебные контуры, массовая правка content, полное persistence глоссария F-018, dependency/security modernization всего проекта и broad refactor. После Goal остановиться; следующий приоритет для выбора — PWA/platform foundation.

**Baseline:** `df383200fd0e6c389038f5b080ec23310a26be07`, fresh origin/main 2026-09-19. Main чистый, один worktree, open PR нет. Первый PR branch `codex/stabilization-delivery-foundation`, base тот же SHA; PR ID до push UNSET. Audit PR #283 merged; последняя аудиторская готовность ниже остаётся snapshot c914793 и не пересчитывается.

### Решения и порядок PR

- История: фиксировать неизменяемую редакцию вопроса/вариантов при включении в попытку; хранение независимо от Telegram-клиента. Существующие попытки backfill только доступным содержимым, без выдумывания утраченных редакций; migration additive/idempotent, оригинальные answers/score/user data сохраняются. Контракт SQLite snapshot v1/hash/provenance закреплён в spec до PR4 (Q-02).
- Lifecycle: non-approved/removed derivative исключается из новых selections, прежняя attempt revision остаётся читаемой. Physical delete user/history rows не нужен.
- Recovery: перед stateful changes согласованный pipeline создаёт SQLite backup и проверяет восстановление в отдельный временный файл. Production restore/volume cleanup не выполняются автоматически. При post-check failure остановка и forward-fix в scope; rollback только после доказательства совместимости.
- Delivery: существующий trusted VPS target из Repository Secrets + pinned host verification; exact validated main SHA, allowlisted directory/services, build before init/seed, runtime image/source identity, internal health и read-only business smoke. Никакого bootstrap/reset --hard/remove-orphans; неизвестный или изменившийся target останавливает поставку.
- GitHub-wide approval/access policy не изменять попутно. Настроить необходимый CI→CD gate в workflows; оставшиеся protections/supply-chain gaps сохранять findings.

| PR / связная задача | DoD / результат | Состояние |
| --- | --- | --- |
| 1. Validation/delivery foundation | Canonical pytest обнаруживает все tests; Windows fixtures и explicit DB closing исправлены; behavioral CI, exact revision delivery/build-before-migration, verified backup/recovery precheck, image/version/health/readonly smoke; targeted procedures обновлены | DONE: #284 + hotfix #285, CD 35447236343 PASS на 8c53aba |
| 2. API input/privacy/destination | F-020/021/028 закрыты regression tests; 4xx без state mutation, отсутствие raw user IDs/initData в logs и невозможность отправки auth на arbitrary origin; совместимые clients | DONE: #286, CD 35448090503 + published assets 9346ab1 |
| 3. Glossary retry | F-019: stable step/options, answer/next idempotency и concurrent/retry tests; dedicated/legacy routes и chat совместимы; old no-step requests требуют refresh, без нового durable learning subsystem | DONE: #287 / 7a5fdc9; CD 35449032741 и static assets PASS |
| 4. Content history/publication | F-016/017: immutable attempt content + safe backfill/lifecycle sync, retired-serving gate, regression/migration/preservation tests и stateful delivery | CODE READY: codex/stabilization-attempt-history, base 7a5fdc9; CI/merge/CD PENDING |

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

Аудиторские E-CODE/E-TEST/E-REPRO и связанные записи — на audit baseline. E-STAB records относятся к указанным revision/worktree текущей Goal; они обновляют Evidence затронутых AC, не аудиторские проценты. Диагностические scripts/logs/SQLite/venv находятся вне repo; в план включены результаты и воспроизводимые сценарии, не raw logs.

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
| E-STAB-05 | PASS local / CI+delivery PENDING | PR4 worktree от 7a5fdc9. Общая suite: 361 PASS, 7 новых cases выявили несовместимость sqlite.Row в reused diagnostic helpers, 1 Docker skip; исправление проверено всеми 139 affected backend/migration/Telegram tests PASS (8 subtests), затем 43 deployment/parity checks PASS; итоговый approved-only guard и affected quiz clients — 123 tests/8 subtests PASS. Реальные init/seed дважды на отдельной SQLite, 575 approved/8 topics, integrity/FK/parity clean; compileall, validators, actionlint и Bash syntax PASS. New snapshot hashes, legacy provenance, immutable trigger, content mutation/history, API owner/recent feedback и stateful recovery/failure gates покрыты. Docker compose обязателен в Linux CI; локально CLI отсутствует. |
| E-STAB-04 | PASS code/delivery | #287 / 7a5fdc9, CI 35449003870, CD 35449032741/job 105912854988 PASS 19.09 14:32 UTC; exact runtime labels, DB/HTTP smoke PASS. Bot image sha256:640913d36367e6a2263243541389cc045a504903c21c04f427061bb973de6ec9; API sha256:521f9c2bb839e69c54f9ffb19f87af4e1e9b01cabb5beca5dd691da6e6db417a. Published HTML normalized sha256 83b0e695f620d171d3b316c6e49896734320ef307711b824a189661a1a3b4f2e совпал с main, Cloudflare build 9790b083-0908-446b-b7dd-5b881b163cab PASS. Local: 143 tests и 8 subtests PASS; stable options, concurrent/replayed answer/next/restart, stale/wrong owner/invalid token и dedicated/alias routes. Node actual UI helper lost-response/double-tap/stale-reply PASS; IAB local synthetic fixture answer failure → same-choice retry → feedback → result → restart PASS, console warnings/errors нет. Telegram production roundtrip не выполнялся. |
| E-STAB-03 | PASS code/delivery | #286 / 9346ab1; focused 184 + subsequent 123/86 tests PASS, Node actual fetch guard + local IAB legacy chooser/form PASS. CI 35448069825 и CD 35448090503/job 105910416453 PASS 19.09 14:14 UTC, internal health exact SHA/auth401, DB smoke, bot image sha256:8a56f5f0852d28dca210ac30d847cb28bb10c3dd0d56a34e0b91ee58546b6c4f / API sha256:6c53b0a5a04af5d0d8c07e6a8860951ffa280aef2334eef531d1cb300395ca65. Published HTML sha256 normalized 9b148a7bfd38cea45c3ee1209765949adf1445b0bc7aeed167e6e6e4415a6b3e, config 361d2c085b6d0580174714a0081e84f8fafcba0ad6f54c3d41bd66afacd03032, совпали с main. |
| E-STAB-02 | PASS delivery | PR #284/#285; final main 8c53aba, CI 35447211955 и CD 35447236343/job 105908164003 (2026-09-19 13:57 UTC). Backup `/data/backups/release-3tghz4bi/quiz.sqlite3`, isolated restore/integrity/FK и USER_STATE_PRESERVED PASS; DATABASE_SMOKE_OK, HTTP_SMOKE_OK exact SHA. Bot image sha256:8f8a9eb25d12a349973a0ff6d7a9d1c2e8711073b7ed564e674295fd01288c7d; API sha256:91af5e21b06f805f152f5a153353c935797217db1ebbfc34d99a7e98cc11256c; оба Running и label=8c53aba. Это bounded read-only runtime smoke, не Telegram roundtrip/load test. |
| E-STAB-01 | PASS local / delivery PENDING | PR1 worktree от df38320: 303 passed, 1 skipped (Docker отсутствует), 24 subtests passed; behavior tests включают 12 real-shell/fake-boundary deployment paths, exact CI selection, SQLite backup/isolated restore/preservation. 71 affected legacy tests PASS. Эти результаты не подтверждают VPS до post-merge CD. |
| E-DOCS | PASS local | Итоговый spec/plan diff: 76 unique AC/spec-plan parity, 67+9 scope split, 28 unique findings, counts/readiness, relative links/anchors и whitespace PASS; только два разрешённых Markdown files. Source/READY/findings self-review выполнен. CI/merge определять по PR head branch и primary records, не по будущему обещанию в snapshot. |

### Окружения и delivery facts

| Поверхность | Установлено / UNSET / N/A |
| --- | --- |
| Local diagnostic runtime | Windows/Python 3.12/isolated venv, synthetic SQLite; Docker отсутствует, WSL не установлен. Не GitHub Environment. |
| CI | PR main, push main, manual; ubuntu-latest/Python 3.12; contents:read; concurrency workflow/ref с cancel. PR checkout default merge ref; head_sha записи run отличать от фактического test-merge tree. Required GitHub checks/reviews не настроены; published checks ожидаются по AGENTS. |
| production Environment | CD Deploy production job; SSH к VPS checkout /opt/psychology-quiz, services psych_quiz_bot + psych_quiz_miniapp_api. Compose project psychology-quiz подтверждён runtime checks E-STAB-02/03/04; host/user values не извлекались, персональный config owner UNSET. Нет environment protections. |
| Application production | Compose loopback ports и ./data bind; source content read-only mount; .env + explicit Compose overrides. Известны имена secrets/vars из procedures, не их values. API через Nginx; internal health и image revision подтверждены E-STAB-02/03/04; внешний firewall и отдельный authenticated roundtrip не проверялись. |
| Static deployment | Отдельный Cloudflare Worker psychology-quiz-miniapp, assets ./miniapp, current published HTML подтверждён. Это deployment unit, отдельный GitHub Environment не обнаружен. |
| Product variants | Classic, Mini App и будущая PWA — клиенты; не три автоматически существующих environments. PWA deployment N/A пока клиент не реализован. |
| Queue/artifact/stateful | CD workflow_run successful exact main CI/manual; concurrency без cancel + failing lock timeout, stale SHA отказ. Candidate images строятся до migrations, label/digest подтверждаются; backup/isolated restore E-STAB-02. VPS rebuild inputs не полностью immutable; отдельное restore/retention Q-08 UNSET (F-014/015). |
| Длительность/стоимость | Baseline CI job 11s, CD job 13s; PR CI workflow ~19s. PR+main CI повторяют validators/install, docs push запускает CD. Billing/остаток minutes UNSET; выборка недостаточна для бюджета/latency SLO. Speculative reruns не запускались. |

## Состояние AC

Реестр отражает текущие AC; строки с E-STAB обновлены в Goal, остальные сохраняют audit baseline. E-FIXTURE подтверждает behavior с явно описанным ограничением; raw suite failures сохранены. Для BLOCKED указывается конкретное решение. Conditional scope помечен отдельно и не превращается в обязательный из-за наличия строки.

| AC | Статус | Scope | Evidence / оставшаяся работа |
| --- | --- | --- | --- |
| AC-FND-01 | IN_PROGRESS | MANDATORY | Topic registry, 8 категорий и module metadata есть; source/lesson graph и навигация всей платформы отсутствуют (F-026). |
| AC-FND-02 | IN_PROGRESS | MANDATORY | SQLite отделяет quiz/literature state по user_id; repetitions, bookmarks, assignments и platform identity отсутствуют (F-026). |
| AC-FND-03 | IN_PROGRESS | MANDATORY | FastAPI, Python bot и analytics существуют; общего backend для целевых контуров ещё нет (E-CODE, F-026). |
| AC-FND-04 | BACKLOG | MANDATORY | Нет React/TypeScript/Vite manifests/build и общего PWA клиента; E-CODE, F-026. |
| AC-FND-05 | BACKLOG | MANDATORY | Runtime — SQLite; PostgreSQL migration/recovery fixtures отсутствуют; Q-02, F-026. |
| AC-FND-06 | IN_PROGRESS | MANDATORY | SQLite content sync сохраняет versioned attempts, answers/users/literature (E-STAB-05); target indexes/embeddings и остальные learning subsystems ещё не реализованы. |
| AC-FND-07 | IN_PROGRESS | MANDATORY | Quiz duplicate guard/API feedback и glossary step/answer recovery проверены (E-STAB-04); общий multi-client backend вне Telegram ещё не реализован. |
| AC-FND-08 | IN_PROGRESS | MANDATORY | Quiz/literature сохраняются в SQLite; glossary state теряется при restart и не разделяется между процессами; F-018. |
| AC-FND-09 | BACKLOG | MANDATORY | Нет независимого PWA; опубликованная статика без Telegram показывает инструкцию /ui; E-HTTP, F-026. |
| AC-FND-10 | IN_PROGRESS | MANDATORY | Bot/Mini App используют quiz DB; PWA и общее состояние всех контуров отсутствуют; F-026. |
| AC-SRC-01 | BACKLOG | MANDATORY | Корень Drive установлен, 8 непосредственных подпапок; recursive ingestion/inventory pipeline отсутствует; E-SOURCE, F-007. |
| AC-SRC-02 | IN_PROGRESS | MANDATORY | Module/topic поля и source_ref есть; форматы одного занятия не связаны lesson metadata; F-007/026. |
| AC-SRC-03 | BACKLOG | MANDATORY | Нет ledger Drive file ID + processed revision и incremental processing tests; F-007/026. |
| AC-SRC-04 | IN_PROGRESS | MANDATORY | 575 questions/99 glossary approved не имеют проверенного per-item Drive revision mapping; validator этого не требует; F-007. |
| AC-SRC-05 | BACKLOG | MANDATORY | Автоматизированного source conflict/review состояния нет; source review полного corpus не выполнен; F-007/026. |
| AC-SRC-06 | IN_PROGRESS | MANDATORY | Литература содержит metadata, но происхождение всего учебного derivative не сертифицировано; F-007/012. |
| AC-SRC-07 | IN_PROGRESS | MANDATORY | Repository publication и lifecycle sync/parity подтверждены E-STAB-05; полного source review/publication trail ещё нет (F-007). |
| AC-SRC-08 | READY | MANDATORY | Нет runtime LLM/editor routes; entrypoints/dependencies и seed filtering/parity tests PASS (E-CODE/E-TEST/E-CONTENT). Ошибка снятия approval отдельно нарушает SRC-07/QUIZ-01. |
| AC-QUIZ-01 | READY | MANDATORY | Backend-derived categories + approved-only selection, lifecycle sync и parity gate; mixed-status/demotion/removal/new-attempt tests E-STAB-05. |
| AC-QUIZ-02 | READY | MANDATORY | #286/E-STAB-03: selection/setup positive suite + malformed/type/range/unknown-ID cases PASS; rejected setup сохраняет полный DB dump. Исторический F-020 исправлен. |
| AC-QUIZ-03 | BACKLOG | MANDATORY | Random выборка есть; history-aware adaptive sampling не реализован; Q-03, F-026. |
| AC-QUIZ-04 | IN_PROGRESS | MANDATORY | Difficulty metadata/any есть; текущий classic требует отдельный шаг, целевой необязательный UX и late calibration ещё не согласованы/проверены; Q-03. |
| AC-QUIZ-05 | IN_PROGRESS | MANDATORY | Feedback/explanation и duplicate recovery проходят API tests; links knowledge/source отсутствуют; F-026. |
| AC-QUIZ-06 | IN_PROGRESS | MANDATORY | Structural/quality audit PASS; 21 сильный length cue, полного source-backed review нет; E-CONTENT, F-007/008. |
| AC-QUIZ-07 | READY | MANDATORY | 575 legacy вопросов/IDs и предметные темы сохранены; immutable attempt editions выдерживают content edits/reorder/demotion/removal. Legacy uncertainty явно отмечена; E-STAB-05 и rollout procedure. |
| AC-PROG-01 | BACKLOG | MANDATORY | Нет persisted schedule/due-list для questions и terms; Q-03, F-026. |
| AC-PROG-02 | BACKLOG | MANDATORY | Нет API/UI личных ошибок и today queue; F-026. |
| AC-PROG-03 | BACKLOG | MANDATORY | Есть итог quiz и owner aggregates; нет личной истории/weak themes/dynamics/mastery distinction UI; F-026. |
| AC-PROG-04 | IN_PROGRESS | MANDATORY | Immutable attempt edition и сохранение исходных answers/score выполнены (E-STAB-05). Personal repetition/version-aware relearning пока отсутствует; Q-02 остаётся частично открытым. |
| AC-PROG-05 | BACKLOG | MANDATORY | Нет подтверждаемого selective learning reset с user-data invariants; F-026. |
| AC-PROG-06 | BACKLOG | CONDITIONAL | Условный scope; mastery policy Q-03 и temporal fixtures отсутствуют. |
| AC-GLO-01 | READY | MANDATORY | Topic quiz, owner isolation, stable step/options и персональный score; retry/concurrency/API tests E-STAB-04. Durable persistence относится к F-018. |
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
| AC-OPS-03 | IN_PROGRESS | MANDATORY | SQLite snapshots/lifecycle и additive retry/preservation checks выполнены (E-STAB-05). Заключительный stateful CD требует backup/restore rehearsal, old-user-state equality, snapshot/parity/version post-check; до primary record результат поставки PENDING. |
| AC-OPS-04 | IN_PROGRESS | MANDATORY | Whole-DB isolated restore rehearsal подтверждён E-STAB-02; отдельное восстановление user data относительно rebuildable content, retention/RPO/RTO ещё UNSET (F-014/Q-08). |
| AC-OPS-05 | IN_PROGRESS | MANDATORY | Auth/access и privacy/destination negative tests PASS; F-021/028 закрыты #286/E-STAB-03. Полный platform/security scope и dependency finding F-023 остаются. |
| AC-LEG-01 | READY | MANDATORY | Classic single/selected_mix/all, counts 5/10/15/all, feedback: E-TEST + 12-case E-REPRO matrix; русские content fixtures/validators PASS. |
| AC-LEG-02 | READY | MANDATORY | Start/help/menu/reading/fallback handlers: E-TEST PASS по поведению; 14 Windows teardown failures изолированы E-FIXTURE. Новый live Telegram smoke не выполнялся. |
| AC-LEG-03 | READY | MANDATORY | #286/E-STAB-03: runner/entrypoint/context/API contracts PASS; IAB legacy form с hostile context остаётся работоспособной; API destination опубликован и защищён. Ограничение authenticated mobile E2E сохранено. |
| AC-LEG-04 | READY | MANDATORY | Code gate private+owner, aggregate renderer/menu review; E-TEST и synthetic owner/non-owner/group matrix E-FIXTURE PASS. |
| AC-LEG-05 | READY | MANDATORY | Polling default, explicit webhook, classic без Mini App, legacy API switch/dedicated runtime: config/update-mode/runner tests PASS (E-TEST). |
| AC-LEG-06 | READY | MANDATORY | JSON IDs/topic registry и m1-q3 сохранены; validators и existing parity fixtures PASS (E-CONTENT/E-TEST). Target PG migration относится к FND-05. |

## Полный реестр findings и blockers

Приоритеты: P1 — integrity/security/delivery foundation или обязательный платформенный gap; P2 — локальный дефект/verification/maintainability; P3 — отложенное улучшение. Finding не разрешает FIX и не добавляет требования. HIGH относится к конкретно указанному evidence, а не ко всему production.

| ID / состояние | Проблема / область | Evidence, влияние, приоритет, confidence | Действие / основание / зависимости |
| --- | --- | --- | --- |
| F-001 / CLOSED | Прежний spec расходился с SRC-01. | PR #282 merged c914793; E-SOURCE/E-GH. P1; HIGH. | DOCUMENT выполнено: E01–E14/76 AC. Остаточные открытые решения — F-010, не скрытое завершение продукта. |
| F-002 / CLOSED | Старые workflow/router и duplicate CI rules. | PR #282, AGENTS/root ci-cd-rules, удалён docs/ai-coding-workflow.md. P1; HIGH. | CONSOLIDATE выполнено; дальнейшие stale supporting sections — F-009/027. |
| F-003 / OPEN | CD не зависит от CI; main и production без protections. | E-GH: protected=false, rulesets=[]; production rules=[], branch policy=null. На audit baseline CD push/manual независимо от CI; #284/#285 ввели trusted exact CI→CD gate (E-STAB-02). Protections отсутствуют по повторной проверке 19.09. P1; HIGH. | Exact revision/gates исправлены в текущей Goal; GitHub-wide branch/environment protections остаются отдельным policy scope. |
| F-004 / CLOSED | CI не запускает behavioral suite; whitespace step без comparison base малоинформативен. | ci.yml: validators/compile/init/seed, нет tests; checkout + git diff --check проверяет чистое дерево, не PR diff. E-GH. P1; HIGH. | FIX выполнен #284: pytest + Docker contract и explicit base..HEAD; E-STAB-02/CI 35447211955 PASS. F-022 закрыт; это не подтверждает все будущие AC. |
| F-005 / CLOSED — audit blocker снят | Глобальные Python packages несовместимы с requirements. | E-TEST: isolated Python 3.12 venv по requirements запускает API suite; глобальные FastAPI/pydantic не менялись. P2; HIGH. | DOCUMENT: использовать isolated env из README. Старый import failure не считать runtime-дефектом и не оставлять blocker AC-LIT-02. |
| F-006 / OPEN | Backend version/health/recovery и прямой VPS доступ не подтверждены. | E-HTTP: static=main, API unauth 401; public /healthz Nginx 404. E-CD checkout sync не доказывает образ. P2; HIGH для ограничения. | E-STAB-02 подтверждает running version/image, internal health, backup rehearsal и safe smoke через CD. Прямой local SSH/персональный config owner остаются UNSET; это ограничение доступа, не outage. Обновить operational ownership в отдельном scope. |
| F-007 / OPEN | Нет source certification/Drive revision mapping всего банка и glossary. | E-CONTENT: 575/99 approved; source_ref(s) не обеспечивают per-item revision. E-SOURCE root inventory только первый уровень. AC-SRC-01–07/QUIZ-06. P1; HIGH. | IMPLEMENT recursive inventory/provenance validator и source-backed review; не переутверждать content по старым repository-evidence reports. |
| F-008 / OPEN | Length cues и содержательное качество банка требуют review. | E-CONTENT: 487/575 (84,70%) correct options uniquely longest; 21 severe cue; exact duplicate question/answer pairs проверены report. P2; HIGH для метрики, MEDIUM для педагогического дефекта. | FIX после source review, без искусственного padding; historical queue остаётся актуальной; E02/E03. |
| F-009 / DEFER | Подробные старые audit reports/RFC уже лежат в repo. | Inventory ниже; banners PR #282 снизили stale authority, raw snapshots всё ещё дублируют evidence. P2; HIGH. | CONSOLIDATE/архивировать в отдельной docs Goal по карте; сохранять unresolved IDs. Audit PR меняет только spec/plan. |
| F-010 / OPEN | Q-01–Q-08: продуктовые/технические решения ещё открыты. | Spec: account/linking, versioning, algorithms, literature mapping, optional scope, mail, source coverage/recovery. P1; HIGH. | DOCUMENT решения до соответствующей реализации; root ID уже установлен. Не трактовать неизвестный алгоритм как разрешение придумать policy. |
| F-011 / DEFER | Legacy m1-q3 и прежние optional content follow-ups. | E-CONTENT/tests, сохранённое решение старого плана. P3; HIGH. | DEFER переименование/новые batches/experimental difficulty до выбора scope; stable ID не является мусором. |
| F-012 / OPEN | Reading Tracker охватывает неполную библиографию и legacy statuses. | 42 review entries в 4 непустых Module 1 списках; пятый literature JSON пуст. Нет audio/outbound-reference полей; E-CONTENT. AC-LIT-01–03. P2; HIGH. | IMPLEMENT corpus-wide inventory + bibliographic verification; DOCUMENT mapping Q-04 до замены legacy states. |
| F-013 / OPEN — переаудирован | Незакрытые риски прежнего runner audit и browser coverage. | AUDIT-001–008 reconciled ниже; frontend tests — 32 source-string contracts; E-HTTP browser только без Telegram. P2; HIGH для test gap, MEDIUM для непроверенных UX failures. | FIX runtime DOM/network/concurrency tests в выбранном scope; не объявлять каждый старый риск воспроизведённым багом. |
| F-014 / OPEN | Поставка mutable main, слабые post-checks и stateful/recovery gaps. | deploy.sh: fetch/ff origin/main, lock может выйти 0 без доставки, проверка Running/logs; seed вызывается до rebuild при app/sql изменениях и может использовать старый image. Bootstrap reset --hard/remove-orphans. E-CD. P1; HIGH для кода, runtime applicability PARTIAL. | Core FIX выполнен #284/#285 + PR4: exact trusted SHA/CI gate, build-before-migration, fail-closed lock/target checks, verified backup/isolated restore, user preservation, snapshot/parity/health/image post-checks и forward-fix procedure. E-STAB-02/05. Осталось: build once/promote immutable artifact вместо VPS rebuild, отдельное user-data restore и backup retention policy (Q-08); отдельный scope, не blocker текущей согласованной additive поставки. |
| F-015 / OPEN | Невоспроизводимые transitive deps/build tooling. | requirements без lock; Actions tags, python:3.12-slim и npx wrangler без pinned version; CD permissions наследует repo default read. E-CODE/E-GH. P2; HIGH. | Actions checkout/setup-python и permissions закреплены #284/#285; FIX оставшиеся transitive/base image/wrangler lock inputs в tooling Goal; не объявлять фактический CD token write-capable без evidence. |
| F-016 / CLOSED | Исправление question/options искажает историю ответов. | E-REPRO: после upsert OLD CORRECT → NEW WRONG, recorded_correct=1/current_correct=0. schema references mutable content, snapshot/version отсутствует. AC-PROG-04/FND-06/QUIZ-07. P1; HIGH. | FIX выполнен в PR4 worktree: immutable snapshot v1/hash/provenance, API/classic feedback из attempt edition, additive backfill до seed; regression/migration/user preservation PASS (E-STAB-05). Ранее утраченные редакции не восстановимы; legacy_backfill_current не выдаётся за original. |
| F-017 / CLOSED | Снятие approval не исключает ранее seeded вопрос из выдачи; parity может пропустить проблему. | E-REPRO: approved → draft seed оставляет DB approved. db.upsert_approved_questions фильтрует вход; audit_question_bank относит canonical retired rows к informational без проверки DB status; existing test закрепляет это. AC-QUIZ-01/SRC-07. P1; HIGH. | FIX выполнен в PR4 worktree: full seed синхронизирует non-approved/removed IDs без удаления rows/history, partial helper не retire unspecified IDs. Serving parity блокирует non-approved-but-serving; E-STAB-05. Зависимость F-016 закрыта в том же diff. |
| F-018 / OPEN | Glossary state только в памяти без retention policy. | miniapp_glossary._SESSIONS, classic context.user_data; cleanup/TTL нет. Повтор одного restart теперь возвращает один child (#287); новые sessions/цепочки restart продолжают накапливаться. Ответы теряются при process restart, workers не делят state. AC-FND-08/GLO-02. P1; HIGH. | IMPLEMENT persistent personal term state и безопасный lifecycle по общей data model; до этого не масштабировать glossary несколькими workers. |
| F-019 / CLOSED | Повторный glossary next меняет варианты уже показанного вопроса. | E-REPRO: тот же term/order, correct index 3→1; прежний отображённый правильный ответ оценивается false. _safe_question вызывается вновь без stable step. AC-GLO-01/FND-07. P1; HIGH. | FIX stable question instance/step token и idempotent answer/next; regression duplicate/retry/cross-request tests. Выполнено: per-session lock и cached step/answer/next/restart; E-STAB-04. In-memory lifetime F-018 отдельно. |
| F-020 / CLOSED | Malformed quiz/glossary payloads вызывают 500; boolean category ID принимается. | E-REPRO: list в question_count/quiz_mode/difficulty и glossary count → 500; category_ids=[true] → 200 для category 1. set-membership до type guard, isinstance(bool,int). AC-QUIZ-02/LEG-03. P2; HIGH. | FIX #286: shared type/range guards, validation до profile/session writes; malformed/unknown categories/oversized IDs regression PASS, E-STAB-03. Auth bypass не обнаружен. |
| F-021 / CLOSED | Логи содержат raw Telegram user IDs вопреки AC-OPS-05. | miniapp_fastapi._log_request, handler_latency, classic handlers; synthetic log check TRUE. Реальные user IDs не извлекались. P2; HIGH. | FIX убрать или согласованно псевдонимизировать IDs; negative logging tests. Выполнено в #286: raw IDs убраны, negative logging tests PASS; E-STAB-03. |
| F-022 / CLOSED | Canonical unittest command неполон; tests непереносимы на Windows. | E-TEST: 281 pytest cases, 264 pass/16 fail/1 skip; 11 pytest-style tests не запускаются unittest (pytest отсутствует requirements). E-FIXTURE: 16/16 после временной fixture adaptation проходят. P2; HIGH. | FIX реализован в PR1 worktree: requirements-dev/pytest, explicit closing и portable fixtures. E-STAB-01/02: Windows suite PASS с одним Docker skip; Linux CI 35446748336/35447211955 включает Docker и весь pytest suite PASS; #284/#285 merged. Discovery/fixtures finding закрыт. |
| F-023 / OPEN | Известные advisories в resolved requirements. | E-DEPS: 16 записей = 8 уникальных advisory IDs: python-dotenv 1.0.1 (1), Starlette 0.46.2 (7). FastAPI 0.115.12 ограничивает Starlette <0.47.0. P2; HIGH для installed versions, MEDIUM для применимости. | FIX совместимый dependency upgrade/lock после reachability review; set_key, FileResponse/StaticFiles, form parsing/HTTPEndpoint не используются в app, остальные случаи проверить. Exploit production не доказан. |
| F-024 / OPEN | Coupling и точный dead duplicate повышают риск локальных изменений. | classic_quiz_handlers 1778 строк с dynamic _main_attr; main 1125, miniapp_api 1069, index.html 2542. _get_classic_reply_state определён идентично на 107/1266, первая binding замещена. Schema helpers дублированы в init_db/db/schema. P2; HIGH. | REFACTOR по границам domain/transport и одному migration owner; REMOVE только подтверждённый shadowed duplicate отдельным scope. Legacy HTTP adapter имеет consumers/tests/flag и не считается dead. |
| F-025 / OPEN | SQLite connection lifecycle и масштабирование не доказаны. | Classic handlers/main используют with get_connection без close (SQLite context завершает transaction); E-FIXTURE показывает Windows file handles до GC. ORDER BY RANDOM; API GET создаёт/обновляет user; JSON читается с диска на запрос. P2; HIGH для lifecycle, MEDIUM для нагрузки. | Explicit closing в handlers/main/entrypoint исправлен PR1 (E-STAB-01); performance/load измерять перед scale/PG migration, не придумывать SLO. Нет доказанного production bottleneck; duplicate indexes оценить перед удалением. |
| F-026 / OPEN | Большая часть целевой платформы не реализована. | E-CODE + AC registry: нет React/PWA, PG/pgvector, e-mail accounts/linking, repetition/personal analytics, knowledge/Obsidian/search, assignments, practice export, owner source dashboard; Reading Tracker частичен. P1; HIGH. | IMPLEMENT выбранными Goals по roadmap и зависимостям. Это agreed scope, не новые features из findings; optional 9 AC отдельно. |
| F-027 / OPEN | Supporting docs/config examples содержат stale детали. | README считает только unittest suite; .env.example не показывает dedicated API settings; runbook sections 9/12 всё ещё требуют MINIAPP_API_ENABLED для dedicated API, хотя flag относится к legacy in-bot server. Glossary coverage говорит 96 entries, actual 99. P2; HIGH. | README pytest и затронутые delivery/rollout процедуры обновлены в Goal. DOCUMENT/CONSOLIDATE оставшиеся .env/example, legacy API sections и glossary coverage по карте; отдельный scope. |
| F-028 / CLOSED | Frontend доверяет api_base_url из unsigned URL context и отправляет туда initData. | index.html: context из query/hash → apiBase без origin allowlist → Authorization/simple_body initData. Backend сам проверяет initData, но destination не закреплён. AC-OPS-05/LEG-03. P1; HIGH для dataflow, MEDIUM для exploitability. | FIX trusted endpoint configuration/allowlist и credential non-disclosure test. Выполнено в #286: publisher-owned config, origin/path/redirect guard и actual-fetch negative tests PASS; E-STAB-03. |

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

PLATFORM-STABILIZATION-001 активна; foundation #284/#285, API/privacy #286 и glossary #287 поставлены (E-STAB-02/03/04). Текущий PR4 `codex/stabilization-attempt-history`, base `7a5fdc94d25a503385d2d6bf3b1ec399b05f5703`: clean fresh origin/main, один worktree, open PR нет, main protections/rulesets отсутствуют. Ветка #287 удалена после merge/tree equivalence/CD/static проверки.

До реализации зафиксировано Q-02 решение: snapshot v1/hash/provenance в quiz_session_questions; additive/idempotent backfill до seed, неизменяемые answers/score; safe lifecycle sync и stale-serving blocker. Validation: content edit/reorder/correct-answer change/demotion/removal и seed retry, legacy migration, all quiz clients и recent feedback, users/literature invariants, full affected backend suite, real init/seed/parity, deployment backup/restore rehearsal и post-checks. Stateful class BACKWARD_COMPATIBLE_AUTOMATED: добавочные nullable columns совместимы со старой schema usage, writers остановлены на backup/migration; old app rollback не используется (старый код не читает snapshots), recovery только forward-fix без production restore. Массовое изменение content не входит в PR.

PR4 реализован, code self-review и local validation выполнены (E-STAB-05); остаются CI/review актуального head, merge и exact-revision stateful CD. До последнего push Goal остаётся IN_PROGRESS: если primary records подтвердят merge, backup/isolated restore, USER_STATE_PRESERVED, snapshot/CONTENT_PARITY_OK, DB/HTTP smoke, обе Running images на merge SHA и безопасную очистку своей ветки, DoD этой Goal выполнен; иначе сохранить blocker и продолжить forward-fix. Metadata-only follow-up PR не требуется. После DoD остановиться для выбора PWA Goal. Readiness snapshot не пересчитывать.
