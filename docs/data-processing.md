# Обработка учебных данных

## Охват и основание

Актуальная сверка 07.10.2026: source baseline `ec486700`, runtime `09a9cef`; retention уже поставлен в runtime CD 37598614074, повторный source sync CD 37607504612 не менял runtime; работа относится к AC-PRIV-01/02/05. Ранее выполненный разбор 29–30.09 сохранён ниже как основание карты потоков. Это карта обработки, а не новая политика или заключение о соответствии закону. Действующий Telegram/Mini App использует Telegram Standard Bot Privacy Policy; адрес хранится в интерфейсе и `TELEGRAM_PRIVACY_POLICY_URL` в [боте](../app/main.py). Первичный документ прочитан 29.09.2026: разделы 4–7 охватывают получение данных, необходимые цели, защиту и обращения пользователей. Доступная ссылка сама по себе не доказывает выполнение этих правил.

## Установленные условия размещения

06.10.2026 владелец подтвердил в чате: страна размещения VPS — Франция.
Основание — сведения владельца; договор провайдера и фактическая инфраструктура
отдельно не проверены. Это не устанавливает страны обработки Telegram, Google,
SMTP и Cloudflare.

07.10.2026 владелец сообщил: управление из России, пользователи могут находиться в разных странах. По D-52 подготовка правовых изменений остановлена; БД не переносится, уведомления и новые формы не добавляются. Эта отсрочка не является заключением о соответствии или неприменимости закона.

07.10 владелец согласовал D-47 в [spec](project-spec.md): DB backups30 дней с minimum2/recovery exceptions, собственные application/Nginx logs14 дней, переданная копия7 дней. Дополнительный VPS/облачный backup не поручен. Ручные VPS snapshots отдельно управляются владельцем; их фактическая retention UNSET.

Поставка кода и post-check retention timer подтверждены CD 37598614074; это не доказательство удаления каждого конкретного файла или фактических сроков внешних сервисов. Заявителя проверяет владелец по известному контакту либо лично; передача на подтверждённый адрес — по явному запросу. Один Telegram ID/username недостаточен. Разработчик обозначен по D-48 как «Владелец PsychologyAtlas» с опубликованным e-mail; ручной порядок для owner PWA согласован D-49; внешние provider settings остаются неподтверждёнными. Владелец read-only проверкой подтвердил два access_log off и error_log /dev/null для сайта; application logs/copies/backups регулируются поставленной процедурой.

## Данные и цели

