# GLOSSARY-CONTENT-AUDIT-001 — аудит качества глоссария

## Scope and evidence posture

This is a documentation-only audit of the active glossary content used by both the classic Telegram glossary quiz and the Mini App glossary flow.

Verified repository facts:

- Active glossary topics are defined by `GLOSSARY_TOPICS` in `app/glossary.py`.
- `load_glossary_entries(topic_id)` only accepts topic IDs present in `GLOSSARY_TOPICS` and loads JSON from `content/glossary/{topic_id}.json`.
- The Mini App glossary flow reuses `GLOSSARY_TOPICS`, `load_glossary_entries()`, and `build_glossary_quiz_question()` from `app/glossary.py`.
- The classic Telegram glossary quiz also reuses `load_glossary_entries()` and `build_glossary_quiz_question()`.
- The active glossary source files found in this audit are:
  - `content/glossary/kachestvennye_metody_issledovaniya.json`
  - `content/glossary/osnovy_eksperimentalnoy_psihologii.json`

Important limitations:

- This audit did not verify terms against external textbooks, lecture notes, or original course/source packs.
- `source_refs` values are treated as repository-local provenance markers only. They are not proof of full source-backed certification.
- Findings marked `review-needed` are conservative review hypotheses and require human/source review before content edits.
- No glossary entries, question-bank JSON, runtime code, Mini App UI, API contracts, DB, deploy/CD, or tests were changed in this PR.

## 1. Executive summary

- Total active topics: **2**.
- Total active glossary entries: **24**.
- Blockers: **none for current 5-question, 10-question, or all-count availability**, because both active topics have at least 10 entries and at least 4 entries are enough for the current 1-correct + 3-distractor quiz shape.
- Highest-risk topic: **`kachestvennye_metody_issledovaniya`**, because it contains more conceptually overlapping entries, broader definitions, and more distractor-quality risks than `osnovy_eksperimentalnoy_psihologii`.
- Main cross-cutting risk: the quiz uses `short_definition` as answer options. Several short definitions are semantically close enough that a learner could plausibly hesitate between multiple options without source-backed wording review.
- “Все доступные” is meaningful and currently stable for both topics because it maps to the loaded entry count for the selected topic. It remains sensitive to future entry-count changes because selecting all entries means every low-quality or overlapping entry appears in a session.

### Topic readiness summary

| Topic ID | Supports 5 questions | Supports 10 questions | Supports “Все доступные” | Notes |
|---|---:|---:|---:|---|
| `kachestvennye_metody_issledovaniya` | Yes | Yes | Yes, 14 entries | Functionally ready; content-quality review recommended before expanding or treating as source-certified. |
| `osnovy_eksperimentalnoy_psihologii` | Yes | Yes | Yes, 10 entries | Functionally ready; “all” equals the 10-question mode today, so it is meaningful but not materially distinct from 10. |

### Recommended priority order for future fixes

1. **GLOSSARY-CONTENT-POLISH-001** — conservative documentation/content polish for typo, terminology consistency, and clarity issues in `kachestvennye_metody_issledovaniya`, with no runtime changes.
2. **GLOSSARY-SOURCE-ALIGNMENT-001** — source/human review for glossary terms whose wording is broad, ambiguous, or based only on repository-local `supplied_snippet:*` / `question:*` markers.
3. **GLOSSARY-DISTRACTOR-QUALITY-001** — only after content review, evaluate whether quiz-generation rules should avoid semantically adjacent distractors or near-duplicate definitions.
4. If findings are substantial, split follow-up content edits **one topic per PR**.

## 2. Topic inventory table

| Topic ID | Title | Entry count | 5-question readiness | 10-question readiness | “All” readiness | Main risks | Recommended action |
|---|---|---:|---|---|---|---|---|
| `kachestvennye_metody_issledovaniya` | Качественные методы исследования | 14 | Ready: enough entries and enough distractors. | Ready: enough entries and enough distractors. | Ready: all means 14 entries; stable while source file stays at 14 entries. | Conceptual overlap among entries about openness, subject approach, position of not knowing, double attention, methodological reflection, and method as instrument; one typo-like English word in a Russian definition; several broad definitions may be weak as answer options. | Start with typo/clarity polish and source/human review of overlapping concepts before changing quiz logic. |
| `osnovy_eksperimentalnoy_psihologii` | Основы экспериментальной психологии | 10 | Ready: enough entries and enough distractors. | Ready: exactly 10 entries. | Ready but not distinct from 10-question mode today; all means 10 entries. | Internal/external validity are intentionally similar terms and definitions; observation/interpretation are contrasting but could be paired as distractors; several entries need source confirmation beyond local `question:*` markers. | Keep behavior unchanged; perform source alignment for terminology and consider future distractor-quality guardrails only if learners report ambiguity. |

