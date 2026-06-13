# Content Audit — All Active Question Topics

## Scope

Audited the active question-bank source files under `content/questions/module1/`, `content/questions/module2/`, and `content/questions/module3/`:

- `content/questions/module1/fiziologiya_vnd.json`
- `content/questions/module1/obschaya_psihologiya.json`
- `content/questions/module1/psihofiziologiya.json`
- `content/questions/module1/fiziologiya_cheloveka.json`
- `content/questions/module1/vvedenie_v_professiyu.json`
- `content/questions/module2/kachestvennye_metody_issledovaniya.json`
- `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json`
- `content/questions/module3/psychological_consulting.json`

## Executive summary

- Total files audited: 8 active topic files.
- Total approved questions found: 575.
- Validator/seed status: JSON parsing, repository validator, DB initialization, and seed smoke all pass.
- Blockers: none found.
- Original audit JSON files changed: no. Follow-up notes now record subsequent focused content QA passes without changing the original audit scope.
- Recommended next action: Module 3 polish, Module 2 experimental balance, Module 1 answer-position cleanup, Module 2 qualitative light polish, and the focused Module 1/2 repo-local source-ref/readability/legacy-ID pass have been addressed; remaining high-value follow-up is source-backed alignment against original local/Drive source packs if those materials are available.
- Module 1/2 source-backed alignment attempt: see `docs/content_source_alignment_module1_module2.md`. This pass completed Level A metadata/source_ref coverage for all 467 Module 1/2 approved questions but could not perform source-text support sampling because the original local/Drive source packs were not available in the workspace; source alignment remains partial/blocked, not confirmed.

## Topic inventory

| Module | File | Category | Approved count | Draft/other count | Difficulty distribution | Correct answer distribution | Notes |
|---|---|---:|---:|---:|---|---|---|
| Module 1 | `content/questions/module1/fiziologiya_vnd.json` | `Физиология ВНД` | 57 | 0 | easy 9, medium 32, hard 16 | 0: 15, 1: 14, 2: 14, 3: 14 | Valid schema/category; answer-position imbalance was addressed in a follow-up pass; flagged long stems shortened safely; source_ref hygiene passed repo-local review. |
| Module 1 | `content/questions/module1/obschaya_psihologiya.json` | `Общая психология` | 56 | 0 | easy 8, medium 35, hard 13 | 0: 14, 1: 14, 2: 14, 3: 14 | Valid schema/category; answer-position imbalance was addressed in a follow-up pass; flagged long stem shortened safely; source_ref hygiene passed repo-local review. |
| Module 1 | `content/questions/module1/psihofiziologiya.json` | `Психофизиология` | 71 | 0 | easy 14, medium 35, hard 22 | 0: 18, 1: 18, 2: 18, 3: 17 | Valid schema/category; answer-position imbalance was addressed in a follow-up pass; source_ref hygiene passed repo-local review. |
| Module 1 | `content/questions/module1/fiziologiya_cheloveka.json` | `Физиология человека` | 55 | 0 | easy 12, medium 36, hard 7 | 0: 14, 1: 14, 2: 14, 3: 13 | Valid schema/category; answer-position imbalance was addressed in a follow-up pass; source_ref hygiene passed repo-local review. |
| Module 1 | `content/questions/module1/vvedenie_v_professiyu.json` | `Введение в профессию` | 57 | 0 | easy 7, medium 41, hard 9 | 0: 15, 1: 14, 2: 14, 3: 14 | Valid schema/category; answer-position imbalance was addressed in a follow-up pass; source_ref hygiene passed repo-local review; `m1-q3` kept stable as an intentional legacy ID after downstream-reference check. |
| Module 2 | `content/questions/module2/kachestvennye_metody_issledovaniya.json` | `Качественные методы исследования` | 53 | 0 | easy 8, medium 32, hard 13 | 0: 14, 1: 13, 2: 13, 3: 13 | Valid schema/category; answer-position underuse addressed; `m2_qual_023`/`m2_qual_041` reviewed as acceptable scaffolding; source_ref hygiene passed repo-local review. |
| Module 2 | `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json` | `Основы экспериментальной психологии` | 118 | 0 | easy 8, medium 80, hard 30 | 0: 30, 1: 30, 2: 29, 3: 29 | Valid schema/category; follow-up pass addressed answer-position imbalance; source_ref hygiene passed repo-local review; low easy-question share remains optional future review if needed. |
| Module 3 | `content/questions/module3/psychological_consulting.json` | `Психологическое консультирование` | 108 | 0 | easy 32, medium 52, hard 24 | 0: 27, 1: 27, 2: 27, 3: 27 | Valid schema/category; expected 108 approved questions confirmed; practical/case/checklist questions are embedded in the topic category. |