| Поток | Данные и цель | Подтверждение и ограничения |
| --- | --- | --- |
| Telegram → bot/API → runtime DB | Telegram ID и переданные имя/username связывают личные попытки. Ответы, результаты, история повторений, цели, достижения и отметки книг сохраняют обучение. Telegram не требует e-mail/пароля приложения. | [DB](../app/db.py), [Mini App API](../app/miniapp_api.py). Runtime actor устанавливается после проверки Telegram identity; клиент не выбирает чужого пользователя. Полный перечень таблиц и связей формирует [read-only inventory](../scripts/privacy_db_inventory.py), без чтения личных строк. |
| Владелец → PWA → DB | E-mail, password hash, session/token digests и подтверждённая связь Telegram дают owner-only доступ к общим учебным данным. Заданное владельцем отображаемое имя хранится отдельно в web_profile_names по account_id; оно тоже относится к персональным данным. | [PWA auth](pwa-auth.md); student PWA исключён из продукта. Не приписывать Telegram пользователям PWA credentials. |
| Владелец → Google OIDC → PWA | По явному подключению из действующей owner session сохраняется Google subject, account_id и время связи. Подтверждённый Google e-mail проверяется при обработке ID token, но не добавляется в таблицу связи и не заменяет identity владельца. | [OIDC client](../app/google_oauth.py), [durable flow](../app/owner_google_oauth.py), [схема](../sql/google-oauth-v1.sql). Только openid/email; авторизационный код, PKCE verifier и client secret передаются Google для обмена. Access/refresh/ID tokens не сохраняются в DB и не выдаются клиенту. Владелец 07.10 подтвердил включение и вход через Google с прежним аккаунтом и сохранённым прогрессом; независимый повторный login не выполнялся. |
| PWA → временное OAuth state | На срок 10 минут DB хранит state/browser digests, nonce, PKCE verifier, purpose и связь с инициировавшей session для link. Secure HttpOnly cookie связывает callback с браузером. | Challenge удаляется до сетевого обмена при принятом callback; просроченные rows очищаются при следующем begin, поэтому TTL не означает немедленное физическое удаление. Disconnect удаляет связь и принадлежащие account challenges, отзывает другие sessions. Backup может сохранять прежние rows до удаления копии. Эти данные входят в privacy inventory и additive recovery, а не в learning-data export. |
| PWA → SMTP | Письма подтверждения/восстановления содержат адрес получателя и одноразовую ссылку. Учебные ответы в SMTP не отправляются этим модулем. | [Mailer](../app/web_mail.py), настройки в [PWA auth](pwa-auth.md). Фактические сроки хранения у почтового провайдера UNSET. |
| Runtime DB → backup/recovery | Копии persistent state нужны для безопасной миграции и восстановления. Они могут содержать личные строки. | [PostgreSQL backup](../scripts/postgres_backup.py), [процедура поставки](miniapp-deployment-qa.md). Срок локальных копий согласован D-47 с исключениями minimum2/recovery; его фактическое применение ещё не подтверждено, автоматического удаления всех copies нет. |
| Browser → reverse proxy → API | HTTP запросы необходимы для Mini App/PWA. Прокси и инфраструктура могут обрабатывать сетевые metadata. | [Поставка](miniapp-deployment-qa.md) и [PWA auth](pwa-auth.md) задают запрет credential/body logging. D-47 задаёт 14 дней собственным Nginx/application logs; фактическая конфигурация, Cloudflare retention и география требуют runtime records. |
| Drive → приватная обработка → публикация | Учебные источники используются для подготовки контента. Это отдельный операторский поток, не экспорт личной истории обучающихся. | [Content rollout](question_bank_content_rollout.md). Приватные исходники и provenance не становятся публичными API ответами. |

## Уточнение клиентских и операторских потоков

Сверка 30.09.2026 на локальной ветке PR2 после `252a36d`: это анализ текущего кода/config, а не снимок сетевого трафика VPS. Этот анализ не устанавливает страны обработки, фактические logs и retention. Позднее владелец подтвердил Францию только для VPS (см. условия размещения выше).

