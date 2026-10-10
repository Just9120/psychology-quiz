# Obsidian Vault

Это личная база владельца E06. Она содержит summaries и самостоятельные заметки по проверенным учебным материалам, а также связи с понятиями, вопросами, терминами и книгами там, где такие связи проверены. Это не учебный раздел Telegram/Mini App/PWA, не банк вопросов и не разрешение автоматически публиковать производный контент.

По D-61 очищенный Vault поставляется сейчас в vault/ единого репозитория независимо от visibility. Публичность позже меняет владелец по желанию. Приватные исходники, Drive identifiers/URLs, review dossiers, личные данные и удержанные claims не публикуются. Локальные manifests и прежний private preview сохранены отдельно. См. [открытие Vault](../vault/README.md).

## Опубликованный пакет и проверка полноты

Пакет содержит645 вопросов,85 терминов,281 произведение/319 связей каталога и42 домашних задания.168 тем curriculum,128 с привязанными вопросами;60 вопросов без точной темы.11 понятий в confusable_with не имеют опубликованного определения: gap отмечен текстом, без выдуманной заметки. Аудиоссылки есть у36 произведений; отсутствие ссылки не доказывает отсутствие версии. Полнота относится к текущему банку, не к полному пересказу425 материалов.Также включены3 ранее подготовленные самостоятельные заметки: private source/revision/range validation повторно прошёл на сохранённых inputs. Их очищенные bodies в content/vault-notes.json проверяются по exact reviewed digest; изменение требует нового source review, status сам по себе не разрешает публикацию.1268 Markdown files включают самостоятельные понятия, полные разборы/кейсы и тематические оглавления.

```bash
python scripts/obsidian_catalogue.py --vault vault --repository-vault
python scripts/obsidian_catalogue.py --vault vault --check
python scripts/audit_public_assets.py --asset-dir vault
```

CI проверяет exact parity committed пакета и текущих разрешённых редакций. Для проверки всех known private IDs оператор добавляет --private-inventory с полным ignored inventory. Файлы детерминированы, без timestamp/личного прогресса; обновление банка требует обновления Vault. Литература использует существующий reading_order и различает text/audio/access, а не привязки к занятиям.

## Источники и локальный приватный экспорт

