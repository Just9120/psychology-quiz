# Инвентарь источников литературы

## Назначение и границы

Документ связывает учебные списки с файлами статического каталога. Требования находятся в [спецификации](project-spec.md), текущие AC, findings и ограничения поставки — в [плане](delivery-plan.md). Контракт каталога и команды проверки находятся в [content rollout](question_bank_content_rollout.md#каталог-литературы).

Каталог хранит библиографию и учебные рекомендации. Личные отметки, история и прогресс хранятся в runtime database, а не в этих JSON-файлах. Наличие библиографической записи не подтверждает доступность полного текста или право распространять его.

## Карта статического каталога

Срез локальной ветки `codex/complete-scope-pr2` на 30.09.2026: 12 файлов, 143 связи с учебными списками и 126 произведений по `work_id`. Это инвентарь файлов, не оценка готовности AC и не доказательство текущей версии VPS. Числа получены чтением `content/literature/*.json`; при изменении каталога сверять их с файлами.

| Дисциплина / topic ID | Файл каталога | Связи со списком |
| --- | --- | --- |
| `developmental_psychology` | [developmental_psychology.json](../content/literature/developmental_psychology.json) | 12 |
| `family_psychology` | [family_psychology.json](../content/literature/family_psychology.json) | 24 |
| `fiziologiya_cheloveka` | [fiziologiya_cheloveka.json](../content/literature/fiziologiya_cheloveka.json) | 15 |
| `fiziologiya_vnd` | [fiziologiya_vnd.json](../content/literature/fiziologiya_vnd.json) | 15 |
| `kachestvennye_metody_issledovaniya` | [kachestvennye_metody_issledovaniya.json](../content/literature/kachestvennye_metody_issledovaniya.json) | 17 |
| `obschaya_psihologiya` | [obschaya_psihologiya.json](../content/literature/obschaya_psihologiya.json) | 6 |
| `organizational_psychology` | [organizational_psychology.json](../content/literature/organizational_psychology.json) | 13 |
| `personality_psychology` | [personality_psychology.json](../content/literature/personality_psychology.json) | 8 |
| `psihofiziologiya` | [psihofiziologiya.json](../content/literature/psihofiziologiya.json) | 6 |
| `psycholinguistics` | [psycholinguistics.json](../content/literature/psycholinguistics.json) | 8 |
| `psychological_consulting` | [psychological_consulting.json](../content/literature/psychological_consulting.json) | 11 |
| `social_psychology` | [social_psychology.json](../content/literature/social_psychology.json) | 8 |

Общее число произведений не равно сумме строк: одно произведение может входить в несколько списков. Стабильные association IDs и подтверждённый `work_id` сохраняют связь с историей чтения; сходство названий само по себе не разрешает объединение.

## Историческое извлечение первых четырёх списков

Следующая таблица сохраняет первоначальное Evidence извлечения Module 1. Упоминание «this PR» относится к исходному этапу наполнения; таблица не является полным современным реестром источников. Идентификаторы ниже уже присутствовали в этом документе; новые приватные locators сюда не добавляются.

| Drive source-list title | Topic ID | Current repository status |
|---|---|---|
| `Список литературы. Общая психология` | `obschaya_psihologiya` | Extracted and seeded in this PR from Drive source `1Qu7CXXravaMnHmmsgSDTeEfgAK36uzZZ`. |
| `Список литературы. Физиология человека` | `fiziologiya_cheloveka` | Seeded from rendered PDF source `1PwOHb_wdshbIgg9-cmO1d4E7iJzere5S`; raw text extraction returned empty. |
| `Список литературы.Физиология высшей нервной деятельности` | `fiziologiya_vnd` | Seeded from rendered PDF source `1H9qgOSUyfvrVRo1Q7hkVG7BgnjHjYuaX`; raw text extraction returned empty. |
| `Список литературы. Психофизиология` | `psihofiziologiya` | Seeded from rendered PDF source `1w7N6-xBrVvPdIx9TxBoEaCZNa4qz8_Ni`; raw text extraction returned empty. |

## Lifecycle и личные статусы

Поле `status` статической записи описывает публикационный lifecycle, например `draft`, `review`, `approved`, `deprecated` или `placeholder`. В проверенном локальном срезе все 143 записи имеют `approved`; это не означает подтверждения каждого издания, наличия полного текста или завершения source reconciliation.

Решение D-38 в спецификации задаёт личные статусы «Не начато» (`not_started`), «Читаю» (`in_progress`), «Прочитано» (`read`), «Отложено» (`deferred`). Legacy `revisit` и `skipped`, если такие строки существуют, сопоставляются по согласованной миграции с сохранением истории. Наличие старых пользовательских строк этим инвентарём не проверялось. Результат PostgreSQL migration и поставки устанавливается по Evidence в плане и первичным records.

## Ограничения библиографической и учебной проверки

Пустое извлечение PDF не означает пустой источник: в первоначальном Module 1 использовались rendered pages. Историческое Evidence этой таблицы нельзя переносить на другие файлы без проверки. Полнота recursive Drive inventory и соответствие всех учебных списков относятся к AC-LIT-01 и F-012.

Годы, издания, редакторы, переводчики, форматы и неоднозначные названия сверяются с первичными библиографическими записями. Неизвестные поля остаются неизвестными; candidate duplicates и предупреждения сохраняются до подтверждения (F-114). `approved` не снимает эти ограничения.

Статические рекомендации включают роль книги, основания чтения, prerequisites и происхождение значимости. Рекомендации агента отделяются от приоритетов преподавателя; порядок исходного списка не считается доказательством сложности. Роль без проверенного основания не назначается. Продолжение чтения, выбор следующей книги и личные фильтры реализуются сервисами и клиентами; завершение AC-LIT-02/03/06/07 подтверждается отдельно в плане, а не наличием полей в каталоге.