| Граница | Наблюдаемый кодовый поток | Ограничение Evidence |
| --- | --- | --- |
| Mini App → Telegram SDK | [Собранный entrypoint](../miniapp-react/index.html) загружает Telegram Web App SDK с домена `telegram.org`. SDK предоставляет initData клиенту; браузер делает отдельный запрос к Telegram. | Нельзя описывать Mini App как полностью локальную страницу без внешних запросов. Фактическая обработка сетевых metadata Telegram определяется его действующими условиями, не этим code review. |
| Mini App → закреплённый API | [Клиент API](../pwa/src/miniapp/api.ts) использует `quiz-api.librechat.online`. GET передаёт initData в Authorization, POST — в envelope вместе с учебным payload. Destination/route allowlist закреплены кодом, redirect запрещён, credentials omitted и cache no-store. | Проверка кода подтверждает адрес и способ передачи, но не текущую DNS/proxy topology или сохранность headers в фактических logs. Контроль backend identity и host verification остаётся в процедуре поставки. |
| Owner PWA → same-origin API | [PWA transport](../pwa/src/api.ts) обращается к относительным `/web/` routes; данные auth и учебные ответы обрабатывает тот же backend domain, с server actor mapping. | Same-origin не означает отсутствие инфраструктурного посредника или access logs. Runtime Nginx/Cloudflare settings требуют отдельных records. |
| Bot → Telegram | [Telegram adapter](../app/main.py) получает update identity и возвращает интерфейс/feedback через Telegram. Учебный результат, показанный в чате, становится содержимым сообщения Telegram. | Это отличается от Mini App API response. Удаление runtime DB history не удаляет автоматически ранее отправленные Telegram-сообщения или данные платформы. |
| Клиент → книжный провайдер | [Литература PWA](../pwa/src/LiteratureView.tsx), [Mini App](../pwa/src/miniapp/MiniLiterature.tsx) и [Telegram adapter](../app/literature_chat.py) открывают внешние offers по действию пользователя. В app-generated URL нет Telegram actor, e-mail, ответов или personal reading state; browser links используют noopener/noreferrer. | После открытия provider может получать собственные сетевые metadata и обрабатывать свою учётную запись по своим условиям. Это не синхронизация прогресса; подключения читалок исключены D-42, дополнительных provider credentials приложение не получает. |
| SMTP → почтовый провайдер | [Mailer](../app/web_mail.py) отправляет owner recipient, тему/текст и одноразовую auth-ссылку через configured SMTP с TLS. | Полный recipient/token нужен для доставки. Generic error path не раскрывает SMTP exceptions клиенту; фактические mail logs/retention/geography ещё UNSET. |
| Private search → локальная модель | [Search service](../app/private_search.py) работает с приватными reviewed extracts и локальным embedding/index. При первом получении model weights возможен внешний сетевой запрос; это отдельный download от runtime query embedding. | Наличие offline query path не доказывает готовый cache или отсутствие любых исходящих соединений во время подготовки. VPS cache/probe/seven-case QA подтверждены на baseline3c10221 owner record06.10 (ниже); проверка этого ограниченного набора не устанавливает все исходящие соединения. RAG отложен D-44. |
| GitHub CI/CD → VPS | [CI](../.github/workflows/ci.yml), [поставка](miniapp-deployment-qa.md) и [исключения build context](../.dockerignore) поставляют код/контент и verified artifacts. Private input/cache исключены из backend build context. | Это конфигурационный контроль; не утверждение о фактическом отсутствии чувствительных данных во всех ранее созданных artifacts/logs. Runtime personal DB/SMTP secret не должны передаваться в публичные repository artifacts. |

## Соответствие выбранной стандартной политике

Telegram Standard Bot Privacy Policy повторно прочитана 30.09.2026. Разделы 2.6, 5–7 оставляют ответственность за соответствие фактической обработки разработчику; одна ссылка не подтверждает соответствие. Проверенная процедура повторно подтверждаемого удаления учебных данных покрывает только согласованный learning-state scope. Правила политики также предусматривают доступный канал запросов, копию личных данных и обращения об исправлении/удалении иных данных. Контакт обращений о копии или исправлении учебных данных согласован владельцем: `Just9119@gmail.com`. Разработчик обозначен по D-48 как «Владелец PsychologyAtlas», контакт Just9119@gmail.com; исполнение requests для owner identity и применение backup/log сроков ещё не подтверждены.

Сверка действующей политики 06.10.2026: пункт 7.3(c) требует своевременно
обрабатывать законные обращения и отвечать в применимые сроки, в любом случае
не позднее 30 дней с получения. Это правило уже выбранной стандартной политики,
а не новый срок хранения данных или утверждение о выполненных обращениях.
Более короткие применимые сроки не установлены. Проверка заявителя и порядок
передачи определены D-47; ручной порядок owner PWA определён D-49 и описан ниже. Пункты 7.2(a) и 7.4(a) предусматривают проверку личности и
содействие заявителя; они сами не определяют технический способ этой проверки.

Кодовый scope AC-PRIV-01/02/05 сверяется с data inventory, доступным контактом,
повторным подтверждением actor-scoped deletion, scoped export и правилами D-47–49.
Current CI и фактическое применение сроков на VPS остаются обязательными gates поставки. Этот разбор не вводит consent form, возрастную блокировку, миграцию хранилища или новый data collection; условные правовые требования остаются предметной проверкой Q-11.

