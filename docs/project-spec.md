# PsychologyAtlas — спецификация проекта

## Назначение и границы

PsychologyAtlas — личная учебная платформа владельца для фундаментального изучения психологии по его программе и материалам. Учебные контуры: тесты, глоссарий, повторение, прогресс, база знаний, литература, домашние задания и практические кейсы. Модули сохраняются как структура программы и metadata; основная навигация ориентирована на дисциплины и темы.

Поддержка независимого состояния нескольких пользователей нужна в data model с первого этапа. Открытие доступа студентам не является обязательством первого этапа. PWA — стратегический основной клиент; Mini App — быстрый quiz runner; classic Telegram — лёгкий fallback.

Ни наличие требования, ни supporting RFC не разрешает реализацию. Пользователь выбирает следующий scope; задачи, статусы AC, Evidence, аудиторская оценка и delivery находятся только в [плане](delivery-plan.md). Наличие AC в этой спецификации не объявляет функцию реализованной.

## Источники и приоритет

| ID | Источник и область |
| --- | --- |
| SRC-01 | Предоставленный пользователем Google Doc, file ID `1V--6vLsM8qSwtPNFQ9MQDp4mW9wlFNufHxxp07tMP1M`; modifiedTime `2026-09-16T11:07:25.174Z`; полностью прочитан через Google Drive 2026-09-19. Разделы источника указаны у каждого эпика ниже. Это согласованный продуктовый и технический intent. |
| SRC-02 | Явное поручение пользователя 2026-09-19 принять новые workflow-документы и дополнительно перенести весь scope/AC из SRC-01. Разрешает документацию, не реализацию платформы. |
| SRC-03 | Прежняя репозиторная спецификация на `ddc661172b50f549a8e1ef4ef8ff5ab54152ae64`: сохраняемые правила classic/Mini App совместимости и legacy контента, если они не отменены SRC-01. |
| SRC-04 | Предоставленные workflow templates от 2026-09-12: [AGENTS.md](../AGENTS.md) и [ci-cd-rules.md](../ci-cd-rules.md). Правила работы и CI/CD; не источник учебных знаний. |

Явные решения пользователя имеют приоритет. Этот spec задаёт согласованные требования; план — состояние работы. Код/config и tests — Evidence фактической реализации, не основание переписывать intent. Supporting docs и исторические отчёты не расширяют scope.

Единственный первичный источник учебных знаний — Google Drive, папка «Психология», folder ID `119DpAwq3T_9JzlTRMPeB7LX7-vpeO95U`, и её вложенные материалы. Read-only inventory 2026-09-19 подтвердил корень и восемь непосредственных подпапок (модули 1–6, «Литература», «Другое»); это не полный рекурсивный inventory и не содержательная сертификация corpus. JSON approved content — контролируемое производное содержимое; runtime DB, indexes и Obsidian не являются первичными источниками знаний.

## Эпики, business rules и AC

Каждая строка связывает стабильный requirement ID с AC. Формат критерия: условие/действие → наблюдаемый результат; затем способ проверки. AC со словом «позже» или «опционально» сохраняют условный scope исходного требования; их включение в implementation Goal требует решения. Числовые SLO, coverage targets, алгоритмы и новая политика доступа здесь не вводятся.

### Граница обязательного и условного scope

Каталог содержит 76 AC. Обязательный согласованный scope — 67 AC, включая отложенные по очередности обязательные разделы. Девять условных AC сохраняются отдельно: AC-PROG-06, AC-GLO-03, AC-SRH-03/04/05, AC-LIT-04/05, AC-PRC-05, AC-AUTH-04. Их условия — отдельное решение о mastery, дополнительных карточках, иной vector DB, RAG, taxonomy/reader, API/voice и OAuth. Они не удалены и не выполнены автоматически из-за отсутствия реализации. Scope выбранной Goal может быть существенно уже всего проекта.

Это уточнение D-08 от 2026-09-19 сохраняет optional intent SRC-01, не отменяет критерии и не разрешает implementation. В аудите обязательная готовность считается по 67 AC; доля READY по всему каталогу 76 AC приводится отдельно, чтобы знаменатель был прозрачен. После явного включения условной возможности её AC входит в обязательный scope с записью решения; предыдущие snapshots не переписываются.

### E01 — Platform/data foundation и клиенты

