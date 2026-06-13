# Module 2 qualitative methods source-alignment evidence report

## Scope and limitations

This is a narrow metadata/source_ref QA pass for `Качественные методы исследования` in `content/questions/module2/kachestvennye_metody_issledovaniya.json`.

- Current repository question source of truth: `content/questions/**/*.json`.
- Current topic file: `content/questions/module2/kachestvennye_metody_issledovaniya.json`.
- Current approved topic range covered by this report: `m2_qual_001` through `m2_qual_053`.
- This PR replaces eight unsupported P0 terminology questions with source-backed presentation/practice questions based on supplied text-backed evidence.
- This PR makes no count/runtime behavior change: no questions were added or removed and no question IDs changed. The replaced items keep their existing IDs and approved status.
- This report does not claim that all 53 questions are fully source-backed.
- Statuses such as `supported`, `weakly_supported`, and `source_ref_alignment_risk` are routing signals from supplied evidence, not final source-backed certification.
- This report does not claim that Module 1/2 source alignment is complete.
- PR #230 added provenance-limited tracking and is not treated here as full source-backed completion.

Codex did not inspect Google Drive or the original source files directly. This pass uses only the supplied evidence pack and repository files. Human/source review remains required before treating any item as source-backed completion evidence.

## Source materials named in supplied evidence

The supplied evidence named the following source areas, but this report does not independently verify access method, PDF visual inspection, or text readability:

- Practice transcripts:
  - `Практика №10`
  - `Практика №11`
  - `Практика №12`
- PDF presentation snippets were supplied by the user for this replacement task. Codex did not inspect Google Drive or the original PDFs directly.

Important provenance limitation: Codex cannot certify that PDFs were visually inspected, that recommended literature was fully text-readable, or that the supplied evidence is complete. Human/source review remains required before treating any item as source-backed completion evidence.

## Post-PR #231 supplied source-review addendum

After PR #231 was merged, a supplied source-review pass provided additional text-evidence snippets for selected Practice 10, 11, and 12 materials. Codex did not inspect Google Drive, PDFs, or original source files for this addendum; the notes below are provenance-limited updates based only on those supplied snippets. They refine routing risk and future-review notes, but do not convert this report into final source-backed certification for all 53 questions.

Key addendum notes:

- `m2_qual_004`: strengthened support from Practice 11. The supplied snippet says Practice 11 directly discusses researcher reflexivity: because knowledge is shaped through an individual lens/view, the researcher should reflect on authorial assumptions, positions, attitudes, and values underlying cognition and description of reality. This reinforces PR #231's routing of `m2_qual_004.source_ref` to `module2/qualitative/practice11`.
- `m2_qual_010`: the current conservative `source_ref` of `module2/qualitative/practice10` remains acceptable. The supplied snippets say both Practice 10 and Practice 11 contain support for case study / analysis of an individual case, so this is not a high-risk source_ref issue even though Practice 11 also has relevant material.
- `m2_qual_028`: remains a candidate for future source_ref review toward Practice 12. The supplied snippet says Practice 12 discusses transferability and explicitly distinguishes it from quantitative representativeness.
- `m2_qual_039`: has partial Practice 12 support for transcription/detail wording. The supplied snippet says Practice 12 discusses transcription/decoding detail, including attention to words, pauses, restarts, slips, and other analytically relevant speech features; however, exact anonymization / indirect-identifier wording still needs source review.
- `m2_qual_006`, `m2_qual_024`, `m2_qual_025`, `m2_qual_026`, `m2_qual_029`, `m2_qual_040`, `m2_qual_043`, and `m2_qual_053`: the previous unsupported P0 terminology questions were replaced with source-backed questions using the supplied presentation / Practice 11 / Practice 12 snippets. The removed unsupported terms were saturation as a sampling stopping criterion, audit trail, triangulation, member checking / respondent validation, and team coding / codebook calibration.

## Current source_ref distribution after this replacement pass