## Удаление учебной истории

В личном Telegram-чате `/delete_data` показывает состав удаления; `/delete_data_confirm` подтверждает его в течение десяти минут. Mini App использует ту же процедуру с отдельным подтверждением. Challenge одноразовый, удаление атомарно и ограничено текущим actor. Удаляются попытки/ответы и связанные snapshots, glossary sessions, reading marks, цели, достижения, история/сессии повторений. Конкретные таблицы и каскадные связи проверяются [SQLite tests](../tests/test_privacy_data.py) и [PostgreSQL tests](../tests/postgres/test_privacy_deletion.py).

Telegram identity сохраняется для продолжения использования бота; общий банк и чужие строки не изменяются. Связанный owner PWA отклоняется до удаления: его общий учебный state нельзя потерять побочным Telegram действием. Обращения о копии или исправлении учебных данных принимаются по согласованному контакту ниже. Порядок удаления собственного owner PWA согласован D-49: отдельный явный запрос, согласование состава и повторное подтверждение. Другие запросы полного удаления identity рассматриваются адресно; фактические операции не выполнялись. Данная команда не объявляется полным исполнением всех прав из стандартной политики.

Контакт для обращений о копии или исправлении учебных данных: `Just9119@gmail.com`. Владелец явно разрешил публикацию 30.09.2026. Доступность почтового ящика и фактическое исполнение запросов этим решением не проверены.

## Копия учебных данных по обращению

В рамках E16 подготовлен [операторский exporter](../scripts/export_learning_data.py).
Это выгрузка данных одного подтверждённого Telegram actor, не полная копия
всех персональных данных платформы. По умолчанию выгружаются только учебные строки:
ответы глоссария, попытки, повторения, цели, достижения и личные отметки книг.
Явный флаг `--include-identity` добавляет сохранённые Telegram ID/имя/username,
режим чтения и даты, а также принадлежащие этому actor e-mail, состояние связанного
PWA account, display name и Google subject с датой привязки. Поля выбираются
по allowlist; password hashes, sessions, mail/link/deletion/OAuth challenges,
общие content snapshots, приватные источники и инфраструктурные logs/backups
не выгружаются. Эти исключения обозначены в metadata копии.

Перед запуском оператор должен подтвердить, что обращение принадлежит этому
Telegram user ID. Username, подпись в письме или присланный чужой ID сами по себе
не подтверждают личность. Флаг `--verified-request` фиксирует выполненный оператором
шаг; script не делает эту проверку и не отправляет файл. Автоматической доставки
и публичного API выбора actor нет. Порядок проверки личности и передачи согласован D-47; exporter сам эти процедуры не выполняет. Проверка заявителя по известному контакту либо лично проводится до запуска, передача на подтверждённый адрес — по явному запросу.

Canonical команда из root, с действующим DATABASE_URL/DB_PATH:
```bash
python scripts/export_learning_data.py --telegram-user-id "$VERIFIED_TELEGRAM_USER_ID" \
  --verified-request --output data/learning-copy-request.json
```

Для запроса, включающего сохранённые сведения пользователя, к той же команде
добавляется `--include-identity`. Это требует текущей инициализированной auth schema;
при несовместимой schema операция прекращается, неполный файл не доставляется.
Результат имеет scope `profile_and_learning_data_copy` и schema_version 2;
прежний учебный формат версии 1 сохраняется без этого флага.

Локальный output — новый ignored `data/*.json`; в production container — новый `/data/learning-copies/*.json` на persistent mount. Файл создаётся с mode 0600;
права и ACL Windows дополнительно контролирует оператор. База открывается read-only,
а все запросы выполняются в одном consistent snapshot. Session children выбираются
через принадлежащие actor попытки; чужой learning state и общий банк не меняются.
JSON содержит row_counts для всех учебных таблиц и `complete: true` только в конце
успешной записи. При STOP частичный файл не доставлять и не выдавать за готовую копию;
проверить результат локально в приватном окружении. Файлы не включать в Git, PR,
public artifacts или обычные logs. Способ передачи и срок хранения согласованы D-47: подтверждённый адрес по явному запросу, 7 дней после передачи. Код не отправляет и не удаляет файл автоматически; применение срока требует процедуры и Evidence.