Источник SRC-01: «Общая концепция», «Пользователи», «Клиенты», «User model», «Основные технологии», «Клиенты и учебное состояние».

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-FND-01 / AC-FND-01 | При работе владельца учебные сущности организованы по дисциплинам/темам с module metadata; классификация не создаёт дубликаты исходных файлов. Проверка: data fixtures и навигационный сценарий. |
| R-FND-02 / AC-FND-02 | Два пользователя работают с attempts, progress, errors, repetitions, bookmarks, assignments и literature state → состояние каждого независимо, approved content общий. Проверка: integration tests чтения/записи и попыток доступа к чужим данным. |
| R-FND-03 / AC-FND-03 | Запуск целевой платформы → Python/FastAPI обслуживает общий backend; bot/content processing/server analytics остаются на Python без отдельного решения о другом языке. Проверка: entrypoints, dependency manifests и API smoke. |
| R-FND-04 / AC-FND-04 | Сборка PWA и Mini App → React + TypeScript + Vite, оба клиента используют общий банк и backend state. Проверка: build/typecheck и cross-client contract tests. |
| R-FND-05 / AC-FND-05 | Перенос runtime с SQLite → PostgreSQL сохраняет identities, attempts и пользовательский прогресс; повтор/ошибка migration не уничтожает исходные данные. Проверка: migration fixtures, reconciliation и согласованный recovery rehearsal до production. |
| R-FND-06 / AC-FND-06 | Пересборка approved content/runtime indexes/embeddings → первичные Drive sources и user learning state не изменяются. Проверка: integration fixtures и сравнение состояния до/после. |
| R-FND-07 / AC-FND-07 | Один ответ повторно отправлен из разных клиентов → учитывается один раз; потеря связи не превращается в неправильный ответ. Проверка: повторные/конкурентные API requests и network-failure scenario. |
| R-FND-08 / AC-FND-08 | Клиент закрыт или сервер перезапущен после сохранения ответа → ответы и прогресс восстанавливаются. Проверка: restart/integration scenario для всех использующих состояние клиентов. |
| R-FND-09 / AC-FND-09 | PWA открыта на desktop/mobile без Telegram → доступны разрешённые учебные разделы и навигация; offline не обязателен. Проверка: browser smoke на обоих размерах и без Telegram context. |
| R-FND-10 / AC-FND-10 | Пользователь использует Mini App/classic fallback → правила ответа, scoring и доступного прогресса согласованы с PWA; сложные knowledge/literature/analytics flows не переносятся в classic без отдельного решения. Проверка: cross-client сценарии и review scope. |

### E02 — Sources, provenance и content pipeline

Источник SRC-01: «Google Drive», «Обновление источников», «Provenance», «Content pipeline», «Обновление контента».

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-SRC-01 / AC-SRC-01 | Обработка «Психологии» → учитываются вложенные транскрипты лекций/практик, glossary, PDF, задания и списки литературы; пустые папки пропускаются. Проверка: nested Drive inventory fixtures, pagination и empty-folder case. |
| R-SRC-02 / AC-SRC-02 | Материалы одного занятия представлены разными форматами/папками → они связаны metadata без дублирования учебного занятия и исходного файла. Проверка: fixture с транскриптом, презентацией, glossary и практикой. |
| R-SRC-03 / AC-SRC-03 | Источник новый, неизменённый или изменённый → pipeline различает эти состояния и показывает обработанное/необработанное; повторная обработка обновляет производные связи без потери прогресса. Проверка: incremental processing tests. |
| R-SRC-04 / AC-SRC-04 | Производный материал предлагается к approval → есть Drive file ID и использованная редакция; страница/timestamp/фрагмент сохранены, когда доступны. Неподтверждённое не публикуется как approved. Проверка: provenance validator и отрицательные fixtures. |
| R-SRC-05 / AC-SRC-05 | Источники противоречат друг другу → сведения не объединяются автоматически; материал направляется на проверку источника. Проверка: conflict fixture и review record. |
| R-SRC-06 / AC-SRC-06 | Книга присутствует только в библиографии → её содержание не используется как знание без доступного source corpus; интернет, LLM, Obsidian и старые вопросы не подменяют corpus. Проверка: source review и negative approval cases. |
| R-SRC-07 / AC-SRC-07 | Новый файл появился в Drive → он не публикуется автоматически; coding/reasoning agent подготавливает и проверяет derivative content до approval через repository/content pipeline. Проверка: publication-state tests и review trail. |
| R-SRC-08 / AC-SRC-08 | Пользователь проходит тест либо редактируется контент → runtime не генерирует вопросы через LLM; публичного editor UI и ручной DB-правки как пути публикации нет. Проверка: runtime dependencies/routes и publication tests. |