## Blockers

None.

No invalid JSON, validator failures, seed failures, duplicate IDs, missing required fields, invalid correct indexes, empty Module 1/2 source refs, malformed Module 1/2 source-ref families, exact duplicate Module 1/2 question texts, or severe category drift were found in the audited active files.

## Completed content QA follow-ups and remaining issues

| File path | Question ID | Issue type | Short reason | Suggested next action |
|---|---|---|---|---|
| `content/questions/module1/fiziologiya_vnd.json` | topic-level | Answer-position imbalance addressed | Follow-up pass redistributed correct answers from 0:24, 1:32, 2:1, 3:0 to 0:15, 1:14, 2:14, 3:14. | No further answer-position cleanup needed for this topic; long-stem/source-ref review remains separate if needed. |
| `content/questions/module1/obschaya_psihologiya.json` | topic-level | Answer-position imbalance addressed | Follow-up pass redistributed correct answers from 0:18, 1:35, 2:3, 3:0 to 0:14, 1:14, 2:14, 3:14. | No further answer-position cleanup needed for this topic; long-stem/source-ref review remains separate if needed. |
| `content/questions/module1/psihofiziologiya.json` | topic-level | Answer-position imbalance addressed | Follow-up pass redistributed correct answers from 0:12, 1:56, 2:3, 3:0 to 0:18, 1:18, 2:18, 3:17. | No further answer-position cleanup needed for this topic; source-ref review remains separate if needed. |
| `content/questions/module1/fiziologiya_cheloveka.json` | topic-level | Answer-position imbalance addressed | Follow-up pass redistributed correct answers from 0:18, 1:37, 2:0, 3:0 to 0:14, 1:14, 2:14, 3:13. | No further answer-position cleanup needed for this topic; source-ref review remains separate if needed. |
| `content/questions/module1/vvedenie_v_professiyu.json` | topic-level | Answer-position imbalance addressed | Follow-up pass redistributed correct answers from 0:5, 1:48, 2:4, 3:0 to 0:15, 1:14, 2:14, 3:14. | No further answer-position cleanup needed for this topic; legacy ID/source-ref review remains separate if needed. |
| `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json` | topic-level | Answer-position imbalance addressed | Follow-up pass redistributed correct answers from 0:26, 1:77, 2:15, 3:0 to 0:30, 1:30, 2:29, 3:29. | No further answer-position cleanup needed for this topic; source-alignment review remains separate if needed. |
| `content/questions/module1/fiziologiya_vnd.json` | `m1_vnd_021`, `m1_vnd_045`, `m1_vnd_046` | Telegram quiz readability addressed | Case stems were shortened for compact Telegram quiz UX while preserving IDs, options, correct-answer text, difficulty, status, explanations, and source refs. | No further action for these flagged stems unless later UX testing finds another issue. |
| `content/questions/module1/obschaya_psihologiya.json` | `m1_gp_030` | Telegram quiz readability addressed | Long multi-clause stem was compressed while preserving the processes/states/properties distinction, options, correct-answer text, difficulty, status, explanation, and source ref. | No further action for this flagged stem unless later UX testing finds another issue. |
| `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json` | `m2_exp_116` | Telegram quiz readability addressed | Long case stem was shortened in a follow-up pass while preserving concept, answer, and source ref. | No further action needed for this flagged stem unless later UX testing finds another issue. |
| `content/questions/module2/kachestvennye_metody_issledovaniya.json` | `m2_qual_023`, `m2_qual_041` | Near-duplicate learning target reviewed | `m2_qual_023` tests code/theme distinction; `m2_qual_041` was lightly varied to make the added category layer explicit. | Keep both as intentional scaffolding; full source-alignment review remains separate if needed. |
| `content/questions/module1/*`, `content/questions/module2/*` | topic-level | Repo-local source-ref hygiene reviewed | All 467 Module 1/2 approved questions have non-empty source refs under the expected `module1/*` or `module2/*` families; no Module 3/unrelated-topic refs or obvious text/source_ref mismatches were found from repository-local evidence. | Full source-backed alignment still requires the original local/Drive source packs and was not claimed in this pass. |