Canonical exporter опубликованного банка — scripts/obsidian_catalogue.py. Рабочая папка — корень репозитория, Python environment указан в [README](../README.md#быстрый-старт-и-проверки). Он использует существующий load_policy().can_publish, проверенные curriculum fingerprints и самостоятельные reading topics; не обращается к Drive/LLM или runtime DB. Ни содержимое книг, ни новые психологические утверждения из библиографии не генерируются. scripts/obsidian_vault.py сохраняется для private local manifests и как общий безопасный writer.

Manifest имеет `schema_version: 1` и массив `notes`. Для каждой заметки нужны стабильный `id`, `title`, самостоятельный `body`, приватные `source_id`, `source_revision`, `source_sha256`, `source_locator`, а также `reviewer` и `reviewed_at`. `links` ссылаются на другие IDs этого manifest; wikilinks в body тоже проверяются. Необязательные `question_ids`, `term_ids`, `literature_ids` должны разрешаться в действующих content registries. Автоматическая проверка координат/хешей не доказывает содержательную опору body: редактор сверяет тезисы с точным фрагментом источника.

Источник должен быть current `processed`, явно классифицирован как `learning_material`, иметь совпадающие revision/SHA и не находиться в unresolved conflict. Библиография или неизвестная классификация не разрешают создавать знание о содержании книги. Если review задаёт `search_ranges`, locator заметки должен совпадать с одним из проверенных диапазонов; это не approval остального текста.

Private manifest inputs храните в ignored data/ либо отдельной приватной папке. Tracked и неignored inputs отклоняются. Raw private notes с provenance экспортируются только в отдельный локальный Vault либо подтверждённый private repository; публичный пакет строится отдельным exporter только из опубликованного банка.

```bash
python scripts/obsidian_vault.py   --manifest data/vault-notes-reviewed.json   --inventory data/source-inventory-current.json   --processing data/source-processing-reviewed.json   --vault /absolute/path/to/private-vault
```

## Сохранность обновления

Exporter управляет только `generated/` с собственным state file и проверенными hashes. Личные файлы вне него не меняются; неизвестная папка, чужие/добавленные файлы, правки управляемых заметок, неизвестная версия state и незавершённый backup останавливают обновление. В private local режиме старые note IDs, отсутствующие в частичном новом manifest, сохраняются byte-for-byte для существующих ссылок и перечисляются в index как заметки предыдущих пакетов, не проверенные этим обновлением. Это не подтверждает актуальность их прежнего содержания. Повтор неизменённого обновления идемпотентен.

Staging и backup относятся только к этому export и находятся непосредственно в выбранном Vault; перед рекурсивной очисткой проверяется абсолютный target. При ошибке сохраните recovery files и выясните состояние; не удаляйте их вслепую.

## GitHub и открытие

D-61 заменяет прежний PRIVATE prerequisite D-45/50. Target остаётся vault/ единого psychology-quiz; отдельный репозиторий не меняется. Публичный exporter принимает --repository-vault только после authenticated exact origin/full_name, известной boolean visibility, archived=false и push permission. PUBLIC/PRIVATE разрешены для byte-identical render_published output, произвольный private manifest отвергается. Exporter не меняет visibility и не делает push.

В публичном пакете удалённая из банка редакция заменяется нейтральной заметкой с прежним ID; её содержимое не переопубликовывается. При published_content=True общий writer сверяет файлы с текущим render_published, проверяет retained bytes на private provenance и все wikilinks до записи. Неизвестная visibility, другой target, недоступная authentication или owner edits останавливают запись. Без --repository-vault output внутри любого checkout проекта по-прежнему запрещён.

Vault исключён из Docker build context и не является PWA/Mini App asset, API или runtime mount. Скачанная папка vault/ открывается в Obsidian, стартовая заметка generated/index.md. Структура и wikilinks проверяются автоматически; запуск native Obsidian в среде агента не подтверждён. Личные заметки сохраняйте в ignored vault/personal/, настройки .obsidian/ и корзина также ignored.

Canonical адресная проверка из корня: python -m pytest tests/test_obsidian_vault.py tests/test_obsidian_catalogue.py -q. Она проверяет source/revision/conflict gates private режима, bibliography boundary, exact committed/public-bank parity, privacy, links, сохранность owner edits/личных файлов/старых note IDs, идемпотентность и Git boundary. Проверка ссылок не подменяет содержательный source review или запуск native Obsidian.

## Сводка покрытия для владельца

`scripts/owner_source_summary.py` собирает только разрешённые агрегаты; `--notes-manifest` подтверждает подготовку заметок, а не их поставку или открытие Vault. Для сохранённых inputs без нового remote observation используйте `--saved-inputs` вместо `--observed-at`: дата означает время расчёта, output содержит observation_basis=saved_inputs, dashboard показывает эту границу. `--observed-at` относится только к известному времени наблюдения inventory; дату нельзя брать из имени файла или времени последнего content review.

```bash
python scripts/owner_source_summary.py --current data/source-inventory-current.json --processed data/source-processing-reviewed.json --reviewed --notes-manifest data/vault-notes-reviewed.json --saved-inputs --output data/owner-source-summary.json
```

Private registry/private topics задаются соответствующими optional flags только при наличии проверенных inputs. Runtime читает проверенную обезличенную `content/owner-source-summary.json`, поставляемую обычным CD; `OWNER_SOURCE_SUMMARY_PATH` задаёт явный operator override. Приватные inputs остаются вне Git. Поставка подтверждается exact revision и owner-only API readback. Нулевые и неизвестные связи различаются; unmapped notes/terms не распределяются по лекциям по сходству названий.