### E03 — Тесты и качество банка

Источник SRC-01: «Банк вопросов», «Аудит качества банка», «Режимы тестирования», «Объяснения и связь с базой знаний».

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-QUIZ-01 / AC-QUIZ-01 | Запуск теста → выбираются только approved вопросы; темы получаются из фактического backend content, не hardcoded во frontend. Проверка: смешанные статусы и изменение набора тем в integration fixtures. |
| R-QUIZ-02 / AC-QUIZ-02 | Выбрана тема, микс или все темы и количество/все доступные вопросы → выдача соответствует scope; неверные или недоступные категории отклоняются server-side. Проверка: setup/selection tests, empty-content и invalid-ID cases. |
| R-QUIZ-03 / AC-QUIZ-03 | Выбрана обычная random выборка → она остаётся доступной; adaptive режим учитывает недавние вопросы, ошибки и слабые темы, избегает постоянных повторов и не исключает повторение по расписанию. Проверка: history fixtures; точная policy — Q-03. |
| R-QUIZ-04 / AC-QUIZ-04 | Пользователь выбирает тест → easy/medium/hard допустимы как metadata, но не обязательный главный шаг выбора. Поздняя статистическая калибровка не выводит общую сложность из ошибки одного человека. Проверка: UX scenario; statistical rule — Q-03. |
| R-QUIZ-05 / AC-QUIZ-05 | Пользователь отвечает → видит правильный ответ и краткое explanation, если оно есть; доступен переход к связанной knowledge topic и исходному материалу с проверкой доступа. Проверка: answer/API и navigation tests, отсутствующее explanation. |
| R-QUIZ-06 / AC-QUIZ-06 | Аудит существующих questions и glossary → проверены смысл, ответы, объяснения, неоднозначность, дубли и sources; спорное/неподтверждённое явно отмечено, source_ref/approved не считаются доказательством сами по себе. Проверка: source-backed review ledger и regression cases. |
| R-QUIZ-07 / AC-QUIZ-07 | Исправляется банк → рабочий legacy контент сохраняется до контролируемой замены; практические вопросы остаются в своей предметной теме, учебная история не искажается. Проверка: rollout/parity tests совместно с AC-PROG-04. |

**Решение PLATFORM-STABILIZATION-001 / Q-02, 19.09.2026:** при включении вопроса в попытку SQLite сохраняет immutable JSON snapshot формата v1 (external ID, текст, объяснение, источник, категория, difficulty, порядок/тексты вариантов и correctness), SHA-256 и provenance `captured`. Все quiz clients оценивают и показывают feedback по этой редакции; повторный seed её не переписывает. Additive migration до изменения serving content заполняет старые attempts доступной текущей редакцией с provenance `legacy_backfill_current`: это не доказательство первоначально показанного текста; прежние answers/score остаются без пересчёта. Доступные редакции не восстанавливают уже утраченные до миграции данные. Полный seed синхронизирует статусы; отсутствующие canonical IDs помечаются retired, physical delete attempts/questions не выполняется. Non-approved вопросы не входят в новые attempts, существующие продолжаются по snapshot. Repetition learning/relearning и PostgreSQL остаются вне этого решения.


### E04 — Повторение и личный прогресс

