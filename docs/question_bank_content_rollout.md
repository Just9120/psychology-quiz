# Поставка банка вопросов и сохранение попыток

Canonical derivative — JSON в content/questions; [seed](../scripts/seed_questions.py) читает полный набор module directories. Это authoritative sync: approved rows обновляются, supplied non-approved IDs снимаются с выдачи, отсутствующие IDs становятся retired. Частичный вызов DB helper не снимает approval с неуказанных IDs. Вопросы и пользовательская история физически не удаляются.

При включении вопроса в попытку [attempt content](../app/attempt_content.py) сохраняет JSON v1, SHA-256 и provenance `captured` в quiz_session_questions. Текущий вопрос, варианты, оценка и feedback в API и классическом Telegram используют этот snapshot. Изменение текста, порядка/числа вариантов, верного ответа, approval или удаление JSON не меняет существующую попытку. Новые attempts используют актуальный approved банк.

Additive migration [init](../scripts/init_db.py) и bot startup заполняют отсутствующие snapshots до seed с provenance `legacy_backfill_current`. Это доступная на момент миграции редакция, а не восстановленный исторический оригинал. Оригинальные answers/score не пересчитываются. Hash проверяется при чтении, DB trigger запрещает перезапись сохранённой редакции. Transaction защищает связанное чтение question/options; повторная migration/seed не заменяет snapshot.

## Release gate

Поставка следует [действующей VPS процедуре](miniapp-deployment-qa.md#действующие-правила-и-delivery-snapshot). Для schema/seed changes класс BACKWARD_COMPATIBLE_AUTOMATED: добавить поля, не удалять существующие; на время backup/migration остановить writers. Build candidate происходит до изменения DB. SQLite backup API и isolated restore rehearsal обязательны; затем init/backfill → seed → integrity/FK и сравнение прежних user fields → snapshots/serving smoke и canonical parity → runtime start/version/health. Проверенные команды и порядок заданы [deploy.sh](../deploy.sh), [DB checks](../scripts/deployment_db.py) и [parity audit](../scripts/audit_question_bank.py).

При failed migration/post-check не продолжать поставку и не восстанавливать production автоматически. Сохранить backup/manifest, run ID и candidate SHA; сверить DB integrity/user preservation и подготовить forward-fix. Старый backend не читает snapshots, поэтому приложение не откатывается автоматически даже при совместимой additive schema. Отсутствующая/повреждённая редакция не подменяется текущим content.

Массовое обновление content — отдельный согласованный scope: content смонтирован read-only с host checkout, который обновляется до runtime restart. Эта Goal не меняет content files. Размещение больших releases и проверка duration/lock window определяются до соответствующей поставки; неизменённый банк не требует искусственного content rollout.

## Unfinished sessions

После внедрения snapshots обычный seed не требует abandon активных attempts: они продолжают исходную редакцию. [abandon script](../scripts/abandon_in_progress_sessions.py) остаётся только для отдельно разрешённой операции закрытия попыток. Он не восстанавливает смысл ранее изменённой истории и не вызывается автоматически CI/CD или startup.
