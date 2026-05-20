# Content audit: Module 2 question bank

## Purpose
Этот документ фиксирует аудит покрытия, баланса и направлений следующего контролируемого роста банка вопросов Module 2.

- Это audit/planning-артефакт.
- Документ не заменяет `docs/project-spec.md`.
- Документ не заменяет `docs/delivery-plan.md`.
- Документ не меняет source-of-truth модель банка вопросов.
- JSON-файлы в репозитории остаются source of truth для контента.
- SQLite остаётся только runtime layer, а не контентным источником.

## Current Module 2 state

| Category | File | Current ID range | Recent PRs | Notes |
|---|---|---|---|---|
| `Основы экспериментальной психологии` | `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json` | `m2_exp_001`–`m2_exp_107` | #91, #92, #101, #104, #108 | Последний QA-улучшенный batch: `m2_exp_096`–`m2_exp_107`. |
| `Качественные методы исследования` | `content/questions/module2/kachestvennye_metody_issledovaniya.json` | `m2_qual_001`–`m2_qual_043` | #93, #100, #104, #106, #107 | Batch 3 `m2_qual_031`–`m2_qual_043` добавлен и затем QA-улучшен. |

## Coverage snapshot — experimental psychology

Текущее покрытие заметно закрывает базовые и промежуточные темы:
- operationalization;
- variables: independent variable, dependent variable, control variables, confounds;
- random assignment vs random sampling;
- validity: internal, external, ecological, а также construct/measurement validity там, где это уже присутствует;
- reliability vs validity;
- manipulation check;
- placebo / expectation effects;
- demand characteristics;
- blind / double-blind procedures;
- interpretation of classic experimental logic;
- experimental and quasi-experimental designs;
- pretest/posttest and attrition;
- applied experimental method cases (точечно, но пока не как доминирующий формат).

Likely gaps / next-growth candidates:
- Больше applied scenario-задач, где студент определяет:
  - IV/DV/confound из сценария;
  - тип дизайна из сценария;
  - угрозу валидности из сценария;
  - лучшую стратегию контроля из сценария.
- Дополнительное покрытие тем:
  - counterbalancing / order effects *(candidate, requires source check)*;
  - factorial designs *(candidate, requires source check)*;
  - interaction effects *(candidate, requires source check)*;
  - within-subject vs between-subject designs *(candidate, requires source check)*;
  - ethics of experiments *(candidate, requires source check)*;
  - preregistration / hypothesis clarity, если подтверждается текущими репозиторными источниками *(candidate, requires source check)*;
  - осторожная интерпретация non-significant findings *(candidate, requires source check)*;
  - measurement artifacts, ceiling/floor effects *(candidate, requires source check)*.

## Coverage snapshot — qualitative methods

Текущее покрытие уже включает ключевые основы:
- qualitative vs quantitative logic;
- research question formulation;
- interview guide quality;
- neutral vs leading questions;
- probing;
- rapport and interviewer role;
- reflexivity;
- observation and field notes;
- participant vs non-participant observation;
- focus group moderation;
- transcription and anonymization;
- purposive sampling;
- saturation;
- coding, codebook, categories, themes;
- triangulation;
- audit trail;
- member checking;
- transferability / thick description;
- deviant cases;
- confidentiality and ethics.

Likely gaps / next-growth candidates:
- Больше applied/case-based вопросов про:
  - переписывание слабых interview-вопросов;
  - выбор sampling strategy под сценарий;
  - различение типов field notes на примерах;
  - выбор корректных probe types;
  - обнаружение leading questions;
  - решение, что именно анонимизировать в цитате;
  - распознавание overgeneralization по цитате;
  - выбор между interview / focus group / observation / document analysis.
- Возможные under-covered темы:
  - document analysis *(candidate, requires source check)*;
  - thematic analysis workflow *(candidate, requires source check)*;
  - researcher positionality *(candidate, requires source check)*;
  - consent in qualitative research *(candidate, requires source check)*;
  - handling sensitive quotes *(candidate, requires source check)*;
  - data management and audit trail examples *(candidate, requires source check)*;
  - limits of saturation *(candidate, requires source check)*;
  - reflexive thematic analysis vs mechanical coding, если поддержано исходными материалами *(candidate, requires source check)*.

## Cross-category observations

- По raw count Module 2 сейчас существенно сильнее покрыт в experimental-направлении, чем в qualitative.
- Для qualitative-направления всё ещё вероятно нужен приоритет на applied/case-based growth.
- Для experimental-направления полезнее смещаться от общих дефиниций к scenario-based interpretation.
- Широкие generic-definition additions стоит добавлять только при явном, подтверждённом пробеле.
- Приоритет — вопросы на applied methodological reasoning.

## Risks

- Риск near-duplicates при росте без явного gap targeting.
- Риск переиспользования одних и тех же семейств `source_ref`.
- Риск добавления вопросов без опоры на первичные источники.
- Риск слишком очевидных distractors (снижение диагностической ценности).
- Риск преждевременного открытия новых категорий Module 2 до зрелости текущих двух категорий.

## Recommended next PRs

1. `Add Module 2 qualitative applied case questions`
   - Focus: interview guide, probing, anonymization, field notes, focus groups, coding decisions.
   - Size: 10–12 questions.
   - No new category.

2. `Add Module 2 experimental design interpretation questions`
   - Focus: scenario-based IV/DV/confound/design/validity interpretation.
   - Size: 10–12 questions.
   - No new category.

3. `QA Module 2 duplicate and source_ref balance`
   - Focus: scan repeated saturation/member checking/validity questions and `source_ref` distribution.
   - Docs or content QA depending on findings.

## Decision

- Новые категории Module 2 пока не открывать.
- Продолжать controlled growth и QA внутри уже активных категорий.
- Mini App / Web App оставлять в analytics/design only.
- Следующий контентный рост должен быть gap-driven, а не generic.