## 3. Entry-level findings

Severity key: `blocker`, `high`, `medium`, `low`, `review-needed`.

| Topic | Entry/term identifier or exact term | Issue type | Evidence | Severity | Recommended action |
|---|---|---|---|---|---|
| `kachestvennye_metody_issledovaniya` | `qual_methods_researcher_bias` / Предвзятость исследователя | Spelling / terminology consistency | The full definition uses the English word `bias` inside otherwise Russian prose: “возможных bias исследователя”. | low | In a content-polish PR, decide whether to keep `bias` as intentional terminology or replace with a Russian equivalent. |
| `kachestvennye_metody_issledovaniya` | `qual_methods_qualitative_methods` / Качественные методы исследования | Overly broad or weak definition | The short definition says this is a “Тема о качественных методах...” rather than defining the concept as a method family or approach. | review-needed | Human/source review should decide whether this is meant to be a topic-label entry or a true glossary term. |
| `kachestvennye_metody_issledovaniya` | `qual_methods_artifact` / Артефакт | Ambiguous term risk | “Артефакт” is broad across psychology/research contexts; repository evidence only defines it as a strange/contradictory fact needing qualitative understanding. | review-needed | Verify against source materials before narrowing or expanding the definition. |
| `kachestvennye_metody_issledovaniya` | `qual_methods_case_study` / Case study / анализ индивидуального случая | Capitalization / terminology consistency | The visible term mixes English and Russian and starts with English `Case study`; this may be intentional but differs from otherwise Russian terms. | low | In a polish PR, choose a consistent display convention if source materials allow it. |
| `kachestvennye_metody_issledovaniya` | `qual_methods_phenomenological_openness` and `qual_methods_position_of_not_knowing` | Near-duplicate concept risk | Both definitions emphasize staying with uncertainty / position of not knowing; both may become mutually plausible answer options. | medium | Source/human review should clarify distinct learning targets or merge/scope wording in a later content PR if appropriate. |
| `kachestvennye_metody_issledovaniya` | `qual_methods_methodological_reflection` and `qual_methods_double_attention` | Near-duplicate definition risk | Both definitions include attention to method/process and live interaction/contact. | medium | Clarify the difference between reflective stance and dual attention if source materials support that distinction. |
| `kachestvennye_metody_issledovaniya` | `qual_methods_subject_approach` and `qual_methods_phenomenological_openness` | Near-duplicate definition risk | Both definitions stress viewing the other person as a subject rather than an object. | medium | Clarify unique criteria for each term before any quiz-generation changes. |
| `kachestvennye_metody_issledovaniya` | `qual_methods_method_as_instrument` | Distractor-quality risk | The short definition says the method is important but does not replace live contact; this overlaps with entries about double attention and subject approach. | review-needed | Keep for now; source review should decide whether answer-option wording is distinctive enough. |
| `kachestvennye_metody_issledovaniya` | `qual_methods_focus_group` | Ambiguous / underspecified wording | The definition says participants are “похожие” and form/develop a common point of view. Without source context, this may underspecify variation in focus-group purposes. | review-needed | Verify with source before editing; avoid declaring incorrect without source evidence. |
| `kachestvennye_metody_issledovaniya` | `qual_methods_transcription` | Definition length / readability | Full definition is 23 words and includes several examples of speech details. It is likely acceptable but near the upper compact-UX range for feedback text. | low | Keep unless UI feedback becomes crowded; no urgent content change. |
| `kachestvennye_metody_issledovaniya` | `qual_methods_methodological_reflection` | Definition length / readability | Full definition is 26 words and contains a long list of ethical/safety dimensions. | low | Consider shortening only in a polish PR if human review confirms no meaning loss. |
| `kachestvennye_metody_issledovaniya` | `qual_methods_artifact` | Definition length / readability | Full definition is 27 words and lists several adjectives before the core explanation. | low | Consider compact wording later; not a blocker. |
| `kachestvennye_metody_issledovaniya` | `qual_methods_qualitative_methods` | Definition length / readability | Full definition is 29 words and reads like a topic placement note. | low | Review with source; likely better handled as clarity/source-alignment than as an immediate typo fix. |
| `osnovy_eksperimentalnoy_psihologii` | `exp_psych_internal_validity` and `exp_psych_external_validity` | Similar-term / similar-definition risk | The terms differ by internal/external scope, and both short definitions use validity-related transfer/causal-confidence wording. They are valid contrasting concepts but can be close distractors. | medium | Keep as valuable contrast; future distractor logic could avoid pairing them only if learner ambiguity is observed. |
| `osnovy_eksperimentalnoy_psihologii` | `exp_psych_observation` and `exp_psych_interpretation` | Multiple-defensible-answer risk if paired carelessly | These are intentionally contrasted; observation definition says data fixation without explanation, while interpretation says explanation of meaning. | low | Keep; pairing can be pedagogically useful, but source-aligned wording should remain crisp. |
| `osnovy_eksperimentalnoy_psihologii` | `exp_psych_hypothesis` | Broad definition risk | The definition is generally plausible but broad; repository evidence traces it to `question:m2_exp_017`, not an original source text. | review-needed | Verify terminology with original learning material before source-backed certification. |
| `osnovy_eksperimentalnoy_psihologii` | `exp_psych_hindsight` / Хиндсайт | Terminology consistency | The Russian term `Хиндсайт` may be acceptable course terminology, but repository evidence does not show whether a longer Russian label was intended. | review-needed | Human/source review should confirm display term and aliases before editing. |
| `osnovy_eksperimentalnoy_psihologii` | `exp_psych_confounding_variable` and `exp_psych_alternative_explanation` | Distractor-quality risk | Both describe factors or causes that complicate causal conclusions. They are distinct, but answer options could feel close to learners. | low | Keep; consider future distractor-quality evaluation with source-backed terms. |
| All topics | All entries | Provenance limitation | `source_refs` are repository-local markers such as `question:*` and `supplied_snippet:*`; this audit did not inspect original external source packs. | review-needed | Do not claim full source-backed certification until original materials are reviewed. |