## Module 1/2 source-ref hygiene review — 2026-06-13

Repo-local review covered the seven active Module 1/2 files listed above. All 467 Module 1/2 approved questions have non-empty `source_ref` values; no `source_ref` pointed to Module 3 or an unrelated module, and no obviously malformed values or visible category/source_ref mismatches were found from question text and repository-local metadata. No source_ref values were changed.

| File | Approved count | Non-empty source_ref count | Source_ref family / prefix posture | Concentration notes |
|---|---:|---:|---|---|
| `content/questions/module1/fiziologiya_vnd.json` | 57 | 57 | all `module1/vnd/*` | largest groups: `lecture2_properties_of_nervous_processes` 10, `lecture1_higher_nervous_activity` 9, `lecture4_learning_and_memory` 8; no suspicious family drift found. |
| `content/questions/module1/obschaya_psihologiya.json` | 56 | 56 | all `module1/general/*` | `lecture2` 16, `lecture3` 13, `lecture1` 11; practice/glossary refs remain smaller and consistent with topic naming. |
| `content/questions/module1/psihofiziologiya.json` | 71 | 71 | all `module1/psychophysiology/*` | `module1_integration` is intentionally prominent at 20; lecture refs otherwise range from 2 to 7. |
| `content/questions/module1/fiziologiya_cheloveka.json` | 55 | 55 | all `module1/human_physiology/*` | nervous-system refs are largest at 21; cardiovascular 8 and endocrine 7; blood/digestive/immune refs are smaller but not malformed. |
| `content/questions/module1/vvedenie_v_professiyu.json` | 57 | 57 | all `module1/intro/*` | topic/practice refs are distributed across topic1–topic7 and practice1–practice4; `m1-q3` is an ID-pattern anomaly only, not a source_ref anomaly. |
| `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json` | 118 | 118 | all `module2/experimental/*` | largest groups: `experimental_research_designs` 31, `lecture1_predmet_i_metod` 26, `practice8_validity_and_alternative_hypotheses` 23, `practice9_applied_experimental_method` 22. |
| `content/questions/module2/kachestvennye_metody_issledovaniya.json` | 53 | 53 | all `module2/qualitative/*` | concentrated in `practice10` 15, `practice11` 16, `practice12` 13, plus `lecture1_intro` 9; this is consistent with the active limited-scope topic. |

Full source-backed alignment was not confirmed in this pass because original source packs were not present in the repository. A future source-backed alignment pass should use the local/Drive source materials before adding, removing, or remapping source-backed content.

A follow-up source-backed alignment attempt is documented in `docs/content_source_alignment_module1_module2.md`. It confirmed the same all-467 non-empty source_ref metadata posture but found the original local/Drive source packs unavailable in the execution environment, so no question-level source-text support was claimed and no JSON was changed.

## Medium-priority improvements

- `content/questions/module1/vvedenie_v_professiyu.json` / `m1-q3`: ID is valid and unique but breaks the otherwise stable `m1_intro_###` naming pattern. Repository search found the content item plus documentation references and no runtime/seed/test references. Keep it stable as an intentional legacy ID because stable IDs may matter downstream; if future normalization is explicitly desired, proposed target is `m1_intro_003` after repeating downstream reference checks and migration-impact review.
- `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json`: easy questions are a small share of a 118-question topic. Consider a targeted difficulty review before new experimental-psychology batches.
- `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json` / `m2_exp_009` and `m2_exp_010`: reviewed in follow-up; the nomothetic/ideographic pair remains educationally useful as a direct conceptual contrast.
- `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json` / `m2_exp_013` and `m2_exp_014`: reviewed in follow-up; the Milgram strength/limitation pair remains intentionally contrastive and source-aligned at the learning-target level.
- `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json` / `m2_exp_022` and `m2_exp_023`: follow-up pass reclassified the core internal/external validity definition contrast from `hard` to `medium`; the paired contrast remains educationally useful.
- `content/questions/module3/psychological_consulting.json` / `m3_psychological_consulting_063`: uppercase `НЕ` phrasing was addressed in the Module 3 polish pass; no remaining action for that specific stem.
- Module 1 and Module 2 explanations are generally present and educational, but some distractors are obviously implausible. A later polish PR can improve distractor plausibility without changing correct answers.