| source_ref | question count | question_id(s) |
|---|---:|---|
| `module2/qualitative/lecture1_intro` | 14 | `m2_qual_001`, `m2_qual_002`, `m2_qual_003`, `m2_qual_006`, `m2_qual_013`, `m2_qual_014`, `m2_qual_017`, `m2_qual_024`, `m2_qual_025`, `m2_qual_026`, `m2_qual_027`, `m2_qual_029`, `m2_qual_032`, `m2_qual_041` |
| `module2/qualitative/practice10` | 13 | `m2_qual_005`, `m2_qual_010`, `m2_qual_016`, `m2_qual_018`, `m2_qual_019`, `m2_qual_020`, `m2_qual_031`, `m2_qual_035`, `m2_qual_038`, `m2_qual_042`, `m2_qual_044`, `m2_qual_048`, `m2_qual_051` |
| `module2/qualitative/practice11` | 16 | `m2_qual_004`, `m2_qual_007`, `m2_qual_008`, `m2_qual_009`, `m2_qual_021`, `m2_qual_022`, `m2_qual_023`, `m2_qual_028`, `m2_qual_033`, `m2_qual_036`, `m2_qual_039`, `m2_qual_043`, `m2_qual_045`, `m2_qual_047`, `m2_qual_049`, `m2_qual_052` |
| `module2/qualitative/practice12` | 10 | `m2_qual_011`, `m2_qual_012`, `m2_qual_015`, `m2_qual_030`, `m2_qual_034`, `m2_qual_037`, `m2_qual_040`, `m2_qual_046`, `m2_qual_050`, `m2_qual_053` |

## Corrections made in this QA pass

| question_id | previous unsupported term/question | replacement support basis | source_ref after replacement |
|---|---|---|---|
| `m2_qual_006` | Saturation as sampling stopping criterion | Presentation meeting 1: qualitative methodology aligns with humanitarian/idiographic orientation and holistic cases. | `module2/qualitative/lecture1_intro` |
| `m2_qual_024` | Audit trail | Presentation meeting 1: humanitarian/sociocultural/cultural-historical orientation emphasizes critique of objectivism, dialogue, context, interpretations, and individual cases. | `module2/qualitative/lecture1_intro` |
| `m2_qual_025` | Triangulation | Presentation meeting 1: contrast between quantitative formalized/hypothesis-testing methodology and qualitative freer/descriptive/interpretive methodology. | `module2/qualitative/lecture1_intro` |
| `m2_qual_026` | Member checking / respondent validation | Presentation meeting 2: situations where qualitative research is necessary or possible, including underexplored topics, deep immersion in respondent experience, and context. | `module2/qualitative/lecture1_intro` |
| `m2_qual_029` | Saturation as sampling stopping criterion | Presentation meeting 1: qualitative methodology supports discovery of the new and detailed description of holistic cases. | `module2/qualitative/lecture1_intro` |
| `m2_qual_040` | Team coding / codebook calibration | Practice 12: qualitative transcription/decoding may attend to pauses, restarts, slips, and other analytically relevant speech features. | `module2/qualitative/practice12` |
| `m2_qual_043` | Member checking / respondent validation | Practice 11: researcher reflexivity includes reflecting on assumptions, positions, attitudes, and values. | `module2/qualitative/practice11` |
| `m2_qual_053` | Audit trail | Practice 12: transferability is discussed and explicitly distinguished from quantitative representativeness. | `module2/qualitative/practice12` |

Earlier PR #231 corrections retained in the current file:

| question_id | field | previous value | new value | rationale |
|---|---|---|---|---|
| `m2_qual_004` | `source_ref` | `module2/qualitative/practice10` | `module2/qualitative/practice11` | Source_ref corrected based on supplied text-backed evidence: Practice 11 explicitly supports researcher reflexivity as reflection on the researcher's assumptions, position, values, and effect on knowledge production. |
| `m2_qual_010` | `source_ref` | `module2/qualitative/practice11` | `module2/qualitative/practice10` | Source_ref corrected based on supplied text-backed evidence: Practice 10 supports case study / analysis of individual cases as part of qualitative methodology. |

## Evidence matrix