## 4. Distractor and quiz-quality review

### Current generation behavior observed from repository code

- For each question, the term is shown and answer options are `short_definition` values.
- The correct option is the current entry's `short_definition`.
- Three distractors are sampled from other entries in the same topic.
- The same glossary quiz generation helper is shared by the classic Telegram glossary quiz and the Mini App glossary flow.

### Quality risks

| Risk | Evidence-backed assessment | Affected topics | Severity | Follow-up |
|---|---|---|---|---|
| Obviously absurd distractors | No strong evidence of absurd distractors. All active entries are within the selected topic, so distractors remain topically related. | Both | low | No immediate action. |
| Multiple defensible answers | Plausible when semantically adjacent entries are sampled together, especially in qualitative-methods terms about subjectivity, openness, method, and contact. This is a review hypothesis based on wording overlap, not a claim that current entries are incorrect. | Mostly `kachestvennye_metody_issledovaniya` | medium | Source/human review before content edits; then consider distractor pairing rules if still needed. |
| Definitions that reveal the term too directly | Most short definitions do not repeat the exact visible term. Some include close lexical hints such as “качественных методов” for `Качественные методы исследования` and “метод” for `Метод как инструмент`. | Both, mostly qualitative methods | low | Acceptable for now; polish only where source review supports it. |
| Duplicate learning targets | Potential duplicates/near-duplicates exist among `Феноменологическая открытость`, `Позиция незнания`, `Субъектный подход`, `Двойное внимание`, and `Методологическая рефлексия`. | `kachestvennye_metody_issledovaniya` | medium | Clarify distinct target concepts one topic at a time. |
| Insufficient variation across a session | Functional count is sufficient. However, `osnovy_eksperimentalnoy_psihologii` has exactly 10 entries, so 10-question and all-entry sessions cover the same entry set, with variation only in random order/options. | `osnovy_eksperimentalnoy_psihologii` | low | No blocker; document that “all” is not materially different from 10 until entry count changes. |

## 5. UX-readability review

### Telegram chat context

- Telegram question text displays the term plus four full `short_definition` options. Current short definitions are generally 7–13 words, which is plausible for a compact chat quiz.
- Longer option text can still be visually dense because all four options are stacked in one message.
- The feedback message displays the longer `definition`. Current definitions range roughly from 12 to 29 words in the audited entries; none appear extreme, but several qualitative-methods explanations are dense.

### Mini App context

- The Mini App uses the same `short_definition` options and later displays the full definition as feedback/explanation.
- Button scanning should be acceptable for most options, but semantically similar options increase cognitive load even when text length is moderate.
- Qualitative-methods definitions are more abstract and value-laden than experimental-psychology definitions, so they may feel more academic or overloaded in a small-screen flow.

