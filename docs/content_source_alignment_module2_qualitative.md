# Module 2 qualitative methods source-alignment evidence report

## Scope and limitations

This is a narrow metadata/source_ref QA pass for `Качественные методы исследования` in `content/questions/module2/kachestvennye_metody_issledovaniya.json`.

- Current repository question source of truth: `content/questions/**/*.json`.
- Current topic file: `content/questions/module2/kachestvennye_metody_issledovaniya.json`.
- Current approved topic range covered by this report: `m2_qual_001` through `m2_qual_053`.
- This PR corrects two `source_ref` values based on supplied text-backed evidence.
- This PR makes no count/runtime behavior change: no questions were added or removed, no question IDs changed, and no `correct_option_index` values changed.
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
- PDF presentations were described as visually inspected but without reliable extractable text in the assistant environment. PDF-based evidence is therefore contextual only and is not used as the sole basis for strict source-backed corrections.

Important provenance limitation: Codex cannot certify that PDFs were visually inspected, that recommended literature was fully text-readable, or that the supplied evidence is complete. Human/source review remains required before treating any item as source-backed completion evidence.

## Current source_ref distribution after this QA pass

| source_ref | question count | question_id(s) |
|---|---:|---|
| `module2/qualitative/lecture1_intro` | 9 | `m2_qual_001`, `m2_qual_002`, `m2_qual_003`, `m2_qual_013`, `m2_qual_014`, `m2_qual_017`, `m2_qual_027`, `m2_qual_032`, `m2_qual_041` |
| `module2/qualitative/practice10` | 15 | `m2_qual_005`, `m2_qual_006`, `m2_qual_010`, `m2_qual_016`, `m2_qual_018`, `m2_qual_019`, `m2_qual_020`, `m2_qual_029`, `m2_qual_031`, `m2_qual_035`, `m2_qual_038`, `m2_qual_042`, `m2_qual_044`, `m2_qual_048`, `m2_qual_051` |
| `module2/qualitative/practice11` | 16 | `m2_qual_004`, `m2_qual_007`, `m2_qual_008`, `m2_qual_009`, `m2_qual_021`, `m2_qual_022`, `m2_qual_023`, `m2_qual_028`, `m2_qual_033`, `m2_qual_036`, `m2_qual_039`, `m2_qual_043`, `m2_qual_045`, `m2_qual_047`, `m2_qual_049`, `m2_qual_052` |
| `module2/qualitative/practice12` | 13 | `m2_qual_011`, `m2_qual_012`, `m2_qual_015`, `m2_qual_024`, `m2_qual_025`, `m2_qual_026`, `m2_qual_030`, `m2_qual_034`, `m2_qual_037`, `m2_qual_040`, `m2_qual_046`, `m2_qual_050`, `m2_qual_053` |

## Corrections made in this QA pass

| question_id | field | previous value | new value | rationale |
|---|---|---|---|---|
| `m2_qual_004` | `source_ref` | `module2/qualitative/practice10` | `module2/qualitative/practice11` | Source_ref corrected based on supplied text-backed evidence: Practice 11 explicitly supports researcher reflexivity as reflection on the researcher's assumptions, position, values, and effect on knowledge production. |
| `m2_qual_010` | `source_ref` | `module2/qualitative/practice11` | `module2/qualitative/practice10` | Source_ref corrected based on supplied text-backed evidence: Practice 10 supports case study / analysis of individual cases as part of qualitative methodology. |

## Evidence matrix

