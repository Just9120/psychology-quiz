# Личный Obsidian Vault

Это личная база владельца E06. Она содержит summaries и самостоятельные заметки по проверенным учебным материалам, а также связи с понятиями, вопросами, терминами и книгами там, где такие связи проверены. Это не учебный раздел Telegram/Mini App/PWA, не банк вопросов и не разрешение автоматически публиковать производный контент.

## Источники и локальный экспорт

Canonical exporter — `scripts/obsidian_vault.py`; рабочая папка — корень репозитория, Python environment указан в [README](../README.md#быстрый-старт-и-проверки). Он получает готовый приватный manifest и inventory/processing snapshots, не обращается к Drive/LLM. Локальный staging не требует GitHub; repository output по D-45 проверяет visibility через аутентифицированный GitHub CLI.

Manifest имеет `schema_version: 1` и массив `notes`. Для каждой заметки нужны стабильный `id`, `title`, самостоятельный `body`, приватные `source_id`, `source_revision`, `source_sha256`, `source_locator`, а также `reviewer` и `reviewed_at`. `links` ссылаются на другие IDs этого manifest; wikilinks в body тоже проверяются. Необязательные `question_ids`, `term_ids`, `literature_ids` должны разрешаться в действующих content registries. Автоматическая проверка координат/хешей не доказывает содержательную опору body: редактор сверяет тезисы с точным фрагментом источника.

Источник должен быть current `processed`, явно классифицирован как `learning_material`, иметь совпадающие revision/SHA и не находиться в unresolved conflict. Библиография или неизвестная классификация не разрешают создавать знание о содержании книги. Если review задаёт `search_ranges`, locator заметки должен совпадать с одним из проверенных диапазонов; это не approval остального текста.

Inputs храните в ignored `data/` либо отдельной приватной папке. Внутри checkout tracked и неignored inputs отклоняются. До окончания разработки output — существующая локальная папка Vault вне любого checkout публичного проекта. По D-45 после разработки основной репозиторий становится единым приватным; итоговый Vault находится в его vault/. Пример ниже описывает локальную подготовку до перехода.

```bash
python scripts/obsidian_vault.py   --manifest data/vault-notes-reviewed.json   --inventory data/source-inventory-current.json   --processing data/source-processing-reviewed.json   --vault /absolute/path/to/private-vault
```

## Сохранность обновления

Exporter управляет только `generated/` с собственным state file и проверенными hashes. Личные файлы вне него не меняются; неизвестная папка, чужие/добавленные файлы, правки управляемых заметок, неизвестная версия state и незавершённый backup останавливают обновление. Старые note IDs, отсутствующие в частичном новом manifest, сохраняются byte-for-byte для существующих ссылок и перечисляются в index как заметки предыдущих пакетов, не проверенные этим обновлением. Это не подтверждает актуальность их прежнего содержания. Повтор неизменённого обновления идемпотентен.

Staging и backup относятся только к этому export и находятся непосредственно в выбранном Vault; перед рекурсивной очисткой проверяется абсолютный target. При ошибке сохраните recovery files и выясните состояние; не удаляйте их вслепую.

## GitHub и открытие

D-45 заменяет прежний target отдельного приватного репозитория: итоговая база находится в `vault/` единого приватного `Just9120/psychology-quiz`. Подготовленные вне Git файлы не отправляются в текущий публичный PR. Существующий отдельный репозиторий сохраняется без новых записей и без удаления.

После завершения разработки и подтверждённого перехода основного репозитория в PRIVATE exporter принимает `--repository-vault` вместе с `--vault <checkout>/vault`. Требуются существующая папка, точный origin основного проекта и доступный аутентифицированный GitHub CLI. Перед записью exporter читает metadata именно github.com: exact full_name, private=true, archived=false и push permission. PUBLIC, неизвестная visibility, неправильный target или недоступная authentication блокируют запись без изменения заметок. Exporter не меняет visibility, не делает push и не заменяет проверку реальной внешней поставки. Без этого флага прежний запрет output в checkout/другой worktree того же проекта сохраняется.

Vault исключён из Docker build context и не является PWA/Mini App asset или runtime mount. После приватной поставки владелец открывает папку `vault/` в Obsidian. Opening smoke проверяет `generated/index.md`, wikilinks и сохранность личных файлов; результат открытия пока PENDING.

Canonical адресная проверка из корня: `python -m pytest tests/test_obsidian_vault.py -q`. Она проверяет source/revision/conflict gates, bibliography boundary, links, сохранность owner edits/личных файлов/старых note IDs, повтор обновления и Git boundary. Synthetic PASS не доказывает review реальных заметок, GitHub delivery или успешное открытие Obsidian.

## Сводка покрытия для владельца

`scripts/owner_source_summary.py` собирает только разрешённые агрегаты; `--notes-manifest` подтверждает подготовку заметок, а не их поставку или открытие Vault. Для сохранённых inputs без нового remote observation используйте `--saved-inputs` вместо `--observed-at`: дата означает время расчёта, output содержит observation_basis=saved_inputs, dashboard показывает эту границу. `--observed-at` относится только к известному времени наблюдения inventory; дату нельзя брать из имени файла или времени последнего content review.

```bash
python scripts/owner_source_summary.py --current data/source-inventory-current.json --processed data/source-processing-reviewed.json --reviewed --notes-manifest data/vault-notes-reviewed.json --saved-inputs --output data/owner-source-summary.json
```

Private registry/private topics задаются соответствующими optional flags только при наличии проверенных inputs. Runtime читает проверенную обезличенную `content/owner-source-summary.json`, поставляемую обычным CD; `OWNER_SOURCE_SUMMARY_PATH` задаёт явный operator override. Приватные inputs остаются вне Git. Поставка подтверждается exact revision и owner-only API readback. Нулевые и неизвестные связи различаются; unmapped notes/terms не распределяются по лекциям по сходству названий.