Источник SRC-01: «Интервальное повторение», «Прогресс».

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-PROG-01 / AC-PROG-01 | Есть история ответов пользователя по вопросам и терминам → формируется due-list; ошибочные/неустойчивые знания возвращаются чаще устойчивых, не только по глобальной difficulty. Проверка: deterministic time/history fixtures; алгоритм — Q-03. |
| R-PROG-02 / AC-PROG-02 | Открыт режим ошибок или повторения на сегодня → показан соответствующий персональный набор; пустая очередь корректно объясняется. Проверка: API/UI cases для двух пользователей и empty queue. |
| R-PROG-03 / AC-PROG-03 | Пользователь открывает прогресс → видны история, процент правильных ответов, слабые темы и динамика по дисциплинам/темам. Результат попытки отличим от mastery; при недостатке истории нет уверенной оценки знаний. Проверка: aggregation fixtures и UI; mastery policy — Q-03. |
| R-PROG-04 / AC-PROG-04 | Вопрос/варианты/правильный ответ исправлены или вопрос заменён → прежние attempts сохраняют исходный смысл; новый материал не становится автоматически выученным, повторение учитывает изменение. Проверка: versioned-content migration/regression fixtures; representation — Q-02. |
| R-PROG-05 / AC-PROG-05 | Запрошен сброс темы/всего обучения → требуется явное подтверждение; чужой прогресс, bookmarks, литература, заметки и прочий user content не удаляются. Проверка: authorization, cancel/confirm и transactional tests. |
| R-PROG-06 / AC-PROG-06 | Позже вводится mastery → оценка учитывает устойчивость повторения, а не только правильные ответы; формула и достаточность истории согласованы заранее. Проверка: temporal fixtures по принятой Q-03 policy. |

### E05 — Глоссарий

Источник SRC-01: «Термины».

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-GLO-01 / AC-GLO-01 | Открыт glossary contour → доступен quiz терминов/определений по теме с персональным результатом. Проверка: glossary runtime/API и cross-user tests. |
| R-GLO-02 / AC-GLO-02 | Термин связан с knowledge → доступны переходы к atomic notes/темам; его история участвует в общей системе повторения. Проверка: link integrity и integration с E04/E06. |

Glossary retry contract (PLATFORM-STABILIZATION-001): вопрос/порядок вариантов фиксируется на `(session_id, step_id)`. API answer/next передают положительный целочисленный step_id из current_question; повтор того же answer возвращает сохранённый feedback без повторного score, другой answer уже отвеченного шага отклоняется. Next продвигает только названный отвеченный шаг один раз; поздние запросы не изменяют другой шаг. Dedicated routes и existing `/miniapp/setup`/`answer` adapter имеют одинаковый контракт. Запрос answer/next без step_id получает `glossary_step_required` и требует переоткрыть актуальную Mini App; это безопасная граница совместимости старого неоднозначного формата. Chat glossary и normal quiz protocol сохраняются. In-memory sessions/restart lifetime остаются ограничением F-018; durable persistence в эту Goal не входит.
| R-GLO-03 / AC-GLO-03 | Если выбран дополнительный PWA term-card scope → видны definition, связанные понятия и разрешённые source references. Проверка: browser/access cases. Карточка — опциональное дополнение к quiz. |

### E06 — Knowledge layer и Obsidian

Источник SRC-01: «Knowledge layer», «Obsidian».

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-KNW-01 / AC-KNW-01 | Обработан source-backed материал → summaries и atomic notes самостоятельны по смыслу, связаны между собой и с sources, пригодны для навигации/retrieval. Проверка: provenance/link validator и содержательный source review. |
| R-KNW-02 / AC-KNW-02 | Владелец открывает knowledge section в PWA → доступны статьи и применимые связи с понятиями, questions, glossary, sources и literature. Доступ других пользователей определяется Q-01. Проверка: navigation/access tests. |
| R-KNW-03 / AC-KNW-03 | Экспортирована база → Markdown можно открыть как Obsidian Vault, links разрешаются, atomic notes сохраняют смысл. Проверка: export fixture/link check и opening smoke. |
| R-KNW-04 / AC-KNW-04 | Vault обновляется → личные заметки владельца сохраняются, не попадают автоматически в approved content; обратная синхронизация правок отсутствует в обязательном scope. Проверка: update fixture с personal files. |
| R-KNW-05 / AC-KNW-05 | Obsidian не установлен/не открыт → Telegram и PWA продолжают работать с knowledge backend. Проверка: runtime/dependency isolation scenario. |

### E07 — Поиск и optional RAG

