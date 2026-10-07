# PostgreSQL storage

## Подготовленная миграция чтения v8

В текущей локальной Goal подготовлен additive `postgres-v8`: [work-level reading DDL](../sql/reading-work-v1.sql) и [migration planner](../app/reading_schema.py). Прежние `user_literature_progress` строки и все их поля остаются историей без перезаписи. Новые отметки принимают четыре статуса и выбираются по последней подтверждённой отметке одного catalog work. Конфликт одинаковых/невалидных timestamps останавливает переход.

Canonical init выполняет upgrade под прежними writer-stop/backup/restore/lock preconditions. [Preservation manifest](../app/postgres_recovery.py) сверяет исходные строки и exact derived projection новых work rows, columns и catalog mapping digest; общий запрет произвольных новых user rows сохраняется. Проверка старых schema hashes v1–v7 остаётся неизменной. Fresh initialization и импорт прежних SQLite versions используют отдельные ветви, не усыновляют неизвестный namespace и не переносят повторно отметки поверх текущего состояния.

Это подготовленный код, не evidence production migration. Runtime/client переход и включение новых work rows в подтверждённое actor deletion реализованы локально в PR2; PostgreSQL CI и production delivery ещё не подтверждены. Фактические CI/CD records находятся в [плане](delivery-plan.md). Helper не запускать отдельно на VPS.

PostgreSQL 18.6, psycopg 3.3.6. Production cutover выполнен 20.09.2026; его Evidence и первичные records — в [delivery plan](delivery-plan.md). Раздел подготовки ниже нужен только для нового согласованного cutover; для последующих изменений используется обычный CD. Фактическая версия восстанавливается по CI/CD records и host phase record.

## Выбор БД и контракт

`DATABASE_URL` — PostgreSQL URI с явными host, user и database; непустое значение имеет приоритет над `DB_PATH`. При отсутствии URI действует прежний SQLite `DB_PATH`. Неверный URI, ошибка подключения или неизвестная схема не вызывают fallback. `.env` загружается canonical entrypoints без переопределения уже заданного process environment. Factory с явно переданным target использует именно его, что сохраняет изоляцию tests. Credentials хранятся только в runtime environment; не передавайте URI через CLI arguments, PR или logs.

Имя поля `Settings.db_path` сохранено для совместимости вызывающего кода; оно может содержать PostgreSQL target и исключено из repr. Лог старта не выводит target. [DB boundary](../app/database.py) адаптирует параметры, rows и транзакции; dialect SQL расположен в domain/schema call sites. PostgreSQL driver exceptions заменяются безопасным SQLSTATE без SQL, values или credentials.

Целевая schema текущей локальной ветки — `postgres-v9`; version/ordered migration steps определяет [schema owner](../app/postgres_schema.py). Live version определяется readiness и первичными delivery records, а не этой страницей. Базовая [postgres-v1](../sql/postgres-v1.sql) и версии v1–v8 сохраняют прежние DDL hashes. Additive v9 добавляет [Google identity/challenges](../sql/google-oauth-v1.sql) без изменения accounts, sessions и учебных rows; новая migration подтверждается в required CI и preservation gates до поставки. Начиная с v2 добавлена [glossary-v1](../sql/glossary-v1.sql), далее — learning, invitations (сохранённая legacy schema), profile, homework, privacy и work-level reading. Сохраняются integer flags, UTC TEXT timestamps, IDs, FK/unique constraints и immutable snapshots. `glossary_sessions` хранит фиксированные вопросы/варианты/definitions и личные ответы/результат; один actor имеет не более одной активной glossary attempt. Старые завершённые/заменённые attempts сохраняются до явного learning reset; автоматическая retention policy не вводится. Runtime startup проверяет marker, hash canonical DDL и catalog signature, но не выполняет DDL.

Auth transactions сериализуются scope `auth`; setup/answer — `actor:<users.id>`. Порядок при совмещении: auth → actor → content. Content publication и capture вопроса вместе с options используют `content`, чтобы попытка не смешивала две редакции. Locks транзакционные; commit/rollback освобождает их. PostgreSQL isolation — READ COMMITTED, lock timeout 10 seconds; read-only content audit использует REPEATABLE READ. SQLite сохраняет BEGIN IMMEDIATE. Нет connection pool или нового throughput/SLO обещания.

## Команды хранения

