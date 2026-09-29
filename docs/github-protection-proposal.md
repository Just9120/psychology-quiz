# Предложение защиты `main` и production

Статус: **подготовлено, не применено**. Владелец 29.09.2026 поручил подготовить конфигурацию F-003 без изменения GitHub settings. Перед возможным применением перечитать фактические branch protection, rulesets, Environment и названия успешных checks: приведённые тела запросов заменяют соответствующие настройки. Не применять их по одной этой странице.

Проверенный 29.09.2026 GitHub state: `main` branch protection не настроена (GET возвращает 404), repository rulesets — пустой список, у Environment `production` нет protection rules и deployment branch policy. По CI на `main` `17d59cc1a4b2907fd853b98dd34a085a630b07e6` проходят jobs `pwa-client` и `validate-and-smoke-test`; CD для этой revision успешен. Источник — GitHub API/Actions records `36575130989` и `36575538001`; этот снимок не доказывает будущего состояния.

Предлагаемая branch protection для `main` (REST `PUT /repos/Just9120/psychology-quiz/branches/main/protection`):

```json
{
  "required_status_checks": {
    "strict": true,
    "contexts": [],
    "checks": [
      {"context": "pwa-client"},
      {"context": "validate-and-smoke-test"}
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "require_code_owner_reviews": false,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": false,
  "lock_branch": false
}
```

Ненулевой объект `required_pull_request_reviews` требует путь через PR, а `required_approving_review_count: 0` не вводит обязательного чужого approval. `strict: true` требует checks на актуальной относительно `main` revision. Прежде чем применять, проверить у GitHub фактическую семантику этих полей для личного публичного репозитория; если API отклонит конфигурацию или readback расходится, остановиться, не подменяя её более слабым правилом. Existing required review или ruleset, появившиеся после снимка, нельзя затирать.

Предлагаемая production Environment (REST `PUT /repos/Just9120/psychology-quiz/environments/production`):

```json
{
  "wait_timer": 0,
  "prevent_self_review": false,
  "reviewers": null,
  "deployment_branch_policy": {
    "protected_branches": false,
    "custom_branch_policies": true
  }
}
```

Затем отдельным REST `POST /repos/Just9120/psychology-quiz/environments/production/deployment-branch-policies` создать ровно один branch pattern:

```json
{"name": "main", "type": "branch"}
```

Порядок применения важен: до появления pattern `main` Environment может остановить CD. После каждого изменения прочитать protection, rulesets, Environment и список branch policies; проверить, что PR с актуальными двумя jobs допускается к merge, прямой push и failed/skipped required check не допускаются, а CD от `main` получает доступ к Environment. Проверка должна использовать тестовую ветку/PR и штатные Actions без повторного production deploy ради одного статуса. Фактический F-003 останется OPEN до отдельного поручения, успешного readback и проверенного поведения.