| question_id(s) | source_ref after this pass | source document(s) from supplied evidence | support_status | evidence summary | recommended action |
|---|---|---|---|---|---|
| `m2_qual_001`, `m2_qual_002`, `m2_qual_003`, `m2_qual_017` | `module2/qualitative/lecture1_intro` | Supplied notes: Practice 10/11; presentation materials | `supported` | Supplied evidence says qualitative methods are discussed as focused on meaning, experience, context, interpretation, and contrast with quantitative/formalized approaches. Treat as a routing signal rather than final certification. | Keep; human/source review remains required before completion claims. |
| `m2_qual_004` | `module2/qualitative/practice11` | Supplied notes: Practice 11 | `source_ref_corrected` | Supplied text-backed evidence routes researcher reflexivity to Practice 11. | Keep corrected `source_ref`; still not final source-backed certification. |
| `m2_qual_005`, `m2_qual_051` | `module2/qualitative/practice10` | Supplied notes: Practice 10 | `weakly_supported` | Supplied evidence says Practice 10 supports case-focused or targeted study of informative individual cases rather than statistical-majority logic, but the exact term “purposive sampling” was not clearly found. | Keep for now; source wording needs later refinement if strict term-level alignment is required. |
| `m2_qual_010` | `module2/qualitative/practice10` | Supplied notes: Practice 10 | `source_ref_corrected` | Supplied text-backed evidence routes case study / individual-case analysis to Practice 10. | Keep corrected `source_ref`; still not final source-backed certification. |
| `m2_qual_018`, `m2_qual_019`, `m2_qual_020`, `m2_qual_031`, `m2_qual_032`, `m2_qual_033`, `m2_qual_044`, `m2_qual_045`, `m2_qual_046` | mixed: `module2/qualitative/practice10`, `module2/qualitative/practice11`, `module2/qualitative/practice12`, `module2/qualitative/lecture1_intro` | Supplied notes: Practice 10; Practice 12 | `weakly_supported` | Supplied evidence says qualitative interviews, in-depth/semistructured interviews, and understanding experience and meaning are supported. Some exact micro-skill terms were not established by the supplied notes. | Keep; later source pass should verify exact terminology if stricter alignment is required. |
| `m2_qual_009`, `m2_qual_022`, `m2_qual_038`, `m2_qual_052` | mixed: `module2/qualitative/practice10`, `module2/qualitative/practice11` | Supplied notes: Practice 12 | `source_ref_alignment_risk` | Supplied evidence routes focus groups as a group interview/discussion method around a shared topic to Practice 12, while current question `source_ref` values point to Practice 10 or Practice 11. This pass leaves them unchanged because the moderator-balance wording and exact behavioral guidance were not directly confirmed by the supplied transcripts. | Needs human/source review before claiming direct support or changing source_ref. |
| `m2_qual_013`, `m2_qual_014`, `m2_qual_028` | mixed: `module2/qualitative/lecture1_intro`, `module2/qualitative/practice11` | Supplied notes: Practice 12 | `source_ref_alignment_risk` | Supplied evidence routes this quality-criteria cluster to Practice 12, while current question `source_ref` values point to lecture intro or Practice 11. The concepts may be supportable, but source_ref/document alignment needs human verification. | Keep for now; verify source_ref alignment before claiming direct support. |
| `m2_qual_015`, `m2_qual_027`, `m2_qual_039`, `m2_qual_047` | mixed: `module2/qualitative/practice12`, `module2/qualitative/lecture1_intro`, `module2/qualitative/practice11` | Supplied notes: Practice 10; Practice 12 | `needs_human_source_review` | Confidentiality/context is discussed in the supplied evidence, but indirect identifiers / pseudonymization are only weakly supported and exact anonymization wording was not strongly confirmed. | Needs human/source review before claiming direct support. |
| `m2_qual_030`, `m2_qual_050` | `module2/qualitative/practice12` | Supplied notes: Practice 12 | `supported` | Supplied evidence routes these items to Practice 12 and says the source discusses context, detailed description, and avoiding overgeneralization beyond what qualitative evidence supports. Treat this as a planning signal, not final certification. | Keep; human/source review remains required before completion claims. |
| `m2_qual_006`, `m2_qual_029` | `module2/qualitative/practice10` | Supplied notes only | `needs_human_source_review` | Saturation is plausible qualitative-methods content, but supplied evidence did not establish direct source evidence for saturation. Occurrences of “насыщенно” in Practice 10 refer to rich/naturated description, not saturation as a sampling stopping criterion. | Human/source review before claiming direct source support. |
| `m2_qual_011`, `m2_qual_012` | `module2/qualitative/practice12` | Supplied notes only | `needs_human_source_review` | Thematic-analysis sequence and themes are plausible, but supplied evidence did not establish direct source evidence for the specific coding-to-theme sequence. | Human/source review before claiming direct source support. |
| `m2_qual_023`, `m2_qual_041` | mixed: `module2/qualitative/practice11`, `module2/qualitative/lecture1_intro` | Supplied notes only | `needs_human_source_review` | Code/category/theme hierarchy is plausible, but supplied evidence did not establish direct evidence for the exact hierarchy. | Human/source review before claiming direct source support. |
| `m2_qual_024`, `m2_qual_053` | `module2/qualitative/practice12` | Supplied notes only | `needs_human_source_review` | Audit-trail terminology was not established by the supplied evidence. | Human/source review before claiming direct source support. |
| `m2_qual_025` | `module2/qualitative/practice12` | Supplied notes only | `needs_human_source_review` | Triangulation terminology was not established by the supplied evidence. | Human/source review before claiming direct source support. |
| `m2_qual_026`, `m2_qual_043` | mixed: `module2/qualitative/practice12`, `module2/qualitative/practice11` | Supplied notes only | `needs_human_source_review` | Member checking / respondent validation terminology was not established by the supplied evidence. | Human/source review before claiming direct source support. |
| `m2_qual_040` | `module2/qualitative/practice12` | Supplied notes only | `needs_human_source_review` | Team coding calibration / codebook consistency terminology was not established by the supplied evidence. | Human/source review before claiming direct source support. |

## Report conclusion

This narrow QA pass corrects only two `source_ref` values based on supplied text-backed evidence and preserves all question IDs, approved counts, answer keys, and runtime behavior. It is not a completed source-alignment matrix, not final source-backed certification for the 53 questions, and not a Module 1/2 completion claim.

Remaining weak or unsupported terminology is intentionally left for later human/source review instead of being rewritten or overclaimed in this PR.