| question_id(s) | source_ref after this pass | source document(s) from supplied evidence | support_status | evidence summary | recommended action |
|---|---|---|---|---|---|
| `m2_qual_001`, `m2_qual_002`, `m2_qual_003`, `m2_qual_017` | `module2/qualitative/lecture1_intro` | Supplied notes: Practice 10/11; presentation materials | `supported` | Supplied evidence says qualitative methods are discussed as focused on meaning, experience, context, interpretation, and contrast with quantitative/formalized approaches. Treat as a routing signal rather than final certification. | Keep; human/source review remains required before completion claims. |
| `m2_qual_004` | `module2/qualitative/practice11` | Supplied notes: Practice 11; post-PR #231 supplied source-review snippet | `source_ref_corrected` | Supplied evidence routes researcher reflexivity to Practice 11; the post-PR #231 snippet strengthens this by describing reflexivity as reflection on the researcher's authorial assumptions, positions, attitudes, and values because knowledge is shaped through an individual lens/view. | Keep corrected `source_ref`; still not final source-backed certification. |
| `m2_qual_005`, `m2_qual_051` | `module2/qualitative/practice10` | Supplied notes: Practice 10 | `weakly_supported` | Supplied evidence says Practice 10 supports case-focused or targeted study of informative individual cases rather than statistical-majority logic, but the exact term “purposive sampling” was not clearly found. | Keep for now; source wording needs later refinement if strict term-level alignment is required. |
| `m2_qual_010` | `module2/qualitative/practice10` | Supplied notes: Practice 10; post-PR #231 supplied source-review snippet for Practice 10 and Practice 11 | `source_ref_corrected` | Supplied evidence routes case study / individual-case analysis to Practice 10. The post-PR #231 snippet says both Practice 10 and Practice 11 contain support for case study / analysis of an individual case, so current Practice 10 routing is acceptable and not high-risk. | Keep corrected `source_ref`; still not final source-backed certification. |
| `m2_qual_018`, `m2_qual_019`, `m2_qual_020`, `m2_qual_031`, `m2_qual_032`, `m2_qual_033`, `m2_qual_044`, `m2_qual_045`, `m2_qual_046` | mixed: `module2/qualitative/practice10`, `module2/qualitative/practice11`, `module2/qualitative/practice12`, `module2/qualitative/lecture1_intro` | Supplied notes: Practice 10; Practice 12 | `weakly_supported` | Supplied evidence says qualitative interviews, in-depth/semistructured interviews, and understanding experience and meaning are supported. Some exact micro-skill terms were not established by the supplied notes. | Keep; later source pass should verify exact terminology if stricter alignment is required. |
| `m2_qual_009`, `m2_qual_022`, `m2_qual_038`, `m2_qual_052` | mixed: `module2/qualitative/practice10`, `module2/qualitative/practice11` | Supplied notes: Practice 12 | `source_ref_alignment_risk` | Supplied evidence routes focus groups as a group interview/discussion method around a shared topic to Practice 12, while current question `source_ref` values point to Practice 10 or Practice 11. This pass leaves them unchanged because the moderator-balance wording and exact behavioral guidance were not directly confirmed by the supplied transcripts. | Needs human/source review before claiming direct support or changing source_ref. |
| `m2_qual_013`, `m2_qual_014`, `m2_qual_028` | mixed: `module2/qualitative/lecture1_intro`, `module2/qualitative/practice11` | Supplied notes: Practice 12; post-PR #231 supplied source-review snippet for Practice 12 | `source_ref_alignment_risk` | Supplied evidence routes this quality-criteria cluster to Practice 12, while current question `source_ref` values point to lecture intro or Practice 11. For `m2_qual_028`, the post-PR #231 snippet adds stronger Practice 12 support because Practice 12 discusses transferability and distinguishes it from quantitative representativeness. | Keep for now; treat `m2_qual_028` as a candidate for future source_ref review toward Practice 12 before claiming direct support. |
| `m2_qual_015`, `m2_qual_027`, `m2_qual_039`, `m2_qual_047` | mixed: `module2/qualitative/practice12`, `module2/qualitative/lecture1_intro`, `module2/qualitative/practice11` | Supplied notes: Practice 10; Practice 12; post-PR #231 supplied source-review snippet for Practice 12 | `needs_human_source_review` | Confidentiality/context is discussed in the supplied evidence, but indirect identifiers / pseudonymization are only weakly supported and exact anonymization wording was not strongly confirmed. For `m2_qual_039`, the post-PR #231 snippet adds partial Practice 12 support for transcription/detail because it describes attention to transcription/decoding, including words, pauses, restarts, slips, and other analytically relevant speech features; exact anonymization / indirect-identifier wording still needs source review. | Needs human/source review before claiming direct support; keep `m2_qual_039` as partial transcription support only. |
| `m2_qual_030`, `m2_qual_050` | `module2/qualitative/practice12` | Supplied notes: Practice 12 | `supported` | Supplied evidence routes these items to Practice 12 and says the source discusses context, detailed description, and avoiding overgeneralization beyond what qualitative evidence supports. Treat this as a planning signal, not final certification. | Keep; human/source review remains required before completion claims. |
| `m2_qual_006`, `m2_qual_029` | `module2/qualitative/lecture1_intro` | Supplied presentation snippets, meeting 1 | `replaced_source_backed_by_supplied_snippet` | Previous saturation questions were replaced. New items cover qualitative methodology as humanitarian/idiographic, discovery-oriented, descriptive/interpretive, and focused on holistic cases. | Keep; no saturation claim remains in these items. Human/source review still required for broader completion claims. |
| `m2_qual_011`, `m2_qual_012` | `module2/qualitative/practice12` | Supplied notes only | `needs_human_source_review` | Thematic-analysis sequence and themes are plausible, but supplied evidence did not establish direct source evidence for the specific coding-to-theme sequence. | Human/source review before claiming direct source support. |
| `m2_qual_023`, `m2_qual_041` | mixed: `module2/qualitative/practice11`, `module2/qualitative/lecture1_intro` | Supplied notes only | `needs_human_source_review` | Code/category/theme hierarchy is plausible, but supplied evidence did not establish direct evidence for the exact hierarchy. | Human/source review before claiming direct source support. |
| `m2_qual_024`, `m2_qual_053` | mixed: `module2/qualitative/lecture1_intro`, `module2/qualitative/practice12` | Supplied presentation meeting 1 and Practice 12 snippets | `replaced_source_backed_by_supplied_snippet` | Previous audit-trail questions were replaced. `m2_qual_024` now asks about humanitarian orientation; `m2_qual_053` now asks about transferability versus quantitative representativeness. | Keep; no audit-trail claim remains in these items. Human/source review still required for broader completion claims. |
| `m2_qual_025` | `module2/qualitative/lecture1_intro` | Supplied presentation snippet, meeting 1 | `replaced_source_backed_by_supplied_snippet` | Previous triangulation question was replaced. New item asks about the presentation-backed contrast between quantitative formalized/hypothesis-testing methodology and qualitative freer/descriptive/interpretive methodology. | Keep; no triangulation claim remains in this item. Human/source review still required for broader completion claims. |
| `m2_qual_026`, `m2_qual_043` | mixed: `module2/qualitative/lecture1_intro`, `module2/qualitative/practice11` | Supplied presentation meeting 2 and Practice 11 snippets | `replaced_source_backed_by_supplied_snippet` | Previous member-checking/respondent-validation questions were replaced. `m2_qual_026` now covers presentation-backed situations for qualitative research; `m2_qual_043` now covers Practice 11 researcher reflexivity. | Keep; no member-checking/respondent-validation claim remains in these items. Human/source review still required for broader completion claims. |
| `m2_qual_040` | `module2/qualitative/practice12` | Supplied Practice 12 snippet | `replaced_source_backed_by_supplied_snippet` | Previous team-coding/codebook-calibration question was replaced. New item asks about Practice 12 transcription/decoding detail: attention to words, pauses, restarts, slips, and other analytically relevant speech features. | Keep; no team-coding/codebook-calibration claim remains in this item. Human/source review still required for broader completion claims. |

## Report conclusion

This narrow replacement pass replaces eight unsupported P0 terminology questions with source-backed presentation/practice questions and preserves all question IDs, total count, approved count, and runtime behavior. It is not a completed source-alignment matrix, not final source-backed certification for the 53 questions, and not a Module 1/2 completion claim.

Remaining weak, partial, or source_ref-alignment-risk items outside the eight requested replacements are intentionally left for later human/source review instead of being rewritten or overclaimed in this PR.