### Readability findings

- **Most readable topic:** `osnovy_eksperimentalnoy_psihologii`. Terms are compact and definitions mostly describe clear research-method concepts.
- **Most readability-sensitive topic:** `kachestvennye_metody_issledovaniya`. Several definitions use abstract stance/process language, which makes distinctions harder to scan quickly.
- **Longest/most compact-UX-sensitive definitions:** `Качественные методы исследования`, `Артефакт`, `Методологическая рефлексия`, `Субъектный подход`, and `Метод как инструмент`.
- **No immediate blocker:** Definition length alone does not prevent 5, 10, or all modes from working.

## 6. Provenance and source posture

Repository-local evidence visible in active glossary files:

- `osnovy_eksperimentalnoy_psihologii` entries use `source_refs` values shaped like `question:m2_exp_*`.
- `kachestvennye_metody_issledovaniya` entries use `source_refs` values shaped like `supplied_snippet:practice10:*` and `supplied_snippet:practice12:*`.

What can be confirmed from repository evidence:

- Each active entry has non-empty `source_refs` values accepted by the current loader.
- The loader does not validate those references against an external source registry.
- The audit can identify local consistency and UX risks from the active JSON content.

What cannot be confirmed without original learning materials:

- Whether every term is source-complete and pedagogically canonical.
- Whether definitions are fully faithful to source materials.
- Whether terms such as `Хиндсайт`, `Артефакт`, `Феноменологическая открытость`, and `Case study / анализ индивидуального случая` use the intended course terminology.
- Whether broad/value-oriented definitions in the qualitative-methods topic intentionally reflect the source material or should be tightened.

Terms needing source/human review before content edits:

- `Качественные методы исследования`
- `Артефакт`
- `Феноменологическая открытость`
- `Позиция незнания`
- `Методологическая рефлексия`
- `Двойное внимание`
- `Субъектный подход`
- `Метод как инструмент`
- `Предвзятость исследователя`
- `Хиндсайт`
- `Гипотеза`
- `Смешивающая переменная`
- `Альтернативное объяснение`
- `Внутренняя валидность`
- `Внешняя валидность`

## 7. Recommended follow-up PR slicing

1. **GLOSSARY-CONTENT-POLISH-001**
   - Scope: typo/clarity/terminology consistency only.
   - Suggested first target: `kachestvennye_metody_issledovaniya`.
   - Examples: decide on `bias` wording, English/Russian display convention for `Case study`, and overly topic-like definition wording.
   - Non-goal: no quiz logic, API, UI, DB, or deployment changes.

2. **GLOSSARY-SOURCE-ALIGNMENT-001**
   - Scope: verify glossary terms and definitions against original learning materials or human SME review.
   - Suggested target: one topic at a time, starting with `kachestvennye_metody_issledovaniya` because it has more overlap risks.
   - Output: source-backed terminology decisions and explicit notes about what remains uncertain.

3. **GLOSSARY-DISTRACTOR-QUALITY-001**
   - Scope: only if source/content polish still leaves problematic pairings.
   - Possible investigation: avoid selecting near-neighbor concepts as distractors, add content metadata for distractor groups, or document intentionally useful contrasts.
   - Non-goal for this audit PR: no generation-logic change.

4. **GLOSSARY-CONTENT-POLISH-OEP-001**
   - Scope: targeted experimental-psychology wording review after source alignment.
   - Suggested focus: `Хиндсайт`, internal/external validity contrast, and causal-inference-adjacent entries.

## Appendix A. Active topic inventory used for this audit

| Topic ID | Title | Source file | Entry count |
|---|---|---|---:|
| `kachestvennye_metody_issledovaniya` | Качественные методы исследования | `content/glossary/kachestvennye_metody_issledovaniya.json` | 14 |
| `osnovy_eksperimentalnoy_psihologii` | Основы экспериментальной психологии | `content/glossary/osnovy_eksperimentalnoy_psihologii.json` | 10 |

## Appendix B. Audit method

- Inspected the glossary loader and topic list to identify active topics and file paths.
- Inspected classic Telegram glossary and Mini App glossary code paths to confirm shared glossary source usage.
- Loaded active glossary JSON through repository code and counted entries per topic.
- Reviewed every active entry's `term`, `short_definition`, `definition`, aliases, difficulty, and `source_refs` from repository-local JSON evidence.
- Compared term and definition wording for duplicate, near-duplicate, ambiguous, broad, circular, weak, long, or inconsistent content risks.
- Treated uncertain source/terminology concerns as `review-needed` rather than as correctness claims.
