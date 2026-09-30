# Личный Obsidian Vault

Это личная база владельца E06. Она содержит summaries и самостоятельные заметки по проверенным учебным материалам, а также связи с понятиями, вопросами, терминами и книгами там, где такие связи проверены. Это не учебный раздел Telegram/Mini App/PWA, не банк вопросов и не разрешение автоматически публиковать производный контент.

## Источники и локальный экспорт

Canonical exporter — `scripts/obsidian_vault.py`; рабочая папка — корень репозитория, Python environment указан в [README](../README.md#быстрый-старт-и-проверки). Он не обращается к Drive/GitHub/LLM: получает готовый приватный manifest и текущие inventory/processing snapshots.

Manifest имеет `schema_version: 1` и массив `notes`. Для каждой заметки нужны стабильный `id`, `title`, самостоятельный `body`, приватные `source_id`, `source_revision`, `source_sha256`, `source_locator`, а также `reviewer` и `reviewed_at`. `links` ссылаются на другие IDs этого manifest; wikilinks в body тоже проверяются. Необязательные `question_ids`, `term_ids`, `literature_ids` должны разрешаться в действующих content registries. Автоматическая проверка координат/хешей не доказывает содержательную опору body: редактор сверяет тезисы с точным фрагментом источника.

Источник должен быть current `processed`, явно классифицирован как `learning_material`, иметь совпадающие revision/SHA и не находиться в unresolved conflict. Библиография или неизвестная классификация не разрешают создавать знание о содержании книги. Если review задаёт `search_ranges`, locator заметки должен совпадать с одним из проверенных диапазонов; это не approval остального текста.

Inputs храните в ignored `data/` либо отдельной приватной папке. Внутри checkout tracked и неignored inputs отклоняются. Output — существующая отдельная папка приватного Vault, вне любого checkout этого публичного проекта. Точный локальный path задаёт владелец; пример ниже содержит placeholder и требует его замены.

```bash
python scripts/obsidian_vault.py   --manifest data/vault-notes-reviewed.json   --inventory data/source-inventory-current.json   --processing data/source-processing-reviewed.json   --vault /absolute/path/to/private-vault
```

## Сохранность обновления

Exporter управляет только `generated/` с собственным state file и проверенными hashes. Личные файлы вне него не меняются; неизвестная папка, чужие/добавленные файлы, правки управляемых заметок, неизвестная версия state и незавершённый backup останавливают обновление. Старые note IDs, отсутствующие в частичном новом manifest, сохраняются byte-for-byte для существующих ссылок и перечисляются в index как заметки предыдущих пакетов, не проверенные этим обновлением. Это не подтверждает актуальность их прежнего содержания. Повтор неизменённого обновления идемпотентен.

Staging и backup относятся только к этому export и находятся непосредственно в выбранном Vault; перед рекурсивной очисткой проверяется абсолютный target. При ошибке сохраните recovery files и выясните состояние; не удаляйте их вслепую.

## GitHub и открытие

Отдельный target `Just9120/psychology-atlas-vault` подтверждён как PRIVATE, не archived, viewer ADMIN; 30.09.2026 collaborator list содержал только владельца. Это snapshot GitHub metadata/access records, а не поставка заметок или проверка всех интеграций. Перед внешней записью повторно сверьте account, repository, visibility, актуальную revision и разрешённый scope публикации. Локальный exporter никогда не выполняет Git push и не делает репозиторий публичным.

После отдельно разрешённой поставки владелец скачивает папку Vault и открывает её в Obsidian. Opening smoke проверяет `generated/index.md`, переходы wikilinks и сохранность личных файлов. Клиенты и runtime приложения не монтируют Vault и продолжают работать без Obsidian.

Canonical адресная проверка из корня: `python -m pytest tests/test_obsidian_vault.py -q`. Она проверяет source/revision/conflict gates, bibliography boundary, links, сохранность owner edits/личных файлов/старых note IDs, повтор обновления и Git boundary. Synthetic PASS не доказывает review реальных заметок, GitHub delivery или успешное открытие Obsidian.