Источник SRC-01: «Semantic search», «Optional RAG», «Основные технологии».

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-SRH-01 / AC-SRH-01 | Запрос по словам или смыслу, включая перефразирование лекции → возвращаются релевантные доступные материалы с source refs без обязательного AI-ответа. Проверка: curated retrieval set, empty/no-access cases; числовой target — UNSET. |
| R-SRH-02 / AC-SRH-02 | Строится semantic index → используется PostgreSQL/pgvector как пересобираемый derivative; отдельная vector DB не обязательна. Проверка: rebuild и source/user-state invariants. |
| R-SRH-03 / AC-SRH-03 | Рассматривается другая vector DB → решение основано на измеренном corpus/performance ограничении PostgreSQL. Проверка: decision record до изменения архитектуры; текущая миграция к Qdrant не запрошена. |
| R-SRH-04 / AC-SRH-04 | Позже включается RAG → ответы основаны на retrieved материалах, сохраняют sources, используют ограниченный контекст; основной UX работает без LLM API. Проверка: grounding/access/failure cases. |
| R-SRH-05 / AC-SRH-05 | RAG предлагается как постоянная production feature → отдельно оценены полезность и tokenomics, получено решение о включении. Проверка: decision record; provider/model/budget — Q-05. |

### E08 — Домашние задания

Источник SRC-01: «Учебные задания».

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-HWK-01 / AC-HWK-01 | Задание обнаружено в Drive → доступно в отдельном учебном контуре по module/discipline/topic независимо от исходной папки, со ссылкой на source. Проверка: ingestion/navigation fixtures. |
| R-HWK-02 / AC-HWK-02 | Пользователь меняет состояние задания → сохраняются «не начато», «в работе», «выполнено» только для него; неверное состояние/чужое изменение отклоняется. Проверка: state/authorization tests. |
| R-HWK-03 / AC-HWK-03 | Для задания существуют связанные материалы → доступны связи с темой, knowledge и другими материалами; отсутствие применимой связи не выдумывается. Проверка: link integrity и access cases. |

### E09 — Литература / Reading Tracker

Источник SRC-01: «Reading tracker».

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-LIT-01 / AC-LIT-01 | Списки литературы поступили из разных учебных материалов → единый каталог сохраняет module/topic/source связи. Проверка: multi-source ingestion и duplicate review. |
| R-LIT-02 / AC-LIT-02 | Пользователь отмечает книгу → доступны «не начато», «читаю/слушаю», «прочитано», «отложено» и progress, когда его удобно определить; чужое состояние недоступно. Проверка: state/auth/persistence tests; mapping legacy statuses — Q-04. |
| R-LIT-03 / AC-LIT-03 | В каталоге текстовая книга или аудиокнига → оба формата поддерживаются; для коммерческого источника достаточно metadata и легального outbound reference без файла в corpus. Содержимое книги не считается доступным знанием. Проверка: format/source fixtures. |
| R-LIT-04 / AC-LIT-04 | Если выбрана классификация значимости → видны согласованные уровни (например, базовая/важная/дополнительная/углублённая). Проверка: metadata/UI review; конкретная taxonomy не предписана. |
| R-LIT-05 / AC-LIT-05 | Позже добавляются связи с авторами/atomic notes или PDF/EPUB reader → сохраняются provenance и права; встроенный reader не обязателен для первого среза. Проверка: feature-specific navigation/access cases. |

### E10 — Учебная практика через внешнюю модель

Источник SRC-01: «Моделирование сессии клиент–психолог», «Внешняя модель по подписке», «Voice».

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-PRC-01 / AC-PRC-01 | Создан кейс → вводная ученика отделена от роли клиента; допустим вымышленный клиент, но психологические основания и критерии разбора связаны с corpus. Проверка: case schema и source review. |
| R-PRC-02 / AC-PRC-02 | Экспортирован structured case package → есть кейс, роль, материалы, ограничения и критерии; пакет можно передать внешней модели по подписке без встроенного LLM API. Проверка: export fixtures и manual handoff smoke. |
| R-PRC-03 / AC-PRC-03 | Идёт упражнение → role instructions исключают подсказки консультанту и показ скрытого контекста как подсказки. Техническая секретность экспортируемого пакета от самого пользователя не обещается. Проверка: package review/scenario. |
| R-PRC-04 / AC-PRC-04 | Сессия завершена → можно сформировать отдельный transcript-analysis package с инструкциями, материалами и критериями; feedback учебный, не оценка профессиональной компетентности. Проверка: export fixture и copy review. |
| R-PRC-05 / AC-PRC-05 | Позже выбирается direct API/voice → сначала оцениваются польза/стоимость; voice использует ту же case/evaluation logic. Возврат/хранение transcript не входят в обязательный первый этап. Проверка: decision record и parity tests; Q-05. |

