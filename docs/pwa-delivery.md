# Публикация самостоятельной PWA

После подготовки кода пользователь 19.09.2026 поручил настройку VPS и публикацию PWA. Target и config owner установлены; первичный HTTP маршрут и сертификат подготовлены оператором. Активация backend/static, local HTTPS и public smoke из VPS и независимой сети подтверждены. Первоначальный URLError не воспроизвёлся при read-only повторе проверки; конфигурация не менялась. Real-mail/owner acceptance пока PENDING; результаты и ограничения — в E-PWA-05 плана. [Backend auth/config](pwa-auth.md), [existing VPS procedure](miniapp-deployment-qa.md) и [client/build](pwa-client.md) сохраняют свои роли. Canonical frontend commands — [README](../README.md#pwa-local-run-и-проверки).

## Установленный target и operator setup

Источник: явные решения владельца, DNS screenshot и вывод root-сессии MobaXterm 19.09.2026; локального SSH-доступа агента нет. Текущий статус поставки и primary records — [Результаты PWA Goal](delivery-plan.md#завершённая-goal--pwa-first-001).

| Поверхность | Значение / owner |
| --- | --- |
| VPS / operator | `167.86.68.98`, Ubuntu 24.04; владелец проекта выполняет команды как root через MobaXterm |
| Public hostname | `psy.cloud-nodes.net`, HTTPS; A record в Cloudflare указывает на этот VPS, Proxied. DNS/Cloudflare управляет владелец |
| Application source / services | `/opt/psychology-quiz`, Compose `psychology-quiz`, `psych_quiz_bot` и `psych_quiz_miniapp_api`; API `127.0.0.1:8081` |
| Static namespace | `/var/www/psychology-atlas`, marker `.pwa-root` = `psychology-atlas-pwa`; public pointer `current`, immutable `releases/<sha>` |
| Nginx site | `/etc/nginx/sites-available/psy.cloud-nodes.net.conf`, symlink в `sites-enabled`; отдельные HTTP/HTTPS server blocks, соседние сайты сохраняются |
| ACME webroot | `/var/www/psychology-atlas/acme`; HTTP location `/.well-known/acme-challenge/` остаётся доступным после включения HTTPS redirect |
| TLS | Certbot 2.9.0; `/etc/letsencrypt/live/psy.cloud-nodes.net/fullchain.pem` и `privkey.pem`. Operator output подтверждает сертификат CN нужного hostname до 18.12.2026 и настроенное автоматическое продление; фактический будущий renewal ещё не проверен |
| Config / mail owner | Владелец проекта; login mailbox согласован отдельно, его значение и SMTP credentials в репозитории не хранятся |
| SMTP source | Существующий Compose `smart-life-platform`, service `api` на том же VPS, переменные `RECOVERY_SMTP_*`; перенос только нужных значений в `PWA_SMTP_*` внутри VPS, без изменения исходного проекта |
| Runtime destination | Существующий `/opt/psychology-quiz/.env`; оригинал сохранить в приватной operator backup directory до записи. Остальные поля, ownership и permissions сохраняются |

Initial setup не является обычным CD. Для него владелец явно разрешил создание dedicated static root, Nginx site, сертификата и owner/SMTP configuration. Production Environment и существующий backend CD сохраняют свои правила. Операция сериализуется через существующий `/tmp/psychology-quiz-deploy.lock`; неизвестный или уже изменённый target требует readback, а не повторного bootstrap.

При первой активации сверить clean checkout/main, source SHA, running image IDs и эффективную Compose configuration. SMTP authentication проверяется через TLS без отправки письма; затем сохранить private config backups и подготовить проверенные static assets через `stage`. До restart подтвердить сохранность остальных dotenv values и проверить candidate через existing `scripts/deployment_db.py preflight`. Пересоздаются только bot/API из уже проверенных images, с прежним `APP_REVISION`; миграций, rebuild образов, остановки соседних проектов и операций над volumes этот этап не требует. После backend post-checks применяются HTTPS template, `activate` и Nginx reload по процедуре ниже. Ошибка до restart позволяет восстановить только собственную невалидную config-запись; failure после переключения требует остановки продвижения и разбора текущего state по record. DB restore не выполняется.

Nginx reload завершается раньше, чем все workers переключатся: после reload проверять точный контрольный ответ ограниченными повторными GET, а не повторять создание файлов после первого 404. Во время setup Certbot один раз получил reset на ACME directory; последующая проверка IPv4/IPv6 дала 200, а одна повторная попытка успешно выдала сертификат. Это Evidence восстановленного запроса, не основание менять Cloudflare proxy или отключать IPv6.

Для Cloudflare public probes использовать идентификатор клиента `PsychologyAtlas-Deployment-Check/1.0`. В этой зоне default Python-urllib получил 403/1010; именованный probe получил контрольный файл с 200. Если оператор задаёт User-Agent у opener существующего `scripts/pwa_smoke.py`, все проверки TLS, запрета redirects, revision, hashes, MIME, headers и actual 401 остаются обязательными. Логи не должны содержать auth query/body/cookie values. Public smoke не выполняет регистрацию и не отправляет real mail.

## Deployment unit и доступы

PWA — public static assets в выделенном каталоге VPS с Nginx HTTPS и same-origin proxy `/web/` к существующему loopback FastAPI на 8081. Это не новая SQLite/Compose service и не отдельный GitHub Environment. Existing production Environment/SSH rules действуют для операции поставки; новые protections не создаются этим кодом. CI `pwa-client` строит assets один раз; runtime backend поставляется existing CD. Нового auto-deploy trigger нет.

До первого запуска оператор должен установить точный host/account/root, владельцев DNS/TLS/Nginx и `.env`, существующий HTTPS bind и MIME configuration. Он отдельно создаёт dedicated root с файлом `.pwa-root`, содержащим ровно `psychology-atlas-pwa`. Корень не должен быть общим document root другого приложения или каталогом data/repository. CLI требует этот marker и существующий absolute root; host bootstrap, permission changes и создание сертификатов он не выполняет. Nginx читает только `ROOT/current`, deploy identity пишет root/releases; посторонние пользователи не должны писать в них.

[Nginx template](../deployment/pwa/nginx.conf.template) включается в существующий `http` context. Все placeholders заменить установленными значениями: `__HTTPS_BIND__`, `__PWA_HOST__`, `__TLS_CERTIFICATE__`, `__TLS_KEY__`, `__PWA_RELEASE_ROOT__`, `__API_PORT__` (текущий backend 8081). Перед reload обязателен `nginx -t` на целевом host. HTTP→HTTPS redirect/DNS/certificate renewal задаёт фактический config owner в initial setup; шаблон не перезаписывает соседние server blocks. Backend port остаётся loopback. `.env` задаёт exact HTTPS PWA_ORIGIN и PWA_ENABLED=true только после готовности владельца/почты; production loopback exception отключён.

Template: no-store, nosniff, no-referrer, self-only scripts/connect/worker, frame-ancestors none; inline styles разрешены для score ring/offline page. Ответы API не кэшируются, URI не переписывается, cookies/Origin/CSRF проходят в backend. Raw access logs выключены; для `/web/` выключены также Nginx error URI logs, используются sanitized backend action/status и обязательные HTTP checks. Это уменьшает edge diagnostics, зато не пишет query/body/cookie credentials в эти logs. Private API никогда не становится SPA fallback. Static MIME types должны быть включены в `http`; smoke проверяет JavaScript MIME.

## CI → merge → backend CD → static release

Операции выполнять в одной сериализованной production delivery сессии. Перед stage и ещё раз перед activate сверить current main/candidate и отсутствие конфликтующего backend/static deploy. Local lock сериализует static операции, но не заменяет общую очередь и проверку candidate.

1. На trusted operator/CI host проверить точный full merge SHA, последнюю успешную main/push CI из `.github/workflows/ci.yml`, все required jobs и последующий existing backend CD. Использовать primary GitHub records; более новый pending/failed run запрещает reuse старого green. При queue delay заново сверить main. Применимый backend runtime должен соответствовать candidate; при source-sync CD сравнить runtime→candidate diff для app/schema/config/dependencies и подтвердить совместимость. Backend health/image/CD records сохраняются отдельно от static SHA.
2. Скачать **именно из этого run** artifact `pwa-<merge-SHA>` штатным `gh run download RUN_ID --name pwa-SHA --dir ARTIFACT`. Убедиться, что artifact не expired и run принадлежит `Just9120/psychology-quiz`, main, push, ожидаемому SHA. Не использовать PR artifacts, cache или build из dirty worktree. Artifact ID/run/digest из GitHub сохранить в delivery records. Если artifact истёк, необходим новый trusted build/validation; не подменять скачивание локальной пересборкой.
3. Проверить скачанное содержимое командой `verify` ниже, передать public artifact на заранее проверенный VPS через host-verified SSH и повторить verify на принимающей стороне. CLI проверяет integrity/identity, **не** устанавливает доверенность CI самостоятельно; source provenance — обязательный предыдущий gate.
4. `stage` создаёт immutable `ROOT/releases/SHA`. `activate` требует наблюдённый previous SHA (`NONE` только для первого запуска), делает atomic symlink replacement и readback. До этого ещё раз подтвердить preconditions: correct target/main/CI/CD, enabled auth config, valid TLS/Nginx, shared API compatibility. CLI не меняет `.env`, DB, Nginx или сервисы.
5. Выполнить public smoke ниже и bounded authenticated owner flow после согласования real e-mail: verify/login/link/quiz/reload/logout/recovery, install/standalone в поддерживаемом браузере. Public smoke подтверждает только assets/headers и unauthenticated boundary; он не заменяет эти проверки. Зафиксировать time, main CI/artifact IDs, backend revision/image, static SHA, target и результаты. Не создавать metadata-only follow-up PR.

Canonical CLI (repository root; Python 3.12 без дополнительных dependencies для release/smoke; значения `SHA`, `ARTIFACT`, `ROOT`, `PREVIOUS`, `ORIGIN` — установленные параметры, не defaults):

```text
python scripts/pwa_release.py verify --sha SHA --artifact ARTIFACT
python scripts/pwa_release.py stage --sha SHA --artifact ARTIFACT --root ROOT
python scripts/pwa_release.py activate --sha SHA --root ROOT --previous PREVIOUS
python scripts/pwa_smoke.py --origin ORIGIN --sha SHA --artifact ARTIFACT
```

Smoke проверяет HTTPS certificate без redirect bypass, полный build manifest и SHA-256 каждого public asset, security headers и `/web/auth/me` = 401/no-store/unauthorized. Он ничего не отправляет владельцу и не меняет progress. В test/private PKI можно явно задать `--ca-file`; TLS verification не отключается.

## Retry и recovery

Повторный stage той же revision допустим только при одинаковом manifest. Existing release не перезаписывается. Activate проверяет old pointer, target hashes и lock; stale expected previous, links за пределы namespace, повреждённые files или чужой обычный `current` оставляют pointer без изменения. Повтор activation уже активной revision читает и проверяет её, не переключая ещё раз.

При failure до activation current остаётся прежним. При failed post-check остановить продвижение, сохранить primary records и выбрать forward-fix. Explicit rollback только статических files возможен тем же activate с прежним SHA и фактически текущим `--previous`, после проверки совместимости backend/API. Он не откатывает DB/config и не разрешает production data restore. Старые releases не удаляются автоматически; cleanup/retention отдельно. После interrupted process возможен `.release.lock`: сначала проверить PID/процессы/очередь и действующий pointer, удаление stale lock — явное действие оператора в установленном target, без автоматического обхода.

## Проверки кода и ограничения

`python -m pytest tests/test_pwa_release.py tests/test_pwa_smoke.py -q`: hash/revision/file set, stale/concurrent activation, link safety, immutable retry, corruption и explicit static rollback. Windows без symlink privilege пропускает только соответствующие cases; Linux CI обязан выполнить их.

В CI frontend job после build/browser suite устанавливает Nginx из runner OS repositories и выполняет из `pwa/` `python tests/nginx_smoke.py`: реальный Nginx, временный TLS certificate с verification, public artifact и synthetic 401 upstream. Это test dependency, не pin production Nginx. Проверены syntax/HTTPS/static integrity/headers/path forwarding. Actual FastAPI auth/quiz покрыты отдельными real-backend browser/API tests. Operator output подтверждает production config/SMTP authentication, enabled runtime и local HTTPS; независимый public smoke проверил HTTPS app routing и все assets. Повтор той же public проверки из VPS также PASS без повторной установки. Real-mail/owner acceptance остаётся PENDING (E-PWA-05); public browser и ограничения installation evidence — E-PWA-06.
