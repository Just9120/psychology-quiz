# PostgreSQL storage

Подготовительная часть [POSTGRES-MIGRATION-001](delivery-plan.md#current-goal--postgres-migration-001). PostgreSQL 18.6, psycopg 3.3.6; текущий production остаётся на SQLite до отдельного cutover. Эта страница описывает код и изолированные проверки. Production bootstrap, backup/restore и cutover процедуры ещё не поставлены; `deployment_db.py` блокирует PostgreSQL delivery в этой подготовительной версии.

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

Native Windows local validation использует PostgreSQL 18.6 с официального EDB binary package, loopback-only порт, private temporary data directory и роль без superuser. Это test environment, не новая product/GitHub Environment и не подтверждение состояния VPS. Production target/config/backup/cutover остаются следующей частью той же Goal.