### E11 — Аккаунты и права

Источник SRC-01: «Пользователи», «User model», «Регистрация и доступ».

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-AUTH-01 / AC-AUTH-01 | Пользователь регистрируется/входит в PWA по e-mail/паролю → аккаунт не зависит только от Telegram ID; неверные credentials не дают доступ. Проверка: auth integration и negative cases. |
| R-AUTH-02 / AC-AUTH-02 | Запрошены подтверждение e-mail/восстановление доступа → используются настроенные письма Яндекс 360; недействительное/повторное подтверждение и ошибка отправки обрабатываются без выдачи доступа. Проверка: mail/auth integration; token policy — Q-06. |
| R-AUTH-03 / AC-AUTH-03 | Пользователь пришёл через sharing или не имеет owner-роли → owner features/личные данные закрыты; guest/student доступ не предполагается до решения. Проверка: role/access matrix; Q-01. |
| R-AUTH-04 / AC-AUTH-04 | Позже добавлен Google OAuth → связывание с существующим аккаунтом не создаёт отдельный прогресс и не позволяет захватить чужую identity. Проверка: linking/conflict cases; Q-01. |
| R-AUTH-05 / AC-AUTH-05 | Telegram аккаунт связывается с платформенным → принадлежность подтверждается, состояние не смешивается/не теряется. Проверка: identity migration и ownership tests; точный linking flow — Q-01. |

### E12 — Owner content dashboard

Источник SRC-01: «Owner dashboard», «Обновление контента».

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-OWN-01 / AC-OWN-01 | Владелец открывает dashboard → видны counts questions/materials по темам, source coverage, новые/необработанные источники и content gaps. Проверка: inventory/aggregation fixtures. |
| R-OWN-02 / AC-OWN-02 | У материала нет производных notes/glossary/questions или тема недостаточно покрыта → это различимо без выдуманного универсального порога достаточности. Проверка: fixtures; пороги при необходимости — Q-07. |
| R-OWN-03 / AC-OWN-03 | Не-owner запрашивает dashboard/analytics → персональные и operational данные не раскрываются; editing approved content остаётся в repository pipeline. Проверка: auth/API negative cases. |

### E13 — Deployment, безопасность и восстановление

Источник SRC-01: «Production», «Клиенты и учебное состояние»; SRC-03: privacy/owner restrictions.

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-OPS-01 / AC-OPS-01 | Поставляется runtime → Docker/VPS остаются baseline; Nginx обслуживает HTTPS и раздельно маршрутизирует PWA/Mini App/API без изменения application logic. FastAPI/PostgreSQL напрямую в internet не публикуются. Проверка: config review и безопасные exposure checks. |
| R-OPS-02 / AC-OPS-02 | Меняется code/content → GitHub Actions обеспечивает контролируемую поставку проверенной revision; exact target, validation/artifact и post-checks восстанавливаются из records. Проверка: CI/CD records и правила [ci-cd-rules.md](../ci-cd-rules.md). |
| R-OPS-03 / AC-OPS-03 | Меняется content/schema → migration/rollout контролируется, сохраняет прогресс и имеет применимые stateful/recovery gates. Проверка: preconditions, migration fixtures и post-checks по согласованному rollout. |
| R-OPS-04 / AC-OPS-04 | Нужен backup/restore → user data восстанавливаются отдельно от пересобираемых content/indexes. Проверка: изолированный restore rehearsal и reconciliation; период/RPO/RTO — UNSET, не выдумываются. |
| R-OPS-05 / AC-OPS-05 | Выполняются auth/runtime операции → secrets, initData, credentials и production owner ID не попадают в репозиторий/логи/артефакты; приватные данные доступны только по правам. Проверка: negative/log tests и review. |

### E14 — Совместимость существующего Telegram продукта

Источник SRC-03; применяется до отдельной согласованной миграции, без превращения legacy UX в целевую платформенную архитектуру.