Рабочий каталог — корень, Python 3.12 с [requirements-dev](../requirements-dev.txt), заданный приватно `DATABASE_URL`. Новая DB/role и права на её schema должны быть подготовлены владельцем окружения. Не запускайте эти команды на неизвестной БД.

| Операция | Команда и результат |
| --- | --- |
| Пустая схема | `python scripts/postgres_storage.py init` — создаёт целевую schema текущего кода только в пустом namespace; текущую проверяет; известная прежняя schema требует canonical upgrade, неизвестную не принимает |
| Проверка | `python scripts/postgres_storage.py check` — read-only version/catalog drift verification |
| Импорт | `python scripts/postgres_storage.py import --source <offline-snapshot.sqlite3> --report <new-report.json>` — атомарный импорт в пустой target, row/sequence reconciliation; report содержит counts/hashes, без содержимого user rows |
| Init/seed | Canonical команды в [README](../README.md#быстрый-старт-и-проверки). PostgreSQL init проверяет текущую schema либо транзакционно обновляет проверенную известную прежнюю версию через ordered steps; seed обновляет canonical content с сохранением snapshots. SQLite init применяет явные migrations актуального кода, включая work-level reading, после проверки legacy schema |
| Content parity | `python scripts/audit_question_bank.py --configured-database` — read-only audit выбранной БД. Legacy JSON key `sqlite` сохранён для consumers, поле `backend` определяет БД. PostgreSQL catalog check не выдаётся за SQLite physical integrity check |

Источник импорта: отдельный завершённый SQLite snapshot после остановки writers, с `identity-v1`/`auth-v1` и полными snapshots. Импорт не выполняет upgrade исходника. Проверяются integrity/FK, полный набор таблиц/колонок, snapshot digest/provenance и версии. Неизвестные таблицы/колонки, пропущенные migrations или повреждённые данные — отказ. Source открыт read-only в одной read transaction.

IDs копируются явно; PostgreSQL sequences продолжаются выше максимума сохранённых IDs и SQLite high-water marks, включая удалённые IDs. Проверка сравнивает counts и hashes всех строк/полей независимо от порядка выдачи. Обычные timestamps и JSON bytes сохраняются без нормализации. Ошибка откатывает inserts/DDL; изменение sequence при ошибке на заранее созданной пустой схеме не трактуется как импортированные данные и задаётся повторно при retry. Источник не изменяется.

Успешный повтор допускается только при совпадении source manifest, target rows и sequences. После новых runtime writes повторный import отказывается перезаписывать target. Report write может отдельно завершиться ошибкой после commit — сначала повторите проверку состояния/import с новым report path; не очищайте target. Отсутствие report само по себе не доказывает отсутствие commit.

На target таблицы берутся ACCESS EXCLUSIVE locks до проверки пустоты и до reconciliation/sequence reset. Неожиданный writer может заблокировать/сорвать операцию; locks не заменяют обязательную остановку обоих runtime writers перед cutover.

## Воспроизводимые проверки

Нужен изолированный PostgreSQL 18.6 и отдельная test database с именем `psychology_test...`. У login role должны быть CONNECT/CREATE на эту DB; superuser для behavioral tests запрещён. `POSTGRES_TEST_DSN` содержит только URI test DB без query options. Fixtures создают UUID schema и удаляют только её; production data не используются.

| Проверка | Команда / условия |
| --- | --- |
| Реальная БД | `python -m pytest tests/postgres -q` из root; перед запуском обязателен `POSTGRES_TEST_DSN`. Без него эта suite отмечается skip и PostgreSQL validation не выполнена |
| Полная совместимость | `python -m pytest -q` из root с тем же target — SQLite suite и PostgreSQL migration/auth/quiz/concurrency suite. Docker contract проверяется в CI; local skip при отсутствии Docker остаётся явным ограничением |
| Browser | Canonical `npm run test:e2e` из `pwa/` при заданном `POSTGRES_TEST_DSN` — synthetic SQLite fixture импортируется в PostgreSQL; desktop/mobile auth/link/quiz/recovery/retry. Без переменной используется прежняя SQLite fixture |

CI сохраняет jobs `validate-and-smoke-test` и `pwa-client`, triggers/revision/permissions прежние. У каждого job свой ephemeral PostgreSQL service; image tag 18.6-bookworm закреплён digest в [workflow](../.github/workflows/ci.yml). Источник версии/digest: официальный docker-library manifest и Docker registry, проверены 20.09.2026. CI-only helper [postgres_test_support](../scripts/postgres_test_support.py) создаёт limited test role; его admin credentials синтетические и не используются на VPS. Browser job собирает frontend один раз и проверяет обе БД. Required CI success и exact main delivery остаются обязательными по [AGENTS](../AGENTS.md).

Native Windows local validation использует PostgreSQL 18.6 с официального EDB binary package, loopback-only порт, private temporary data directory и роль без superuser. Это test environment, не новая product/GitHub Environment и не подтверждение состояния VPS.

Native recovery tests: `python -m pytest tests/postgres/test_recovery.py -q` из root. Кроме `POSTGRES_TEST_DSN`, нужны loopback `POSTGRES_TEST_ADMIN_DSN` той же test instance и `POSTGRES_TEST_NATIVE_BIN` с клиентами 18.6; в CI вместо bin используется `POSTGRES_TEST_CONTAINER` ephemeral service. Admin применяется только для создания/удаления уникальных test databases; application manifest читается limited role. Проверки выполняют настоящий custom-format dump/restore, сверяют все таблицы/поля, schema marker и sequences; повреждённый dump не проходит, исходник остаётся прежним. Без этих условий local skip не является recovery PASS. CI также запускает actual Compose profile на отдельном UUID project и private temporary bind directory, проверяет secret mount, SCRAM/checksums и отсутствие host port, затем удаляет только свои test resources.

## Production target и ownership

| Объект | Контракт |
| --- | --- |
| Host / checkout | VPS `167.86.68.98`, root operator, `/opt/psychology-quiz`, чистый `main` / fetched `origin/main`, exact validated SHA. Прямого SSH агента нет; оператор работает через MobaXterm |
| Application unit | Compose project `psychology-quiz`, `psych_quiz_bot` и `psych_quiz_miniapp_api`. Обе службы — writers; остановка одной недостаточна |
| PostgreSQL | Профиль `postgres`, service `psych_quiz_postgres`; pinned 18.6-bookworm image в [Compose](../docker-compose.yml). DB `psychology_atlas`, login `psychology_app`, NOSUPERUSER/NOCREATEDB/NOCREATEROLE, без replication/bypassrls; owner только собственной DB |
| Network / storage | Только Compose network `psychology-quiz_default`; DB port не публикуется. Bind `/opt/psychology-quiz/.postgres/data` → `/var/lib/postgresql` (PG18 layout), mount root UID/GID 999 и mode 0700; checksums on. Родитель `.postgres/` остаётся root-owned 0700. `.postgres/` исключён из Git/build context; app services его не монтируют |
| Config owner | root operator владеет `.env`, `.postgres/` и state record; private data mount принадлежит container UID 999. `.env` должен быть private regular root-owned file. `DATABASE_URL` генерирует процедура; остальные env bytes/owner/mode сохраняются. `DB_PATH` остаётся для исходного SQLite, после переключения не выбирается |
| Credentials | `.postgres/` mode 0700, `app.password` 0600/root; admin secret 0400/uid 999 (проверяется по pinned image), читается только DB container и root. Секреты создаются один раз, не выводятся/не ротируются при retry. DSN передаётся ephemeral app через environment, не аргумент CLI |
| Serialization | Общий `/tmp/psychology-quiz-deploy.lock`; operator fail-fast, routine CD ждёт по [deploy](../deploy.sh). Нельзя параллельно менять env, запускать seed/import или отдельный writer |
| Delivery identity | Existing GitHub Environment `production`, SSH target и protections — [deployment runbook](miniapp-deployment-qa.md). DB profile — runtime resource, не новый GitHub Environment. Точный app image label/SHA проверяется до операций и после старта |

Actual host resources, свободное место и ownership до preflight — UNSET. `preflight` требует reserve не меньше max(1 GiB, 8× SQLite size); перед PG backup — max(1 GiB, 3× pg_database_size). Это ограниченная защита операции, не обещание capacity/SLO: dump и отдельная восстановленная DB временно сосуществуют. Не удалять старые backups ради прохождения проверки без отдельного maintenance scope.

## Подготовка и cutover на VPS

Класс — EXPLICITLY_GATED: создание private DB resources и перенос данных выполняет root operator в согласованной Goal, после PR CI/merge и обычного CD этой revision. Routine CD сам не запускает prepare/cutover. `EXPECTED_SHA` ниже — точный SHA успешного CD; не подставлять произвольную ветку или ещё не проверенный commit.

```bash
cd /opt/psychology-quiz
python3 scripts/postgres_vps.py preflight --expected-sha "$EXPECTED_SHA" </dev/null
python3 scripts/postgres_vps.py prepare --expected-sha "$EXPECTED_SHA" </dev/null
python3 scripts/postgres_vps.py cutover --expected-sha "$EXPECTED_SHA" </dev/null
python3 scripts/postgres_vps.py status --expected-sha "$EXPECTED_SHA" </dev/null
```

Запускать последовательно с `set -Eeuo pipefail`, останавливаясь на первой ошибке. Перед первой командой обновить только remote refs и проверить, что HEAD, origin/main и `EXPECTED_SHA` совпадают; checkout уже синхронизирует штатный CD. Не делать reset/clean/pull поверх неизвестных изменений. Проверить account/host, окончание текущего CD и root identity. Будущему CD тоже нужен root для private PostgreSQL records; фактический SSH account подтвердить по job/operator evidence до переключения, не раскрывая credentials.

Operator CLI не принимает stdin; `</dev/null` явно отделяет его от следующих строк при запуске через Bash heredoc. Внутри скрипта обычные subprocess также получают EOF; SQL/manifest bytes и archive file stream передаются только явно. `POSTGRES_PREFLIGHT_OK` подтверждает только preflight: без `POSTGRES_PREPARED`/`POSTGRES_CUTOVER_OK` следующие этапы не считаются выполненными. После неоднозначного прерывания сначала проверить наличие state record и выполнить `status`, не повторять запись вслепую.

`prepare` проверяет действующие SQLite containers, их revision/data mounts и private config, создаёт только новые `.postgres` resources, поднимает pinned profile и проверяет network/storage/checksums/version. Создаёт отдельную role/DB и пустую schema. SQLite writer containers и `.env` пока прежние. Неизвестный существующий container/path/cluster/schema не принимается за результат этой работы; несовместимое состояние требует разбора.

PG18 использует вложенный `PGDATA`: entrypoint назначает владельца вложенному каталогу, но не корню bind mount. Поэтому `prepare` при phase `allocated` перед запуском назначает только `.postgres/data` UID/GID 999, сохраняя mode 0700, и проверяет readback. Это также исправляет прерванную allocation прежней версии с root-owned 0700 mount. Известные private state/credentials сохраняются; recursive chown, сброс cluster и очистка данных не выполняются. Symlink, иной owner, широкие права или root-owned mount после `allocated` вызывают отказ. Уже исправленный каталог не меняется при retry.

`cutover` сохраняет private копию `.env`, останавливает оба writers, создаёт SQLite backup через online backup API и репетирует его restore. Импортирует этот неподвижный snapshot, сверяет все rows/IDs/sequences и content parity. Затем создаёт PostgreSQL dump, восстанавливает его в новую `psychology_restore_<UUID>` DB, сравнивает полный manifest и удаляет только собственную restore DB. Исходные SQLite и PG runtime DB не являются restore targets.

Только после этих checks атомарно меняется `DATABASE_URL` в `.env`. Before-start phase записывается и fsync выполняется до запуска PG writers. Запускаются оба existing app images exact revision. Post-checks: работающий image SHA, выбранный private PG target у обеих служб, `/healthz`, DB-backed `/readyz` с revision/backend/version, anonymous Telegram/PWA auth boundaries; expected PASS markers и `.postgres/state.json` фиксируют результат. После operator результата обязательны bounded public PWA check и восстановление owner session/attempt; ответы пользователя не подменять тестовыми без соответствующего поручения.

## Прерывание, retry и recovery

State record `.postgres/state.json` содержит phase, revision/cluster identity, source snapshot digest/import report, native recovery record и конечные image IDs. Records private, без raw rows/credentials. Сохранять последний phase и error type; `.env`, passwords и user data в чат/Actions logs не копировать.

| Phase | Следующее действие |
| --- | --- |
| `allocated` / `database_started` | Сверить сохранённые private files/cluster, затем повторить `prepare` той же проверенной revision. Role/password не пересоздаются; неизвестный partial directory без валидного record — остановка и разбор |
| `prepared` | `cutover` после успешного preflight; пока SQLite остаётся runtime |
| `stopping` … `recovery_verified` | Оба writers остаются остановленными при failure. Исправить причину и повторить `cutover` с тем же SHA. Существующий snapshot/import проверяется; target не очищается. Изменившийся source/target/config вызывает отказ |
| `configured` / `postgres_writers_starting` | Считать PG writes возможными. Retry продолжает только PG, без повторного import/возврата `.env` к SQLite. При ошибке остановить дальнейшее продвижение и forward-fix; production restore требует отдельной проверенной процедуры |
| `complete` | Повтор `cutover` только проверяет состояние; не переносит данные заново. `status` — чтение record, само по себе не live health evidence |

Автоматического SQLite rollback нет даже до первых PG writes: процедура сохраняет остановленное состояние для контролируемого retry. Если владелец выбирает возврат до этой границы, сначала отдельно доказать отсутствие PG writers, неизменность SQLite и совместимость app/config; после PG writes старый SQLite уже не recovery target. Production restore/drop/volume cleanup и удаление source/backups не реализованы этой командой.

Backup record `.postgres/backups/release-*/record.json`: cluster/database/revision identity, SHA-256/size native dump, полный source manifest, restore phase и cleanup. `verified` означает реальный isolated restore + совпадение всех строк/schema/sequences при остановленных writers. После uncertain CREATE хранится generated restore name; сначала проверить actual existence/owner и record, не создавать/удалять DB вслепую. Failed rehearsal не разрешает migration. При process kill restore DB может остаться; cleanup выполняется отдельно только после проверки принадлежности.

## Обычный CD после переключения

[deploy.sh](../deploy.sh) получает backend из candidate config; неизвестный/внешний PostgreSQL target отклоняется. Перед stateful migration останавливает оба writers, вызывает host `postgres_vps.py backup --lock-held`, затем init/seed и `verify --record ...` под унаследованной lock. Последняя команда сверяет cluster/revision/dump identity и весь прежний user/auth state; content changes допустимы отдельно. Для SQLite остаётся прежняя backup API procedure. После начала migrations нет автоматического data restore/app rollback.

Любой поддержанный переход выполняется в этом же stopped-writer flow: preflight и native backup/isolated restore сначала проверяют известную исходную schema, canonical init под schema lock атомарно применяет ordered migrations и обновляет version/hash/catalog. После миграции readiness и smoke требуют целевую версию кода. Preservation сверяет все прежние user/auth rows, sequences и import provenance. Новые user tables должны быть пустыми; единственное описанное исключение для reading v8 — точный projection, заранее выведенный из сохранённых legacy строк и проверенного catalog mapping. Иная неожиданная новая строка, drift/unknown schema или failed backup/restore останавливают поставку. Последующие backups включают новую личную таблицу. Import неподвижного SQLite snapshot сохраняет поддержанную исходную schema либо проверенно переносит legacy v5–v7 в пустой current target; новые runtime writes запрещают повторную загрузку. Import не является production recovery или способом перезаписать историю.

`/readyz` проверяет существующий SQLite или version/catalog PostgreSQL и выполняет реальное чтение; unavailable/schema drift → 503 без DSN/raw errors. `/healthz` остаётся лёгкой process/version проверкой. Stateful classifier охватывает DB boundary/schema/import changes и canonical content; `.dockerignore` считается runtime input. SQL/schema compatibility для последующих schema versions всё равно требует отдельного reviewed migration — автоматического неизвестного DDL нет.

D-47 задаёт локальным DB backups 30 дней с сохранением minimum2/recovery exceptions. Ниже read-only план; очистка ещё не внедрена. Ручные VPS snapshots отдельно управляются владельцем в панели провайдера; новый off-host backup не поручен. RPO/RTO, off-host copy, HA и масштабная нагрузка — UNSET, обязательства по ним не вводятся без согласованного требования. Bounded restore rehearsal не доказывает восстановление всей VPS или готовность к неизвестному объёму пользователей.


## Read-only план хранения резервных копий

Canonical inspector — [backup_retention_plan.py](../scripts/backup_retention_plan.py). Он только читает отдельные `release-*` records и проверяет `database.dump` по размеру/SHA-256; операций удаления и production restore нет. Не использовать mtime как дату verified backup. Новые [backup records](../scripts/postgres_backup.py) сохраняют `created_at` и `verified_at` в UTC; старые records без этих полей по-прежнему пригодны для verified recovery, но inspector оставляет их на ручную проверку.

На VPS из `/opt/psychology-quiz`, root, без вывода содержимого БД/DSN:

```bash
flock -n /tmp/psychology-quiz-deploy.lock python3 scripts/backup_retention_plan.py \
  --backup-root /opt/psychology-quiz/.postgres/backups --retention-days 30
```

Без `--retention-days` срок UNSET, кандидатов к очистке нет. В команде выше указан согласованный срок 30 дней; она не удаляет файлы. Для recovery point, которым пользуется активная процедура, добавить `--pin-record` с его `record.json`; внешние пути отклоняются. Минимум две новейшие проверенные точки каждого кластера остаются независимо от срока. Failed/unknown records, symlinks, повреждённые dumps, несовместимые identities и недостоверные даты сохраняются. `REVIEW_CANDIDATE` означает только необходимость операторского review с учётом незавершённых recovery records; automatic cleanup не внедрён. Снимок отражает момент проверки, не состояние после освобождения lock. Срок согласован D-47, фактическая очистка и её Evidence ещё не выполнены; никакой RPO/RTO этот инструмент не устанавливает.


## Подготовленная очистка локальных DB backups

[backup_retention.py](../scripts/backup_retention.py) применяет D-47 только к /opt/psychology-quiz/.postgres/backups, под общей deploy lock. Без --apply только план; с --apply --expected-sha <проверенная-revision> проверяются чистая main/exact origin и удаляются лишь известные record.json/database.dump units из свежего перепроверенного плана. Новый unit с unknown файлами, небезопасными paths/permissions, повреждённым dump, unfinished recovery или конфликтом плана не удаляется. Минимум две verified точки каждого cluster и control-record pins сохраняются. Recovery records, live DB и полные VPS snapshots не удаляются. Частичный сбой не считать успешной очисткой.

Код подготовлен локально; production применение пока PENDING. Перед --apply нужны проверенная поставленная revision и read-only review точного плана. Для автоматического запуска подготовлен scoped systemd timer; его установка на VPS ещё PENDING. Application/Nginx logs и переданные копии обрабатываются отдельно.


## Ежедневный запуск локальной очистки

[Установщик](../scripts/install_backup_retention.py) обслуживает только
`/etc/systemd/system/psychology-quiz-backup-retention.service` и
`/etc/systemd/system/psychology-quiz-backup-retention.timer` на том же VPS.
Timer запускается ежедневно с 03:00 UTC и случайной задержкой до 30 минут.
Сервис не создаёт off-host backup и не управляет ручными VPS snapshots.

Canonical [deploy](../deploy.sh) выполняет read-only preflight перед остановкой
приложения, а установку — после проверки runtime и публикации PWA, только для
PostgreSQL. Неизвестные/чужие units, overrides или незавершённое recovery блокируют
поставку; существующие настройки других проектов не перезаписываются.
Установка не запускает очистку немедленно. При ошибке timer post-check
восстанавливаются прежние два unit files и enabled/active state; база не откатывается,
`DEPLOY_OK` не выдаётся. Ошибка восстановления требует operator reconciliation.

Scheduled cleanup сверяет clean main, exact origin и ancestry установленной
revision; при последующих documentation-only commits используется текущая main.
Общая deployment lock исключает очистку во время поставки. Неизвестные recovery
records/повреждённые copies сохраняются, даже если поэтому срок превышает 30 дней;
оператор должен разобраться с причиной. При остановке сервиса/таймера срок тоже
не гарантирован. Minimum2 и pinned exceptions не являются новой гарантией RPO/RTO.

Для bounded readback после поставки: из `/opt/psychology-quiz` проверить
`systemctl is-enabled psychology-quiz-backup-retention.timer` и
`systemctl is-active psychology-quiz-backup-retention.timer`, затем
`python3 scripts/backup_retention.py` (read-only). Фактический scheduled run
проверяется по systemd service result; чужие журналы и private dump contents
не публикуются. Контракт установки и восстановления проверяется
[адресными tests](../tests/test_install_backup_retention.py), порядок/failure
поставки — [shell contract](../tests/test_deploy_production_contract.py).

Согласование сроков D-47 само по себе не подтверждает установку этих privileged
units и выполнение cleanup: для текущего пакета нужны разрешённая поставка и
runtime Evidence. Полные VPS snapshots остаются под ручным управлением владельца.
