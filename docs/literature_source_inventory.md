# Инвентарь источников литературы

## Назначение и границы

Документ связывает учебные списки с файлами статического каталога. Требования находятся в [спецификации](project-spec.md), текущие AC, findings и ограничения поставки — в [плане](delivery-plan.md). Контракт каталога и команды проверки находятся в [content rollout](question_bank_content_rollout.md#каталог-литературы).

Каталог хранит библиографию и учебные рекомендации. Личные отметки, история и прогресс хранятся в runtime database, а не в этих JSON-файлах. Наличие библиографической записи не подтверждает доступность полного текста или право распространять его.

## Карта статического каталога

Срез 06.10.2026: 18 файлов каталога, 319 опубликованных связей с учебными списками и 281 произведение по `work_id`. Каталог совпадает с delivered baseline `3c10221592bdc749f349f8a34db9e7f603f80097`; таблица проверена по локальным JSON и canonical `load_literature_items()`. Это инвентарь файлов, не оценка готовности AC и не доказательство полного текста/точности каждого издания. При изменении каталога сверять его с файлами.

| Дисциплина / topic ID | Файл каталога | Связи со списком |
| --- | --- | --- |
| `developmental_psychology` | [developmental_psychology.json](../content/literature/developmental_psychology.json) | 12 |
| `family_psychology` | [family_psychology.json](../content/literature/family_psychology.json) | 24 |
| `fiziologiya_cheloveka` | [fiziologiya_cheloveka.json](../content/literature/fiziologiya_cheloveka.json) | 17 |
| `fiziologiya_vnd` | [fiziologiya_vnd.json](../content/literature/fiziologiya_vnd.json) | 25 |
| `kachestvennye_metody_issledovaniya` | [kachestvennye_metody_issledovaniya.json](../content/literature/kachestvennye_metody_issledovaniya.json) | 42 |
| `klinicheskaya_psihologiya` | [klinicheskaya_psihologiya.json](../content/literature/klinicheskaya_psihologiya.json) | 19 |
| `obschaya_psihologiya` | [obschaya_psihologiya.json](../content/literature/obschaya_psihologiya.json) | 10 |
| `organizational_psychology` | [organizational_psychology.json](../content/literature/organizational_psychology.json) | 17 |
| `osnovy_eksperimentalnoy_psihologii` | [osnovy_eksperimentalnoy_psihologii.json](../content/literature/osnovy_eksperimentalnoy_psihologii.json) | 9 |
| `personal_brand` | [personal_brand.json](../content/literature/personal_brand.json) | 1 |
| `personality_psychology` | [personality_psychology.json](../content/literature/personality_psychology.json) | 12 |
| `psihofiziologiya` | [psihofiziologiya.json](../content/literature/psihofiziologiya.json) | 8 |
| `psychodiagnostics` | [psychodiagnostics.json](../content/literature/psychodiagnostics.json) | 12 |
| `psycholinguistics` | [psycholinguistics.json](../content/literature/psycholinguistics.json) | 12 |
| `psychological_consulting` | [psychological_consulting.json](../content/literature/psychological_consulting.json) | 20 |
| `quantitative_methods` | [quantitative_methods.json](../content/literature/quantitative_methods.json) | 53 |
| `social_psychology` | [social_psychology.json](../content/literature/social_psychology.json) | 20 |
| `turning_point` | [turning_point.json](../content/literature/turning_point.json) | 6 |

Общее число произведений не равно сумме строк: одно произведение может входить в несколько списков. Стабильные association IDs и подтверждённый `work_id` сохраняют связь с историей чтения; сходство названий само по себе не разрешает объединение.

## Историческое извлечение первых четырёх списков

Следующая таблица сохраняет первоначальное Evidence извлечения Module 1. Упоминание «this PR» относится к исходному этапу наполнения; таблица не является полным современным реестром источников. Проверочные идентификаторы и locators не нужны для навигации по каталогу и здесь не публикуются; исходный приватный provenance сохраняется отдельно.

| Drive source-list title | Topic ID | Current repository status |
|---|---|---|
| `Список литературы. Общая психология` | `obschaya_psihologiya` | Первоначально извлечён и добавлен в каталог; точный locator хранится приватно. |
| `Список литературы. Физиология человека` | `fiziologiya_cheloveka` | Первоначально извлечён по rendered PDF pages; raw text extraction returned empty. Locator хранится приватно. |
| `Список литературы.Физиология высшей нервной деятельности` | `fiziologiya_vnd` | Первоначально извлечён по rendered PDF pages; raw text extraction returned empty. Locator хранится приватно. |
| `Список литературы. Психофизиология` | `psihofiziologiya` | Первоначально извлечён по rendered PDF pages; raw text extraction returned empty. Locator хранится приватно. |

## Lifecycle и личные статусы

Поле `status` статической записи описывает публикационный lifecycle, например `draft`, `review`, `approved`, `deprecated` или `placeholder`. В проверенном локальном срезе все 319 записей имеют `approved`; это не означает подтверждения каждого издания, наличия полного текста или завершения source reconciliation.

Решение D-38 в спецификации задаёт личные статусы «Не начато» (`not_started`), «Читаю» (`in_progress`), «Прочитано» (`read`), «Отложено» (`deferred`). Legacy `revisit` и `skipped`, если такие строки существуют, сопоставляются по согласованной миграции с сохранением истории. Наличие старых пользовательских строк этим инвентарём не проверялось. Результат PostgreSQL migration и поставки устанавливается по Evidence в плане и первичным records.

## Ограничения библиографической и учебной проверки

Пустое извлечение PDF не означает пустой источник: в первоначальном Module 1 использовались rendered pages. Историческое Evidence этой таблицы нельзя переносить на другие файлы без проверки. Полнота recursive Drive inventory и соответствие всех учебных списков относятся к AC-LIT-01 и F-012.

Годы, издания, редакторы, переводчики, форматы и неоднозначные названия сверяются с первичными библиографическими записями. Неизвестные поля остаются неизвестными; candidate duplicates и предупреждения сохраняются до подтверждения (F-114). `approved` не снимает эти ограничения. Текущий loader показывает 268 связей с `metadata_warnings`; это предупреждения о metadata, а не 268 отсутствующих произведений. Coverage сохранённого recursive inventory подтверждён в плане; повторный обход Drive ради пересчёта каталога не нужен.

Статические рекомендации включают роль книги, основания чтения, prerequisites и происхождение значимости. Рекомендации агента отделяются от приоритетов преподавателя; порядок исходного списка не считается доказательством сложности. Роль без проверенного основания не назначается. Продолжение чтения, выбор следующей книги и личные фильтры реализуются сервисами и клиентами; завершение AC-LIT-02/03/06/07 подтверждается отдельно в плане, а не наличием полей в каталоге.
