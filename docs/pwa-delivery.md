# Публикация самостоятельной PWA

Сейчас подготовлен код; применение на production отложено пользователем. Hostname, static release root, DNS/TLS/config owner и реальные owner/SMTP settings — **UNSET**. Не подставлять адрес Mini App и не запускать операции на неизвестном target. [Backend auth/config](pwa-auth.md), [existing VPS procedure](miniapp-deployment-qa.md) и [client/build](pwa-client.md) сохраняют свои роли. Canonical frontend commands — [README](../README.md#pwa-local-run-и-проверки).

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

В CI frontend job после build/browser suite устанавливает Nginx из runner OS repositories и выполняет из `pwa/` `python tests/nginx_smoke.py`: реальный Nginx, временный TLS certificate с verification, public artifact и synthetic 401 upstream. Это test dependency, не pin production Nginx. Проверены syntax/HTTPS/static integrity/headers/path forwarding. Actual FastAPI auth/quiz покрыты отдельными real-backend browser/API tests. Доступ к production Nginx/settings и live public PWA пока не подтверждён.
