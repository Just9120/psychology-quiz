# Архив проектной документации

Действующие требования находятся в [спецификации](../project-spec.md), AC/findings/Goal и Evidence — в [плане](../delivery-plan.md), команды и процедуры — в [README](../../README.md). Архив сохраняет прежние отчёты и решения для трассировки; слова current/ready, старые числа и рекомендации отдельных PR относятся только к описанному там состоянию.

## Перенесённые отчёты о контенте

Шесть отчётов перенесены 30.09.2026 из основного каталога docs без удаления содержимого. Проверка tracked consumers через `git grep` и поиска динамических doc readers в app/scripts/tests/workflows не обнаружила их использования кодом; относительные Markdown-ссылки пересчитаны. Это консолидация F-009, не повторная научная проверка содержимого.

| Исторический документ | Основание переноса | Действующая область и незакрытая работа |
| --- | --- | --- |
| [All topics content audit](content_audit_all_topics.md) | Снимок прежних counts, source-ref hygiene и завершённых QA follow-ups | E02/E04, F-026: полная проверка текущего корпуса по первичным источникам и покрытие тем; сохранение stable IDs. Старое repo-local source-ref совпадение не доказывает source support. |
| [Human physiology content audit](content_audit_fiziologiya_cheloveka.md) | Ограниченный question-by-question review старого корпуса | E02/E04, F-026: действующая source-review очередь; старые needs-source-check сохраняются как историческое evidence, а не автоматически новые approvals. |
| [Module 2 content audit](content_audit_module2.md) | Старые предложения последовательных content PR и ограничений клиента | E02/E04, F-026: gap-driven source coverage и quality review. Текущий client scope задаёт spec, прежнее analytics-only не действует. |
| [Glossary content audit](glossary_content_audit.md) | Прежние UX/distractor/provenance гипотезы | E05, F-026: проверить source fidelity и неоднозначные термины/дистракторы на текущих редакциях; полная очередь исходных рекомендаций сохранена в отчёте. |
| [Glossary quality alignment](glossary_global_quality_alignment.md) | Снимок repo-evidence изменений и confusable metadata | E05, F-026: source-backed semantic review. Закрытие legacy publication loopholes F-102/103 не закрывает полноту редакторской проверки. |
| [Glossary coverage](glossary_coverage.md) | Исторические counts и режимы прежних восьми тем | E05, F-026: актуальные counts/режимы подтверждаются loader, tests и текущим планом; исходные цифры не использовать как current baseline. |

Исторические рекомендации сохраняются для reconciliation по current content edition: перенос не закрывает открытые source/semantic/UX findings и не разрешает добавлять вопросы, менять ID или публиковать приватные источники. Полный актуальный реестр сохраняется в delivery-plan, новый реестр здесь не создаётся.

## Прочие материалы

- [Прежний student PWA draft](student-access-draft.md): исключённый student PWA scope; фактические data flows — в [data processing](../data-processing.md).
- [Архив завершённых Goal](../delivery-plan-archive.md): история delivery, primary records и ограничений.