| Requirement / AC | Условие → результат; проверка |
| --- | --- |
| R-LEG-01 / AC-LEG-01 | Classic quiz запускается через /quiz или меню → доступны single/selected_mix/all, session-selected темы, выбор 5/10/15/всех доступных вопросов и обратная связь; вопросный контент остаётся русским. Проверка: classic/runtime regression tests. |
| R-LEG-02 / AC-LEG-02 | Используются /start, /help, скрытие меню и чтение → меню восстанавливается после квиза, чтение поддерживает обычный/бионический вид; reply keyboard и inline fallback сохраняются до решения о смене UX. Проверка: handler tests и Telegram smoke. |
| R-LEG-03 / AC-LEG-03 | /ui или «В окне» → fresh inline WebApp launch, компактный bootstrap, backend hydration, server-side validation; legacy inline context fallback не ломается. До отдельной UX-миграции /ui остаётся opt-in setup chooser даже при активной попытке с предупреждением о её завершении; chat /glossary остаётся отдельным glossary quiz. Проверка: context/entrypoint/API/frontend contracts. |
| R-LEG-04 / AC-LEG-04 | Не-owner или групповой чат вызывает /stats → доступ закрыт; разрешённый private owner получает только агрегаты; команда не становится публичным меню. Проверка: access/handler tests. |
| R-LEG-05 / AC-LEG-05 | Меняется runtime config → polling остаётся default, webhook включается явной конфигурацией; classic работает без MINI_APP_URL, отключённый legacy in-bot HTTP path не подменяет dedicated FastAPI. Проверка: config/runtime tests. |
| R-LEG-06 / AC-LEG-06 | Мигрируются текущие JSON IDs/topic registry → сохраняются downstream references и понятный путь миграции; legacy m1-q3 не переименовывается без проверки связей. Проверка: validators, parity и migration fixtures. |

## Интерфейсы, данные и зависимости

Логические слои: source corpus → проверяемый derivative/approved content → пересобираемые serving/search indexes; отдельно accounts, attempts/answers, repetitions, progress, bookmarks, assignments, literature state и личные заметки. Редакции sources и content должны позволять восстановить смысл старых attempts. Конкретные PostgreSQL schema, migration order и linking contract определяются до реализации E01/E11 (Q-01/Q-02).

Существующие Mini App routes /miniapp/state, /setup-options, /setup, /answer и literature topics/items/state/progress — совместимые интерфейсы переходного периода; полные paths и payloads проверяются по backend и [hydration contract](miniapp_setup_hydration.md). Telegram initData остаётся недоверенным input до backend verification; PWA auth не подменяется Telegram ID.

E04 зависит от user identity и content versioning. E06/E07 требуют provenance; E05/E08/E09 связываются с knowledge по мере его появления. E10 сначала использует export без runtime LLM. Минимальная PWA должна быть доступна к появлению зависящих от неё учебных разделов. Точный порядок PR — в плане.

Технические ограничения: PostgreSQL/pgvector вместо добавления обязательного vector service; React/TypeScript/Vite для новых клиентов; Python/FastAPI backend; Docker/VPS/Nginx для production; Яндекс 360 для account mail. Нет согласованных throughput/latency/availability targets; их нельзя выводить из выбранного stack. Учебная обратная связь не является профессиональной сертификацией.

## Принятые решения и изменённые ограничения

