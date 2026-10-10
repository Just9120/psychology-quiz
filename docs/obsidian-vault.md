# Obsidian Vault

E06 — база знаний на основе источников: самостоятельные понятия, механизмы, модели и смысловые отношения. Это не выгрузка тестов, домашних заданий или книжного каталога. Настоящие имена Markdown-файлов читаемы по-русски; темы служат точками входа, а названия занятий — только основанием утверждений. См. [открытие](../vault/README.md) и [требования](project-spec.md#e06--личная-база-obsidian).

D-61 разрешает очищенный Vault в `vault/` единого репозитория независимо от visibility; D-62 исправляет ошибочную трактовку поставки PR346/347. Экспорт не меняет публичность. Приватные исходники, Drive identifiers/URLs, досье, личные данные и удержанные утверждения остаются вне Git и клиентских assets.

## Проверенная редакция знаний

Текущий пакет содержит387 атомарных заметок,13 содержательных тематических обзоров, стартовую страницу и страницу границ:402 Markdown. Конечная сверка охватывает все425 сохранённых редакций:149 имеют прямые проверенные основания заметок,254 сопоставлены тематически как повторные изложения и практические/подготовительные материалы. Это различение не выдаёт учебное упражнение за доказательство теории или эффективности.637 прежних exact-fragment reviews сохранены;71 новая самостоятельная заметка сверена с конкретными не удержанными фрагментами. Добавлены семейные и возрастные понятия, социальное влияние, операции мышления, речь, шкалы измерения, клинические и организационные различения. Исторические модели, метафоры и ограничения вывода обозначены явно.

У всех425 редакций проверены сохранённые captures и receipts прежнего полного чтения. Три перехода от исходного PDF к актуальному extracted/OCR text подтверждены finalized receipts с хешами обеих форм и прочитанными физическими страницами.14 библиографических списков,2 организационных введения,1 личное/организационное обсуждение и5 практически полностью удержанных материалов учтены отдельно, без пустых страниц и blanket approval. Частичные удержания остальных источников сохранены. База не является буквальным пересказом каждого утверждения; неопубликованное удержанное содержание не объявлено реализованным знанием. Точная карта425 редакций с revision/SHA/locator, исходами и редакторскими основаниями хранится приватно. Публичная страница `generated/Границы базы.md` содержит только сводку и ограничения. Повторного обхода Drive нет.

## Подготовка и воспроизводимый экспорт

Canonical команда остаётся `scripts/obsidian_catalogue.py` для совместимости прежней процедуры, но теперь она не читает банк вопросов, homework, литературу, curriculum или runtime DB. Вход — очищенный `content/vault-notes.json`, schema2: `notes` с `title`, `section`, `body`, `links` (понятие → смысл отношения), `sources` (читаемые названия), и `coverage` с обзорами и границами.

Редактор сначала проверяет самостоятельность утверждения, точную опору в сохранённой редакции, удержанные фрагменты, атомарность и смысл связей. Исследовательские inputs/receipts остаются ignored. В публичный manifest переносится только whitelist знаний. Проверка exact reviewed digest в exporter закрепляет проверенную редакцию; изменение требует нового содержательного source review, а поле status не даёт разрешения. Автоматические checks проверяют воспроизводимость и структуру, но не заменяют эту сверку.

Команды из корня репозитория, Python environment — в [README](../README.md#быстрый-старт-и-проверки):

```bash
python scripts/obsidian_catalogue.py --vault vault --repository-vault
python scripts/obsidian_catalogue.py --vault vault --check
python scripts/audit_public_assets.py --asset-dir vault
python -m pytest tests/test_obsidian_vault.py tests/test_obsidian_catalogue.py -q
```

Для полного локального privacy scan добавьте `--private-inventory` с текущим ignored inventory. CI знает только tracked registry; его PASS не доказывает отсутствие неизвестных private IDs. Экспорт детерминирован, без даты запуска и личного прогресса. Изменение банка само по себе не переписывает знания.

## Сохранность и замена ошибочной выгрузки

Общий writer `scripts/obsidian_vault.py` управляет только `generated/` с собственным state и hashes. Неизвестные файлы, owner edits, symlinks, неизвестная версия state и незавершённый backup останавливают запись. Файлы вне generated не переписываются. Staging и backup находятся в выбранном Vault; очистка проверяет абсолютный owned target. При ошибке сохраните recovery files.

Для однократной замены неизменённого каталога PR347 есть явный флаг:

```bash
python scripts/obsidian_catalogue.py --vault vault --repository-vault --replace-catalogue
```

Он допускает удаление только пакета с закреплённым digest старого state, после сверки каждого старого файла. Любая личная правка, добавленный файл или иной пакет запрещают замену. Ссылки из `personal/` на удаляемые страницы также останавливают миграцию: владелец сначала сохраняет или обновляет свои ссылки. Это осознанная замена ошибочного формата, а не обычное удаление заметок при обновлении. Прежние страницы вопросов не сохраняются в новом пакете. При обычном последующем снятии понятия остаётся нейтральная заметка с прежним именем без переопубликации утверждения; повтор неизменённого обновления идемпотентен.

`--repository-vault` требует authenticated exact origin/full_name, известную boolean visibility, archived=false и push permission. PUBLIC/PRIVATE допустимы только для byte-identical очищенного render output; произвольный private manifest не проходит. Экспорт не выполняет push. Raw private mode сохраняет более строгий visibility guard.

Vault и `content/vault-notes.json` исключены из Docker build context; они не являются asset, API или mount приложения. Archive structure, portable names, wikilinks и managed-state readback проверяются автоматически. Запуск native Obsidian в среде агента не подтверждён и не подменяется проверкой файлов.

## Отдельный локальный приватный экспорт

Manifest имеет `schema_version: 1` и массив `notes`. Для каждой заметки нужны стабильный `id`, `title`, самостоятельный `body`, приватные `source_id`, `source_revision`, `source_sha256`, `source_locator`, а также `reviewer` и `reviewed_at`. `links` ссылаются на другие IDs этого manifest; wikilinks в body тоже проверяются. Необязательные `question_ids`, `term_ids`, `literature_ids` должны разрешаться в действующих content registries. Автоматическая проверка координат/хешей не доказывает содержательную опору body: редактор сверяет тезисы с точным фрагментом источника.

Источник должен быть current `processed`, явно классифицирован как `learning_material`, иметь совпадающие revision/SHA и не находиться в unresolved conflict. Библиография или неизвестная классификация не разрешают создавать знание о содержании книги. Если review задаёт `search_ranges`, locator заметки должен совпадать с одним из проверенных диапазонов; это не approval остального текста.

Private manifest inputs храните в ignored data/ либо отдельной приватной папке. Tracked и неignored inputs отклоняются. Raw private notes с provenance экспортируются только в отдельный локальный Vault либо подтверждённый private repository; публичный пакет строится отдельно из очищенных и содержательно проверенных знаний.

```bash
python scripts/obsidian_vault.py   --manifest data/vault-notes-reviewed.json   --inventory data/source-inventory-current.json   --processing data/source-processing-reviewed.json   --vault /absolute/path/to/private-vault
```


## Сводка покрытия для владельца

`scripts/owner_source_summary.py` собирает только разрешённые агрегаты; `--notes-manifest` подтверждает подготовку заметок, а не их поставку или открытие Vault. Для сохранённых inputs без нового remote observation используйте `--saved-inputs` вместо `--observed-at`: дата означает время расчёта, output содержит observation_basis=saved_inputs, dashboard показывает эту границу. `--observed-at` относится только к известному времени наблюдения inventory; дату нельзя брать из имени файла или времени последнего content review.

```bash
python scripts/owner_source_summary.py --current data/source-inventory-current.json --processed data/source-processing-reviewed.json --reviewed --notes-manifest data/vault-notes-reviewed.json --saved-inputs --output data/owner-source-summary.json
```

Private registry/private topics задаются соответствующими optional flags только при наличии проверенных inputs. Runtime читает проверенную обезличенную `content/owner-source-summary.json`, поставляемую обычным CD; `OWNER_SOURCE_SUMMARY_PATH` задаёт явный operator override. Приватные inputs остаются вне Git. Поставка подтверждается exact revision и owner-only API readback. Нулевые и неизвестные связи различаются; unmapped notes/terms не распределяются по лекциям по сходству названий.
