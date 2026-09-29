# Обработка учебных данных

## Охват и основание

Проверка кода ветки `codex/complete-scope-pr2` 29.09.2026 после `a48bfde`; работа относится к AC-PRIV-01/02/05. Это карта обработки, а не новая политика или заключение о соответствии закону. Действующий Telegram/Mini App использует Telegram Standard Bot Privacy Policy; адрес хранится в интерфейсе и `TELEGRAM_PRIVACY_POLICY_URL` в [боте](../app/main.py). Первичный документ прочитан 29.09.2026: разделы 4–7 охватывают получение данных, необходимые цели, защиту и обращения пользователей. Доступная ссылка сама по себе не доказывает выполнение этих правил.

## Данные и цели

| Поток | Данные и цель | Подтверждение и ограничения |
| --- | --- | --- |
| Telegram → bot/API → runtime DB | Telegram ID и переданные имя/username связывают личные попытки. Ответы, результаты, история повторений, цели, достижения и отметки книг сохраняют обучение. Telegram не требует e-mail/пароля приложения. | [DB](../app/db.py), [Mini App API](../app/miniapp_api.py). Runtime actor устанавливается после проверки Telegram identity; клиент не выбирает чужого пользователя. Полный перечень таблиц и связей формирует [read-only inventory](../scripts/privacy_db_inventory.py), без чтения личных строк. |
| Владелец → PWA → DB | E-mail, password hash, session/token digests и подтверждённая связь Telegram дают owner-only доступ к общим учебным данным. | [PWA auth](pwa-auth.md); student PWA исключён из продукта. Не приписывать Telegram пользователям PWA credentials. |
| PWA → SMTP | Письма подтверждения/восстановления содержат адрес получателя и одноразовую ссылку. Учебные ответы в SMTP не отправляются этим модулем. | [Mailer](../app/web_mail.py), настройки в [PWA auth](pwa-auth.md). Фактические сроки хранения у почтового провайдера UNSET. |
| Runtime DB → backup/recovery | Копии persistent state нужны для безопасной миграции и восстановления. Они могут содержать личные строки. | [PostgreSQL backup](../scripts/postgres_backup.py), [процедура поставки](miniapp-deployment-qa.md). Срок хранения и ручной порядок исполнения запросов в backups UNSET; автоматического удаления всех copies нет. |
| Browser → reverse proxy → API | HTTP запросы необходимы для Mini App/PWA. Прокси и инфраструктура могут обрабатывать сетевые metadata. | [Поставка](miniapp-deployment-qa.md) и [PWA auth](pwa-auth.md) задают запрет credential/body logging. Фактические Cloudflare/Nginx logs, сроки и география требуют runtime records; текущий code review их не устанавливает. |
| Drive → приватная обработка → публикация | Учебные источники используются для подготовки контента. Это отдельный операторский поток, не экспорт личной истории обучающихся. | [Content rollout](question_bank_content_rollout.md). Приватные исходники и provenance не становятся публичными API ответами. |

## Удаление учебной истории

В личном Telegram-чате `/delete_data` показывает состав удаления; `/delete_data_confirm` подтверждает его в течение десяти минут. Mini App использует ту же процедуру с отдельным подтверждением. Challenge одноразовый, удаление атомарно и ограничено текущим actor. Удаляются попытки/ответы и связанные snapshots, glossary sessions, reading marks, цели, достижения, история/сессии повторений. Конкретные таблицы и каскадные связи проверяются [SQLite tests](../tests/test_privacy_data.py) и [PostgreSQL tests](../tests/postgres/test_privacy_deletion.py).

Telegram identity сохраняется для продолжения использования бота; общий банк и чужие строки не изменяются. Связанный owner PWA отклоняется до удаления: его общий учебный state нельзя потерять побочным Telegram действием. Для удаления PWA account/identity, копии всех данных и других обращений отдельный контакт/процедура владельца — UNSET. Данная команда не объявляется полным исполнением всех прав из стандартной политики.

## Оставшиеся условия проверки

- На целевой revision выполнить PostgreSQL actor-isolation/one-use tests в required CI и подтвердить additive migration/CD.
- Проверить фактические DB/backups/logs/SMTP/Cloudflare records; оператор, страны и сроки UNSET до первичных данных. Страна VPS не выводится из IP или названия хостера.
- Определить доступный канал обращений и порядок owner PWA/identity/export requests; не создавать контакт или сроки по предположению.
- Согласовать backup retention/recovery так, чтобы восстановление старой копии не выдавалось за сохранение выполненного удаления.

Статусы и Evidence остаются в [delivery plan](delivery-plan.md); AC-PRIV-01/02/05 не закрываются этим документом целиком.