- D-01 (SRC-01/SRC-02): прежний запрет standalone Web UI/PWA заменён целевым PWA scope E01. Classic остаётся fallback, а не стратегическим центром новых функций.
- D-02: прежний SQLite baseline — исходная реализация для перехода; target PostgreSQL. Изменение docs не выполняет migration и не разрешает потерю user state.
- D-03: первичен Drive corpus; JSON и Obsidian — производные. Старые repository-evidence reviews не объявляются source-certified и не заменяют AC-SRC-04/AC-QUIZ-06.
- D-04: полный запрет RAG заменён optional future RAG после оценки; запрет runtime LLM-генерации тестовых вопросов сохраняется.
- D-05: исторические RFC о /next, reminders/reading plans и private-note UI не создают обязательств SRC-01; они требуют отдельного решения. Reader, OAuth, voice и direct LLM API сохраняют свой поздний/опциональный характер.
- D-06: старые продуктовые AC ID отсутствовали; новые ID введены здесь впервые. Идентификаторы прежних delivery items сохранены в плане/архиве, не переиспользованы как новые AC.
- D-07: implementation/code baseline и content counts хранятся в плане, команды — в README, workflow — в AGENTS.md. Дубли статусов и старый процесс «сначала merge, затем CI» не являются нормативными.
- D-09 (явный выбор пользователя 19.09.2026): первый самостоятельный PWA-срез — рабочий quiz вне Telegram, вход владельца по e-mail/паролю и подтверждённое связывание с его текущим прогрессом. Для этой Goal сохраняется SQLite; PostgreSQL migration — следующая Goal. Target PostgreSQL/pgvector и AC-FND-05 не отменены. PWA использует React/TypeScript/Vite и общий FastAPI/domain/state; старые Mini App/classic сохраняются как совместимые клиенты. Перенос Mini App на React не является условием запуска первой PWA.
- D-10 (декомпозиция D-09, без расширения scope): первый доступ PWA — владельцу; публичный self-signup для студентов/гостей, OAuth, sharing и новая role policy не включаются. E-mail verification/recovery используют предусмотренный Яндекс 360. PWA login после onboarding не требует Telegram initData или открытого Telegram; Telegram нужен только при добровольном подтверждении связи с существующей legacy identity. Связь подтверждает владение обеими identities; совпадение имени/e-mail или введённый Telegram ID не доказывают ownership. Уже занятая identity/конфликт истории отклоняются без автоматического merge, удаления или переназначения чужого state.
- D-11 (граница PWA-FIRST-001): самостоятельный клиент покрывает текущий random quiz (темы/микс/все, количество/все доступные, необязательная difficulty, ответ/feedback/результат/resume). Доступный уже сейчас quiz state общий с Telegram. Offline обучение, новые learning contours и полная analytics/history UI не входят в первый срез. Потеря связи не оценивается как ошибка ответа; installability не означает обязательное offline хранение content/user data.
- D-12 (identity-v1 и shared quiz, реализация D-09/10): `users.id` — неизменный learning actor, Telegram ID — nullable UNIQUE external identity; web-only users не получают synthetic Telegram ID. Existing progress сохраняется versioned migration по [runbook](miniapp-deployment-qa.md#identity-v1-для-pwa); credentials/linking остаются отдельным auth boundary. Shared quiz service принимает actor после проверки auth adapter. Ответ одному вопросу одной попытки фиксируется один раз: retry, включая conflicting choice и finished attempt, возвращает исходный сохранённый выбор/результат без перезаписи; чужой actor не получает feedback. Новые попытки и будущие вопросы не разрешают отвечать в обход текущего шага.


## Открытые решения / SPEC gaps

| ID | Решение и зависимый scope |
| --- | --- |
| Q-01 | Первый PWA owner-only и proof-of-both-identities/no-auto-merge для e-mail/Telegram определены D-09/10. Student/guest sharing, knowledge access, OAuth и сложные объединения уже существующих accounts остаются открытыми; E01/E11. |
| Q-02 | SQLite attempt snapshot representation принято 19.09; D-09 сохраняет SQLite для первого PWA. Identity-v1 schema/compatibility/reconciliation определены D-12 и runbook; PostgreSQL cutover следующей Goal, repetition version policy остаётся открытой; E01/E04/E13. |
| Q-03 | Алгоритм intervals/adaptive sampling, достаточность истории и mastery/global difficulty policy; E03/E04. |
| Q-04 | Mapping legacy not_started/in_progress/read/revisit/skipped в согласованные «читаю/слушаю/отложено», progress units и дедупликация библиографии; E09. |
| Q-05 | Условия включения optional RAG/direct API/voice; provider/token budget и возврат transcript не определены; E07/E10. |
| Q-06 | PWA-FIRST-001 требует owner e-mail allowlist, конфигурацию Яндекс 360 (sender/SMTP secret owner), session/one-time token expiry/revocation и recovery policy до включения login. Конкретные значения/владельцы пока UNSET; секреты здесь не фиксируются. Это gate auth/mail delivery, не причина откладывать независимый frontend/domain код. |
| Q-07 | Coverage taxonomy/пороги и полный рекурсивный Drive inventory; root ID установлен выше, revision mapping производных материалов ещё не установлен; E02/E12. |
| Q-08 | Фактические production config owners, artifact/version identity и recovery procedure для target stack; E13. SLO, RPO/RTO — UNSET до решения. |

Эти вопросы блокируют только зависящие от них решения; декомпозиция понятных требований в AC не требует повторного утверждения каждой строки.
