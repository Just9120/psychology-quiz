# Owner PWA: auth contract и эксплуатация

Границы первого owner-only среза — [spec](project-spec.md), состояние/Evidence — [план](delivery-plan.md). Общий quiz service принимает проверенный `users.id`; web request не задаёт actor. Старые Telegram routes продолжают проверять initData. Public signup/sharing и merge двух историй не входят в этот этап.

## Конфигурация

По умолчанию `PWA_ENABLED=false`: `/web/*` routes отсутствуют. После подготовки кода владелец 19.09.2026 поручил публикацию: hostname, owner mailbox и источник SMTP установлены в [operator setup](pwa-delivery.md#установленный-target-и-operator-setup). Включение и SMTP TLS authentication подтверждены operator output; real-mail/owner acceptance пока PENDING (E-PWA-05 плана). Runtime host `.env` — существующий источник secrets; обычные PR/CD его не заменяют и не заполняют. Первичную конфигурацию выполняет владелец на VPS с сохранением остальных settings и приватной резервной копии.

Enabled API и bot требуют:

| Переменная | Правило |
| --- | --- |
| `PWA_ENABLED` | `true` / `false`; неизвестное значение — startup error |
| `PWA_ORIGIN` | Единственный HTTPS origin без path/query/fragment/credentials. PWA вызывает same-origin `/web/*`, Nginx направляет его в existing loopback API; PWA CORS не включается |
| `PWA_OWNER_EMAIL` | Единственный allowlisted owner, lowercase/trim; реальный адрес в repository не публиковать |
| `PWA_SMTP_HOST`, `PWA_SMTP_PORT` | По документации Яндекс 360, проверенной 19.09.2026: `smtp.yandex.ru`, SSL 465 или STARTTLS 587. Фактический mailbox устанавливает владелец; certificate verification обязательно |
| `PWA_SMTP_USERNAME`, `PWA_SMTP_PASSWORD`, `PWA_SMTP_FROM` | Account/app password и sender только runtime, не в CLI arguments/logs/artifacts |
| `PWA_ALLOW_HTTP_LOCALHOST` | Явное local development исключение: HTTP localhost/127.0.0.1/::1 и отдельная dev cookie без Secure. Public HTTP всегда запрещён |

Install/init/run/tests — canonical команды в [README](../README.md#быстрый-старт-и-проверки). Tests inject synthetic mailer; runtime не имеет bypass e-mail proof и не возвращает mail tokens в API. SMTP timeout 10 секунд, до двух отправок на процесс. Ошибка удаляет выданный token и возвращает только `mail_unavailable`.

## API и пользовательский flow

POST: JSON до 16 KiB, exact Origin; query parameters запрещены. Authenticated mutations дополнительно требуют `X-CSRF-Token` из `GET /web/auth/me`. Private responses — `no-store`; raw Uvicorn `/web` access logs заменены action/status без URL, cookie, IP, e-mail, Telegram ID или body. Reverse proxy также не должен логировать credentials/body.

| Endpoint | Payload / результат |
| --- | --- |
| `POST /web/auth/register` | `{email}` → generic `{ok:true}`. Verification link только разрешённому новому owner; пароль до proof не сохраняется |
| `POST /web/auth/verify` | `{token,password}` → verified account. Expired/replayed/wrong-purpose proof отклоняется; все register tokens адреса отзываются. Затем обычный login |
| `POST /web/auth/login` | `{email,password}` → `{ok:true}` + HttpOnly cookie. Unknown/disabled/not-allowlisted/wrong credentials → одинаковый 401; неизвестный account также проходит password hash workload |
| `GET /web/auth/me` | E-mail, CSRF, `needs_identity`, `telegram_linked`, `link_pending`, `link_confirmed`, `link_target` (подтверждённые имя/username/Telegram ID) только инициировавшей session |
| `POST /web/auth/logout` | Пустой JSON + CSRF → session/link request отозваны, cookie истекает |
| `POST /web/auth/recover` | `{email}` → generic response; письмо только enabled owner |
| `POST /web/auth/reset` | `{token,password}` → новый hash, все sessions/link requests account отозваны, recovery tokens удалены |
| `POST /web/identity/new` | Явно выбрать независимый actor без Telegram; повтор не создаёт второго. После выбора связывание с другим actor/merge историй не поддерживаются |
| `POST /web/link/start` | Account без actor → одноразовый `code`, предыдущий link отзывается. Владелец отправляет боту `/link CODE` в private chat |
| Telegram `/link CODE` | Verified sender предлагает свою identity; bot показывает destination e-mail и кнопку подтверждения. Чужой callback/повтор отвергается |
| `POST /web/link/complete` | В той же PWA session после показа `link_target` и явного согласия → existing actor. Занятая identity, expiry, нет Telegram confirmation, уже выбранный actor → отказ без переноса/удаления истории |
| `GET /web/quiz/options`, `GET /web/quiz/state` | Общие backend-derived options/state выбранного actor |
| `POST /web/quiz/setup` | `quiz_mode=single/selected_mix/all`, `category_ids`, `question_count=5/10/15/null` (`null` — все), `difficulty=any/easy/medium/hard` → runner state |
| `POST /web/quiz/answer` | `session_id`, `question_id`, `selected_option_index` → общий authoritative feedback/state. Retry возвращает исходный choice/result, чужой actor → 403 |

Verification/recovery links передают token в fragment, который не поступает в HTTP access log/Referer. Frontend обязан сразу удалить fragment из address bar, хранить token только в памяти формы и передать JSON. Нельзя сохранять passwords/tokens/private responses в localStorage, service-worker cache или analytics. Ссылка сама не устанавливает пароль; владелец задаёт его после proof. Linking confirmation нельзя выполнять автоматически.

## Policy и хранение

Passwords: 15–128 Unicode characters без trim/усечения, Argon2id v19, 64 MiB / 3 iterations / parallelism 1; до двух hash operations на процесс, иначе 503. Основание: OWASP Password Storage Cheat Sheet и argon2-cffi API, проверены 19.09.2026. Это техническая policy среза, не новый продуктовый SLO.

Sessions/proofs — random 256-bit secrets, в DB только SHA-256 digest. Production cookie `__Host-psychology_session`: HttpOnly, Secure, SameSite=Strict, Path=/, без Domain. Absolute TTL 7 дней, idle 12 часов; максимум 10 sessions, старые/истёкшие удаляются при login. Logout отзывает текущую, recovery все. CSRF привязан к secret session и не восстанавливает revoked session.

Verify TTL 1 час, recovery 15 минут, link 10 минут. Consume атомарный; link привязан к account/session/проверенному Telegram actor. Registration создаёт account только после e-mail proof, поэтому чужая предварительная заявка не задаёт владельцу пароль. Истории не объединяются.

Durable owner-only limits: login 10/min; register/recover совместно 5/hour; verify/reset совместно 10/min. Buckets глобальны для закрытого приложения, не доверяют forwarded IP. Анонимный flood может временно ограничить владельца; дополнительный proxy anti-abuse можно согласовать при публикации. Expired mail/session/link rows удаляются при соответствующих lifecycle operations; произвольные per-IP/e-mail buckets не создаются.

## Migration и delivery

[auth-v1](../app/auth_schema.py) добавляет accounts/sessions/mail/link/limit tables после identity-v1, отдельной idempotent transaction. Request-time DDL отсутствует, legacy learning rows не меняются. Stateful classifier покрывает helper; [backup/reconciliation](../scripts/deployment_db.py) включает все auth tables, существовавшие в backup. Их отсутствие при первой additive migration допустимо; изменение старых rows/fields при следующей не проходит preservation gate.

Используется [VPS procedure](miniapp-deployment-qa.md#действующие-правила-и-delivery-snapshot): stop writers → verified backup/isolated restore → init/seed → preservation/FK/parity → up → exact revision/image/HTTP smoke. Дополнительно `/web/auth/me` обязан отвечать 404 при disabled, 401 при enabled. Это не real-mail acceptance. После migration failure — stop/forward-fix; production restore/rollback не автоматизированы. Default-off backend delivery не меняет secrets/DNS/Nginx.

Перед включением нужны hostname/DNS/TLS/same-origin proxy и config owner, frontend build/publication, sender/credentials, bounded verification/recovery на согласованном адресе, auth/link/quiz/installability smoke с версией. DNS/HTTP/TLS, runtime config/SMTP authentication и local HTTPS подтверждены operator output; независимый public smoke PASS. Public probe из VPS также PASS после read-only повтора; real-mail/owner gates ещё PENDING (E-PWA-05 плана). [Static release/Nginx procedure](pwa-delivery.md) описывает этот этап. Existing backend preflight вызывает тот же WebSettings validator до остановки writers, поэтому неполный enabled config не допускается к переключению.
