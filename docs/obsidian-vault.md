# Obsidian Vault

E06 — самостоятельные source-backed заметки, модели и осмысленные связи. Это база для чтения, не выгрузка вопросов, заданий или книжного каталога. D-71 заменяет публичную поставку D-61: готовый переносимый ZIP находится в закрытой папке Google Drive с результатами вне учебных источников. Код подготовки остаётся в Git. История решений и AC — в [spec](project-spec.md#e06--личная-база-obsidian).

## Подготовка и проверка пакета

Вход — приватный reviewed manifest schema2: `notes` с `title`, `section`, `body`, `links` (понятие → смысл отношения), `sources` (читаемые названия), и `coverage` с обзорами и границами. Manifest, готовые Markdown и точные source mappings не коммитятся. Inputs внутри проекта должны быть ignored и untracked. Вывод в Git working copy запрещён; внутри проекта допускается только ignored staging в `data/`.

Редактор проверяет самостоятельность тезисов, точную опору в сохранённой редакции, related holds, атомарность и смысл связей. Digest закрепляет именно проверенные bytes; изменение требует нового содержательного review. Status, кэш и совпадение метаданных не дают publication approval. ZIP содержит exact reviewed manifest, управляемые Markdown со state, README и объектный manifest. Сырьё курса, ученическая БД, личные настройки и transient download URLs не включаются.

Команды из корня проекта; environment — в [README](../README.md#быстрый-старт-и-проверки). Output должен быть новым. `EXPECTED_SHA256` заменяется digest из проверенной private receipt:

```bash
python scripts/vault_package.py create --manifest data/vault-reviewed.json --archive data/private-vault.zip
python scripts/vault_package.py check --archive data/private-vault.zip --sha256 EXPECTED_SHA256
python -m pytest tests/test_obsidian_vault.py tests/test_obsidian_catalogue.py tests/test_vault_package.py tests/test_vault_links.py tests/test_knowledge_coverage.py -q
```

`check` ничего не извлекает. Он проверяет SHA ZIP, безопасные имена/типы entries, отсутствие дублей, bounds, hashes объектов, exact reviewed edition и byte-identical render. Произвольный digest из недоверенного архива не является одобрением.

До upload подтвердите target, owner-only permissions и отсутствие дубля. После — имя, размер, parent и права. Для окончательной receipt скачайте ZIP обратно и повторите `check` с исходным SHA. Только после этого сохраняется private completion receipt. Реальные Drive IDs/URLs в Git не заносятся; старые архивы/journals не переписываются ради путей.

## Открытие и границы покрытия

Порядок открытия — в [инструкции](../vault/README.md). Архив распаковывают в отдельную папку, открывают как Vault и начинают с `generated/База знаний.md`. Проверка Markdown/links и файлового обновления не выдаётся за запуск native Obsidian или физического Android-устройства.

Сохранённый пакет от10.10 содержит387 atomic notes,13обзоров, стартовую страницу и границы:402 Markdown. Это датированная редакция по прежнему425-source scope, не подтверждение полноты текущей папки. Точная карта редакций и ограничений хранится приватно. Тематическая связь не равна независимому подтверждению. Scientific holds и исторические неопределённости сохраняются. Новая delta требует адресного review и новой редакции пакета.

Пакет от 06.11 содержит 425 заметок и 16 обзоров. В текущем индексе 489 материалов. Для 64 добавлений после прежнего снимка зафиксированы роли и границы использованных фрагментов. Исходный журнал связей по каждому из прежних 425 материалов недоступен. Идентичность состава и сохранённые основания сверены отдельно. Изменения редакций и ограничения этой проверки указаны в границах самого пакета.

Owner dashboard получает только [сводку без данных об источниках](../content/knowledge-coverage.json) от 06.11. В ней 135 заметок с однозначной связью с 41 занятием и 290 нераспределённых заметок. Проверка по каталогу этой редакции учитывает 44 занятия и оставляет три без однозначных связей. Связь по сходству названий или разделу не создаётся. Runtime digest и алгоритм квалификации проверяются CI без приватных текстов. Сводка воспроизведена из точного private manifest и каталога этой редакции. Снимок от 10.10 сохранён в прежней версии пакета и истории Git.

## Обновление существующего хранилища

```bash
python scripts/vault_package.py apply --archive data/private-vault.zip --sha256 EXPECTED_SHA256 --vault /absolute/path/to/private-vault
```

Target — существующая папка вне Git либо ignored `data/` staging. Writer меняет только собственный `generated/`, проверяет прежние hashes, version state, symlinks, неизвестные добавления и незавершённый backup. Личные правки managed notes не перезаписываются. Staging/backup находятся внутри target; ошибка замены восстанавливает прежнюю папку. При незавершённом восстановлении сохраните recovery files.

До записи проверяются обычные wikilinks и Markdown links из всех личных `.md`, включая корень и вложенные папки, aliases, URL-encoded пути, заголовки, вложенные заголовки и block IDs. Исчезновение связанной страницы или ранее существовавшего anchor останавливает обновление. Уже сломанный anchor не считается новой ошибкой, но удаление его страницы требует переноса ссылки. Кодовые примеры и внешние URL не считаются навигацией. Неизвестные plugin-specific links не интерпретируются; `.obsidian/`, canvas и вложения сохраняются byte-for-byte.

При снятии понятия сохраняется нейтральная страница с прежним именем без прежних утверждений. Если личная ссылка указывает на исчезающий заголовок, обновление останавливается: владелец сначала переносит ссылку. Данные не меняются ради прохождения проверки.

Для неизменённого quiz catalogue PR347 оставлен `scripts/obsidian_catalogue.py --manifest … --vault … --replace-catalogue`: разрешён только закреплённый старый state после проверки bytes и личных ссылок. Обычный package apply не удаляет неизвестные страницы. Старый `--repository-vault` прекращает запись независимо от visibility; PRIVATE repository не заменяет закрытую ZIP-поставку.

Личные файлы, настройки и root README/JSON скачанного пакета не переписываются. После apply результат содержит SHA применённого пакета; root JSON остаётся квитанцией исходного скачивания, не текущим личным прогрессом. Обновление одного устройства не обновляет остальные. Обратной синхронизации в approved bank нет.

## Приватные основания и сводка источников

`scripts/obsidian_vault.py` сохраняет raw private export schema1 с ID, revision/SHA/locator/reviewer/reviewed_at. Вывод также только вне Git или в ignored `data/`. Источник должен быть current `processed`, `learning_material`, без unresolved related conflict; `search_ranges` ограничивает locator. Библиография или неизвестная классификация не разрешает знание о содержании книги. Содержательная сверка обязательна сверх hashes.

```bash
python scripts/obsidian_vault.py --manifest data/vault-notes-reviewed.json --inventory data/source-inventory-current.json --processing data/source-processing-reviewed.json --vault /absolute/path/to/private-vault
python scripts/owner_source_summary.py --current data/source-inventory-current.json --processed data/source-processing-reviewed.json --reviewed --notes-manifest data/vault-notes-reviewed.json --saved-inputs --output data/owner-source-summary.json
```

`--saved-inputs` означает расчёт по сохранённым inputs, не новое remote observation. `--observed-at` задают по фактическому времени наблюдения inventory. Optional registry/topic inputs используют при наличии проверенных данных. Runtime читает разрешённые агрегаты, не приватный ledger; unmapped notes не распределяются по сходству названий. Vault и inputs исключены из Docker и клиентских assets/API независимо от visibility.