Validation: [SQLite/CLI isolation](../tests/test_privacy_export.py) и
[native PostgreSQL contract](../tests/postgres/test_learning_copy_postgres.py).
Native проверка обязательна в существующем backend CI до merge; подготовка кода
не подтверждает исполнение реальных обращений или готовность AC-PRIV-01/02/05 целиком.

## Оставшиеся условия проверки

- На целевой revision выполнить PostgreSQL actor-isolation/one-use tests в required CI и подтвердить additive migration/CD.
- Проверить фактические DB/backups/logs/SMTP/Cloudflare records и применение D-47; обозначение разработчика согласовано D-48; страны/retention внешних сервисов UNSET до первичных данных. Для VPS Франция подтверждена владельцем 06.10; страна не выведена из IP или названия хостера.
- Проверить доступность согласованного контакта и определить порядок owner PWA/identity/export requests; выбранная политика задаёт ответ не позднее 30 дней, фактическое исполнение и конкретные применимые сроки пока не подтверждены.
- Согласовать backup retention/recovery так, чтобы восстановление старой копии не выдавалось за сохранение выполненного удаления.

Сверка 06.10.2026, ветка `codex/project-completion`: native PostgreSQL deletion/export/recovery checks уже прошли на delivered baseline `3c10221592bdc749f349f8a34db9e7f603f80097` (main CI `37369443143`, CD `37428925553`). Они подтверждают actor isolation и сохранность state в своих сценариях, но не юридическое соответствие, фактическую географию или сроки хранения. Для поставленной OAuth schema v9 main CI37535922810/head eb57072 PASS: backend job112516673767 выполнил Behavioral regression suite, PWA job112516674155 — PostgreSQL browser regression. Native fixture в CI отклоняет отсутствующий PostgreSQL target, поэтому этот запуск не подменяется локальным skip. Privacy deletion/export modules и схема не изменены локальным retention diff; новая runtime output path/helper всё равно требует нового CI/CD. Private search VPS checks baseline PASS по record `/root/psychology-search-check-dPLNP3lJ`; это ограниченный набор retrieval cases и resource measurements, не утверждение об отсутствии любых внешних запросов. RAG отложен по D-44.

Статусы и Evidence остаются в [delivery plan](delivery-plan.md); AC-PRIV-01/02/05 не закрываются этим документом целиком.

## Сохранённый student PWA state

Перед deprecation приглашений/связанной схемы выполнить [read-only preflight](../scripts/student_legacy_preflight.py) в окружении с действующими `DATABASE_URL`/`DB_PATH` и `PWA_OWNER_EMAIL`: `python scripts/student_legacy_preflight.py` из root. В контейнере штатного API используются уже установленные runtime values: `docker compose -p psychology-quiz -f docker-compose.yml exec -T psych_quiz_miniapp_api python scripts/student_legacy_preflight.py`. Команда применима после поставки версии с этим script; повторный deploy ради inventory не требуется. Не публикуйте resolved env/DSN. Вывод содержит только агрегаты и метки snapshot; unknown owner/table означает отсутствие подтверждения, не отсутствие данных. Даже нулевые counts не разрешают удаление схемы: отдельно нужны согласованные migration/recovery и проверки consumers. Существующие accounts, приглашения, history и schema этим preflight не меняются.


## Подготовленное хранение логов приложения

[Runtime wrapper](../scripts/runtime_log.py) сохраняет вывод API и бота в приватных daily files mounted data/runtime-logs. Каждый сервис удаляет только собственные известные date buckets через14 дней; неизвестные files и логи другого сервиса не трогает. Mode directory0700/files0600, symlinks/hardlinks и чужие permissions отклоняются. Тихий сервис выполняет очистку раз в час. По [compose](../docker-compose.yml) API/bot не сохраняют вторую бессрочную копию stdout/stderr через Docker logging driver. Private log files исключены из Git/build/client assets как часть data/.