## Module 1 notes

### `content/questions/module1/fiziologiya_vnd.json`

- Coverage strengths: foundational ВНД concepts, Павловская tradition, conditioning, inhibition/excitation balance, learning/memory, needs, emotions, will/decision-making, and practice-oriented cases.
- Likely gaps or underrepresented areas: source-backed review should confirm whether later lecture/practice materials are proportionally represented; no new topic should be added in this audit PR.
- Balance: difficulty distribution is reasonable overall; answer-position imbalance was addressed to 0:15, 1:14, 2:14, 3:14 in a follow-up pass.
- Usability: flagged practical scenario stems `m1_vnd_021`, `m1_vnd_045`, and `m1_vnd_046` were shortened safely for compact Telegram quiz flow.

### `content/questions/module1/obschaya_psihologiya.json`

- Coverage strengths: object/subject of psychology, psychics/mental phenomena, methods, observation/interview/testing, processes/states/properties, and practical examples.
- Likely gaps or underrepresented areas: source-backed review should verify whether practice materials after `practice4` need any future balancing.
- Balance: difficulty distribution is acceptable; answer-position imbalance was addressed to 0:14, 1:14, 2:14, 3:14 in a follow-up pass.
- Usability: flagged long-stem candidate `m1_gp_030` was shortened safely for compact Telegram quiz flow.

### `content/questions/module1/psihofiziologiya.json`

- Coverage strengths: brain/anatomy, neurotransmitters, inhibition, motivation, wakefulness, attention, perception, behavioral organization, and integrated module review items.
- Likely gaps or underrepresented areas: `module1/psychophysiology/module1_integration` is heavily represented; check whether this is intended as review coverage.
- Balance: high count is acceptable for a stable baseline topic; answer-position imbalance was addressed to 0:18, 1:18, 2:18, 3:17 in a follow-up pass.
- Usability: no overlong stems were flagged by length threshold.

### `content/questions/module1/fiziologiya_cheloveka.json`

- Coverage strengths: nervous, endocrine, cardiovascular, respiratory, immune, digestive, blood-system, stress/emotion, and consulting-adjacent physiology materials.
- Likely gaps or underrepresented areas: cardiovascular and nervous-system content are better represented than blood/immune/digestive topics; source review should decide whether this reflects source weight.
- Balance: difficulty skews medium with few hard questions; answer-position imbalance was addressed to 0:14, 1:14, 2:14, 3:13 in a follow-up pass.
- Usability: stems are compact and generally quiz-friendly.

### `content/questions/module1/vvedenie_v_professiyu.json`

- Coverage strengths: profession introduction, ethics, interview/observation, professional identity, practice topics, and role boundaries.
- Likely gaps or underrepresented areas: source review should confirm whether practice topics are proportionate to lecture topics.
- Balance: difficulty skews medium; answer-position imbalance was addressed to 0:15, 1:14, 2:14, 3:14 in a follow-up pass.
- Usability: stems are compact; `m1-q3` was kept stable as an intentional legacy ID after repository-wide downstream-reference search.

## Module 2 notes

### `content/questions/module2/kachestvennye_metody_issledovaniya.json`

- Coverage strengths: qualitative research logic, coding, themes, interviews, observation, triangulation, reflexivity, and practice materials 10–12.
- Likely gaps or underrepresented areas: source refs are concentrated in three practice sessions plus one intro lecture; verify against local source materials before adding or removing content.
- Balance: difficulty distribution is healthy; follow-up pass addressed correct answer position 3 underuse by moving from 0:23, 1:15, 2:12, 3:3 to 0:14, 1:13, 2:13, 3:13.
- Deduplication: `m2_qual_023` and `m2_qual_041` were reviewed as acceptable scaffolding: the first keeps the code/theme distinction, while the second now explicitly foregrounds the transition from codes to categories and themes.

