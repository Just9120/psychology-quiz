# PostgreSQL storage

Процедура [POSTGRES-MIGRATION-001](delivery-plan.md#current-goal--postgres-migration-001). PostgreSQL 18.6, psycopg 3.3.6. Production остаётся на SQLite до отдельного operator cutover; наличие кода и успешный обычный CD не означают, что PostgreSQL уже включён. Фактическая поставка восстанавливается по CI/CD records и host phase record.

## Выбор БД и контракт

`DATABASE_URL` — PostgreSQL URI с явными host, user и database; непустое значение имеет приоритет над `DB_PATH`. При отсутствии URI действует прежний SQLite `DB_PATH`. Неверный URI, ошибка подключения или неизвестная схема не вызывают fallback. `.env` загружается canonical entrypoints без переопределения уже заданного process environment. Factory с явно переданным target использует именно его, что сохраняет изоляцию tests. Credentials хранятся только в runtime environment; не передавайте URI через CLI arguments, PR или logs.

Имя поля `Settings.db_path` сохранено для совместимости вызывающего кода; оно может содержать PostgreSQL target и исключено из repr. Лог старта не выводит target. [DB boundary](../app/database.py) адаптирует параметры, rows и транзакции; dialect SQL расположен в domain/schema call sites. PostgreSQL driver exceptions заменяются безопасным SQLSTATE без SQL, values или credentials.

Схема [postgres-v1](../sql/postgres-v1.sql) сохраняет integer flags, UTC TEXT timestamps, IDs, FK/unique constraints и immutable snapshots. Это перенос хранения, а не изменение API или формата данных. PostgreSQL DDL выполняется только явно. Runtime startup проверяет marker, hash canonical DDL и catalog signature колонок, constraints, indexes, trigger/function и sequence settings. SQLite additive migrations продолжают действовать только на SQLite.

Auth transactions сериализуются scope `auth`; setup/answer — `actor:<users.id>`. Порядок при совмещении: auth → actor → content. Content publication и capture вопроса вместе с options используют `content`, чтобы попытка не смешивала две редакции. Locks транзакционные; commit/rollback освобождает их. PostgreSQL isolation — READ COMMITTED, lock timeout 10 seconds; read-only content audit использует REPEATABLE READ. SQLite сохраняет BEGIN IMMEDIATE. Нет connection pool или нового throughput/SLO обещания.

## Команды хранения

Рабочий каталог — корень, Python 3.12 с [requirements-dev](../requirements-dev.txt), заданный приватно `DATABASE_URL`. Новая DB/role и права на её schema должны быть подготовлены владельцем окружения. Не запускайте эти команды на неизвестной БД.

| Операция | Команда и результат |
| --- | --- |
| Пустая схема | `python scripts/postgres_storage.py init` — создаёт schema v1 только в пустом namespace; известную проверяет; чужую не принимает |
| Проверка | `python scripts/postgres_storage.py check` — read-only version/catalog drift verification |
| Импорт | `python scripts/postgres_storage.py import --source <offline-snapshot.sqlite3> --report <new-report.json>` — атомарный импорт в пустой target, row/sequence reconciliation; report содержит counts/hashes, без содержимого user rows |
| Init/seed | Canonical команды в [README](../README.md#быстрый-старт-и-проверки). На PostgreSQL init только проверяет schema; seed обновляет canonical content с сохранением snapshots |
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
| Network / storage | Только Compose network `psychology-quiz_default`; DB port не публикуется. Bind `/opt/psychology-quiz/.postgres/data` → `/var/lib/postgresql` (PG18 layout), checksums on. `.postgres/` исключён из Git/build context; app services его не монтируют |
| Config owner | root operator владеет `.env`, `.postgres/` и state record. `.env` должен быть private regular root-owned file. `DATABASE_URL` генерирует процедура; остальные env bytes/owner/mode сохраняются. `DB_PATH` остаётся для исходного SQLite, после переключения не выбирается |
| Credentials | `.postgres/` mode 0700, `app.password` 0600/root; admin secret 0400/uid 999 (проверяется по pinned image), читается только DB container и root. Секреты создаются один раз, не выводятся/не ротируются при retry. DSN передаётся ephemeral app через environment, не аргумент CLI |
| Serialization | Общий `/tmp/psychology-quiz-deploy.lock`; operator fail-fast, routine CD ждёт по [deploy](../deploy.sh). Нельзя параллельно менять env, запускать seed/import или отдельный writer |
| Delivery identity | Existing GitHub Environment `production`, SSH target и protections — [deployment runbook](miniapp-deployment-qa.md). DB profile — runtime resource, не новый GitHub Environment. Точный app image label/SHA проверяется до операций и после старта |

Actual host resources, свободное место и ownership до preflight — UNSET. `preflight` требует reserve не меньше max(1 GiB, 8× SQLite size); перед PG backup — max(1 GiB, 3× pg_database_size). Это ограниченная защита операции, не обещание capacity/SLO: dump и отдельная восстановленная DB временно сосуществуют. Не удалять старые backups ради прохождения проверки без отдельного maintenance scope.

## Подготовка и cutover на VPS

Класс — EXPLICITLY_GATED: создание private DB resources и перенос данных выполняет root operator в согласованной Goal, после PR CI/merge и обычного CD этой revision. Routine CD сам не запускает prepare/cutover. `EXPECTED_SHA` ниже — точный SHA успешного CD; не подставлять произвольную ветку или ещё не проверенный commit.

```bash
cd /opt/psychology-quiz
python3 scripts/postgres_vps.py preflight --expected-sha "$EXPECTED_SHA"
python3 scripts/postgres_vps.py prepare --expected-sha "$EXPECTED_SHA"
python3 scripts/postgres_vps.py cutover --expected-sha "$EXPECTED_SHA"
python3 scripts/postgres_vps.py status --expected-sha "$EXPECTED_SHA"
```

Запускать последовательно с `set -Eeuo pipefail`, останавливаясь на первой ошибке. Перед первой командой обновить только remote refs и проверить, что HEAD, origin/main и `EXPECTED_SHA` совпадают; checkout уже синхронизирует штатный CD. Не делать reset/clean/pull поверх неизвестных изменений. Проверить account/host, окончание текущего CD и root identity. Будущему CD тоже нужен root для private PostgreSQL records; фактический SSH account подтвердить по job/operator evidence до переключения, не раскрывая credentials.

`prepare` проверяет действующие SQLite containers, их revision/data mounts и private config, создаёт только новые `.postgres` resources, поднимает pinned profile и проверяет network/storage/checksums/version. Создаёт отдельную role/DB и пустую schema. SQLite writer containers и `.env` пока прежние. Неизвестный существующий container/path/cluster/schema не принимается за результат этой работы; несовместимое состояние требует разбора.

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

`/readyz` проверяет существующий SQLite или version/catalog PostgreSQL и выполняет реальное чтение; unavailable/schema drift → 503 без DSN/raw errors. `/healthz` остаётся лёгкой process/version проверкой. Stateful classifier охватывает DB boundary/schema/import changes и canonical content; `.dockerignore` считается runtime input. SQL/schema compatibility для последующих schema versions всё равно требует отдельного reviewed migration — автоматического неизвестного DDL нет.

Backup retention/RPO/RTO, off-host copy, HA и масштабная нагрузка — UNSET/outside этой Goal. Bounded restore rehearsal не доказывает восстановление всей VPS или готовность к неизвестному объёму пользователей.