До CI/CD это подготовленная конфигурация, не подтверждение runtime хранения. Nginx/Cloudflare/PostgreSQL diagnostics этим wrapper не управляются. Nginx retention14 дней требует отдельной проверки точного vhost/log path на shared host; общую nginx/journald retention не менять по догадке. Для диагностики после поставки использовать приватные host files, не docker logs; не прикладывать raw logs к публичным Actions/PR.


## Production выгрузка и семь дней после передачи

Внутри runtime-container exporter пишет только в новый приватный /data/learning-copies/*.json на persistent mount, создавая learning-copies с0700 и файл с0600. /app/data не является runtime target и Git внутри образа не нужен. Локальный host checkout сохраняет прежнюю ignored-data policy. [Проверка target](../tests/test_export_learning_target.py) и actor/export tests подтверждают эти разные границы; actual production command ещё PENDING.

После проверки заявителя оператор создаёт копию из /opt/psychology-quiz:

```bash
docker compose -p psychology-quiz -f docker-compose.yml exec -T psych_quiz_miniapp_api \
  python scripts/export_learning_data.py --telegram-user-id "$VERIFIED_TELEGRAM_USER_ID" \
  --verified-request --include-identity --output /data/learning-copies/request.json
```

Имя request.json — пример нового файла; existing target не перезаписывается. До передачи файл проверяется в приватном окружении. После фактической передачи на подтверждённый адрес по явному запросу:

```bash
docker compose -p psychology-quiz -f docker-compose.yml exec -T psych_quiz_miniapp_api \
  python scripts/learning_copy_retention.py --mark-delivered /data/learning-copies/request.json \
  --confirmed-transfer
```

[Receipt/cleanup](../scripts/learning_copy_retention.py) фиксирует UTC передачи и SHA файла в private delivery-receipts; адрес, ID заявителя и текст копии в receipt не добавляются. Повторный mark не продлевает срок. Только полная выгрузка с совпадающими row_counts допустима; неполный/изменённый файл или чужой путь не удаляется. Непереданные copies и unknown files не имеют автоматического срока удаления. API wrapper при старте и раз в час чистит только неизменённые copies с истёкшими7 днями после передачи, под отдельной lock этого каталога. Ошибка receipt сохраняет файлы и даёт generic private diagnostic, не останавливая обучение. Эта команда не выполняет отправку и не заменяет проверку личности.

Код подготовлен локально и требует current CI/CD; это не Evidence уже исполненного пользовательского обращения. Receipt helper, runtime upkeep и operator exporter должны поставляться одной revision.


## Scoped Nginx evidence и диагностические логи

07.10 владелец передал read-only снимок `nginx -T`: единственный найденный
vhost `psy.cloud-nodes.net` расположен в
`/etc/nginx/sites-enabled/psy.cloud-nodes.net.conf`, error_log — `/dev/null`.
Дополнительная проверка этого файла подтвердила две access_log directives,
обе `off`. Для этих потоков собственного vhost новые logs не создаются и
retention не требуется. Файл и shared Nginx configuration не изменяются.
Это ограниченный снимок, не проверка всех upstream/proxy/provider logs.

API child запускается с `--no-access-log`: request URI, включая OAuth callback
code/state, не должны попадать в новые диагностические файлы через Uvicorn
access logger. Bot/API diagnostics остаются в private daily files по D-47.
Cloudflare, Telegram, Google и SMTP — отдельные внешние системы; их страны и
провайдерская retention этим снимком не установлены. Не описывать фактическую
обработку как ограниченную только почтой: Telegram identity, учебная история
и owner auth/link metadata перечислены в inventory выше.


## Операторский порядок обращений

Действующий опубликованный контакт — `Just9119@gmail.com`. Пользователь направляет
обращение о своих данных, владелец определяет запрошенный результат: копия,
исправление, удаление истории либо прекращение хранения иных идентифицирующих
данных. Обращение само по себе не разрешает отправить файл неизвестному адресату,
изменить чужую запись или удалить общую историю владельца PWA.

1. Подтвердить заявителя по известному владельцу контакту либо лично (D-47).
   Telegram ID/username или знание чужого e-mail сами по себе недостаточны.
   Не запрашивать паспортные документы по умолчанию. Если проверка не завершена,
   не выполнять передачу/изменение; ответить заявителю о недостающем подтверждении.
2. Определить точного actor и согласовать состав операции. Для копии использовать
   exporter с `--include-identity`, проверить `complete`, scope, row_counts и
   принадлежность actor; неполный результат не передавать. Credentials/proofs
   и копии инфраструктуры не включаются в этот exporter. Если запрос шире его
   состава, отдельно проверить имеющиеся данные и объяснить состав ответа;
   не выдавать scoped JSON за автоматически полную копию всех данных.
3. Передать согласованную копию только на подтверждённый адрес по явному запросу;
   отметить выполненную передачу private receipt и применить7-дневную очистку.
   Receipt не доказывает отправку: сначала выполняется реальная передача.
4. Исправление выполнять только для подтверждённого actor и согласованных полей,
   после проверки текущей revision/state. Не переписывать правильность учебных
   ответов или общие источники под видом исправления имени. Если имя в Telegram
   изменено самим пользователем, штатный `create_or_load_user` обновляет сохранённые
   username/имя при следующем обращении; PWA display name меняется в настройках.
5. Для удаления обычной Telegram учебной истории использовать существующее
   повторное подтверждение; оно не удаляет Telegram-аккаунт, identity, сообщения
   платформы или snapshots. Запрос полного прекращения хранения identity либо
   связанного owner PWA требует отдельного подтверждения состава и scoped
   procedure. Для собственного owner PWA порядок согласован D-49; реальная операция требует его конкретного запроса и повторного подтверждения. Полное удаление иной Telegram identity здесь не объявляется реализованным.
6. Ответить на обращение без неоправданной задержки, не позднее30 дней по выбранной
   стандартной политике; более короткий применимый срок требует предметного
   основания. Фактическое исполнение обращений/доступность inbox этим code review
   не проверены; реальные запросы не отправлялись ради теста.

Локальные backups могут содержать прежнее состояние. Срок30 дней и minimum2/pinned
исключения указаны D-47; их наличие не означает немедленное удаление всех старых
личных строк. Перед отдельно разрешённым production restore оператор должен
сверить удаления/исправления после даты backup и определить порядок их повторного
применения до открытия writers. Если этих сведений нет, restore не объявлять
сохранением выполненного удаления. Canonical routine deploy не выполняет
production restore и не возвращает старый backup автоматически.

D-48 согласовал обозначение разработчика; D-49 — ручной порядок для собственного
owner PWA (07.10). Они не меняют права Telegram
команды и не разрешают удаление каких-либо текущих данных. Окончательное privacy
Evidence требует принятого решения, current CI и применения D-47 на VPS.


## Отдельный запрос владельца PWA

Удаление рассматривается только после собственного явного запроса владельца.
Сначала определить, относится ли запрос лишь к PWA-аккаунту либо также к общей
учебной истории связанного Telegram actor. Показать полный состав и последствия,
сохранение либо удаление общей истории, затем получить отдельное повторное
подтверждение. Перед исполнением установить текущую identity/state, точный target,
необходимые recovery условия и запрет изменения чужих строк. Только после этого
выполняется согласованная scoped операция с readback; незавершённый результат
не объявляется успешным. Согласование этой процедуры само по себе не означает,
что такой запрос поступил или что удаление выполнено. Сейчас аккаунт и история
остаются без изменений; кнопка автоматического полного удаления не добавляется.
