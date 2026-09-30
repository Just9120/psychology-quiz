# Архив проектной документации

Действующие требования находятся в [спецификации](../project-spec.md), AC/findings/Goal и Evidence — в [плане](../delivery-plan.md), команды и процедуры — в [README](../../README.md). Архив сохраняет прежние отчёты и решения для трассировки; слова current/ready, старые числа и рекомендации отдельных PR относятся только к описанному там состоянию.

## Перенесённые отчёты о контенте

Шесть отчётов перенесены 30.09.2026 из основного каталога docs без удаления содержимого. Проверка tracked consumers через `git grep` и поиска динамических doc readers в app/scripts/tests/workflows не обнаружила их использования кодом; относительные Markdown-ссылки пересчитаны. Это консолидация F-009, не повторная научная проверка содержимого.

| Исторический документ | Основание переноса | Действующая область и незакрытая работа |
| --- | --- | --- |
| [All topics content audit](content_audit_all_topics.md) | Снимок прежних counts, source-ref hygiene и завершённых QA follow-ups | E02/E04, F-026: полная проверка текущего корпуса по первичным источникам и покрытие тем; сохранение stable IDs. Старое repo-local source-ref совпадение не доказывает source support. |
| [Human physiology content audit](content_audit_fiziologiya_cheloveka.md) | Ограниченный question-by-question review старого корпуса | E02/E04, F-026: действующая source-review очередь; старые needs-source-check сохраняются как историческое evidence, а не автоматически новые approvals. |
| [Module 2 content audit](content_audit_module2.md) | Старые предложения последовательных content PR и ограничений клиента | E02/E04, F-026: gap-driven source coverage и quality review. Текущий client scope задаёт spec, прежнее analytics-only не действует. |
| [Module 2 source-alignment report](content_source_alignment_module2_qualitative.md) | Прежняя сверка 53 редакций по предоставленным фрагментам; без прямого просмотра источников | E02/E04, F-026: сверять source fidelity текущих редакций по сохранённым ID. Все limitations и прежние risk/needs-review записи сохранены. Старые supported labels не утверждают текущий контент и не возвращают retired вопросы в публикацию. |
| [Glossary content audit](glossary_content_audit.md) | Прежние UX/distractor/provenance гипотезы | E05, F-026: проверить source fidelity и неоднозначные термины/дистракторы на текущих редакциях; полная очередь исходных рекомендаций сохранена в отчёте. |
| [Glossary quality alignment](glossary_global_quality_alignment.md) | Снимок repo-evidence изменений и confusable metadata | E05, F-026: source-backed semantic review. Закрытие legacy publication loopholes F-102/103 не закрывает полноту редакторской проверки. |
| [Glossary coverage](glossary_coverage.md) | Исторические counts и режимы прежних восьми тем | E05, F-026: актуальные counts/режимы подтверждаются loader, tests и текущим планом; исходные цифры не использовать как current baseline. |

Исторические рекомендации сохраняются для reconciliation по current content edition: перенос не закрывает открытые source/semantic/UX findings и не разрешает добавлять вопросы, менять ID или публиковать приватные источники. Полный актуальный реестр сохраняется в delivery-plan, новый реестр здесь не создаётся.

## Прочие материалы

- [Прежний student PWA draft](student-access-draft.md): исключённый student PWA scope; фактические data flows — в [data processing](../data-processing.md).
- [Архив завершённых Goal](../delivery-plan-archive.md): история delivery, primary records и ограничений.

## Исторические предложения учебных разделов

Два RFC перенесены 30.09.2026 с полным сохранением текста и исправлением relative navigation. Их исходная модель static-only/future progress уже не описывает runtime: каталог и личные отметки реализованы в [literature service](../../app/literature_service.py), термины — в действующем клиенте. Приоритеты и обязательства определяют текущие spec/plan.

| Документ | Сохранённые границы и незакрытые обязательства |
| --- | --- |
| [Literature runtime RFC](literature_runtime_rfc.md) | E09: личный план чтения и обоснованный следующий шаг AC-LIT-06 остаются в текущей Goal; legacy state mapping Q-04 и интеграции AC-LIT-08/09 не объявлены завершёнными. Старые /next, reminders, deadline и daily-time proposals сами по себе не расширяют требования. |
| [Glossary and literature contours RFC](glossary_literature_contours_rfc.md) | E05/E09: сохраняются историческая структура и rationale разделов; source-backed coverage и чтение проверяются по текущим AC, а не по прежнему статусу proposal. Исторический proposal реестра тем сохранён в архиве; действующие contracts определяются текущими registry/validator и spec/plan. |

## Исторические отчёт и план Mini App

Два файла перенесены 30.09.2026 без изменения содержимого. Exact-name/path consumer search в tracked файлах и проверка doc readers не выявили использования кодом/tests/workflows; прежние упоминания в карте документов плана обновлены. Перенос не закрывает findings и не подтверждает отсутствие дефектов текущего клиента.

| Документ | Основание и действующие обязательства |
| --- | --- |
| [Runner audit после PR 146](2026-05-24-miniapp-runner-audit.md) | Снимок прежнего HTML client и API. AUDIT-001/002/003 (hydration/restart/error recovery) и AUDIT-005 (browser coverage) сопоставлять с текущим React-клиентом в F-013; AUDIT-004 (cache) и AUDIT-007 (origin configuration) — с действующей delivery procedure/F-116; AUDIT-006 (docs drift) — F-009; AUDIT-008 (parallel setup) — AC-FND-07/F-025. Все восемь исходных записей сохранены, неподтверждённые legacy гипотезы не объявлены текущими дефектами или устранёнными. |
| [Mini App / Bot Refactor RFC](refactor-plan-miniapp-bot.md) | Исторический план шести PR и ограничение no-build/без React/PostgreSQL заменены текущими AGENTS/spec. Полезные цели разделения transport/domain, удаления dynamic coupling и сохранения contracts остаются в F-024. Legacy HTML сохраняется по F-116 до проверки внешних потребителей; перенос RFC не разрешает удаление или новый scope. |

## Исторический proposal реестра тем

| Документ | Основание и действующие обязательства |
| --- | --- |
| [Topic registry / phase 1 proposal](topic_registry_schema_phase1.md) | Прежний design-only snapshot восьми тем / 575 вопросов предшествует действующим [topics](../../content/topics.json), [validator](../../scripts/validate_topics.py) и runtime consumers. Exact-name/path consumer search в tracked app/scripts/tests/workflows не выявил использования proposal; код использует registry, CI — validator. Полный текст сохранён с исправлением трёх relative links. Старые будущие решения и запреты runtime не задают текущий scope; E01/E02/E05/E09, стабильные IDs и compatibility проверяются по spec/plan. Перенос не подтверждает выполнение этих AC. |