### `content/questions/module2/osnovy_eksperimentalnoy_psihologii.json`

- Coverage strengths: experimental method, validity, research designs, classic experiments, applied method, hypotheses, and threats to inference.
- Likely gaps or underrepresented areas: as a large 118-question topic, it would benefit from a source-alignment pass to confirm whether easy onboarding questions are sufficient.
- Balance: medium and hard questions dominate; only 8 easy questions. A follow-up pass balanced correct answer positions to 0:30, 1:30, 2:29, 3:29 while preserving IDs, source refs, explanations, and correct-answer texts.
- Usability: `m2_exp_116` was shortened for mobile readability. Mirrored conceptual pairs were reviewed as useful contrast items; the validity pair was lightly varied and reclassified to `medium`.

## Module 3 notes

- Total count check: `content/questions/module3/psychological_consulting.json` contains 108 approved questions, matching the expected current state.
- Lecture/practice batch structure: 84 questions point to lecture/glossary source refs and 24 questions point to practical/case/checklist/technique-card source refs.
- Category consistency: all 108 questions use `Психологическое консультирование`.
- Practical questions embedded correctly: practice 17–20, checklist, conceptualization blank, and technique-card questions remain in the existing `Психологическое консультирование` category; no separate practical category is present.
- Difficulty balance: easy 32, medium 52, hard 24 gives a healthy progression for a newly opened Module 3 topic.
- Correct answer distribution: perfectly balanced at 27 questions per answer position.
- Dedup/source-alignment candidates: no exact duplicate question text, option sets, or repeated explanations were found. The lecture/practice split should still receive a source-backed review for overlap between conceptual lecture questions and practical application questions before broader Module 3 expansion.
- Readability: stems are generally compact. Follow-up polish reworded `m3_psychological_consulting_063` from an uppercase negation stem to a positive out-of-scope formulation while preserving the same concept and answer.

## Recommended follow-up PRs

1. Module 3 dedup/readability/source-alignment polish: addressed in a focused follow-up pass for lecture/practice overlap, the single uppercase `НЕ` item, and family-level source mapping without changing category structure.
2. Module 2 experimental psychology balance pass: addressed for answer-position imbalance, definition-like validity item difficulty, and the flagged long stem; source-alignment review remains separate if needed.
3. Module 1 answer-distribution cleanup: addressed by mechanically reshuffling options across stable baseline topics while preserving correct answers, explanations, IDs, difficulties, and source refs.
4. Module 2 qualitative methods light polish: addressed answer position 3 underuse and reviewed `m2_qual_023`/`m2_qual_041` as intentional scaffolding; full source-alignment review remains separate if needed.
5. Module 1/2 source-ref/readability/ID-hygiene pass: addressed repo-local source_ref hygiene, shortened the flagged Module 1 long stems, and kept `m1-q3` stable as an intentional legacy ID; full source-backed alignment remains a future pass if original source packs are available.

## Validation

Commands run successfully:

- `python -m json.tool content/questions/module1/fiziologiya_vnd.json`
- `python -m json.tool content/questions/module1/obschaya_psihologiya.json`
- `python -m json.tool content/questions/module1/psihofiziologiya.json`
- `python -m json.tool content/questions/module1/fiziologiya_cheloveka.json`
- `python -m json.tool content/questions/module1/vvedenie_v_professiyu.json`
- `python -m json.tool content/questions/module2/kachestvennye_metody_issledovaniya.json`
- `python -m json.tool content/questions/module2/osnovy_eksperimentalnoy_psihologii.json`
- `python -m json.tool content/questions/module3/psychological_consulting.json`
- `python scripts/validate_questions.py`
- `DB_PATH=/tmp/quiz-ci.sqlite3 python scripts/init_db.py`
- `DB_PATH=/tmp/quiz-ci.sqlite3 python scripts/seed_questions.py`
- `git diff --check`

Additional local analysis was run with a temporary inline Python script and not committed. It computed counts by file/category/status, difficulty distributions, correct answer index distributions, duplicate IDs, exact duplicate text, repeated option sets, repeated explanations, overlong stems, uppercase `НЕ` usage, and near-duplicate candidates.
