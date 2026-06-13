# Module 2 qualitative methods source-alignment evidence report

## Scope and limitations

This is a focused topic-level evidence report for `Качественные методы исследования` in `content/questions/module2/kachestvennye_metody_issledovaniya.json`.

- Current repository question source of truth: `content/questions/**/*.json`.
- Current topic file: `content/questions/module2/kachestvennye_metody_issledovaniya.json`.
- Current approved topic range covered by this report: `m2_qual_001` through `m2_qual_053`.
- No question JSON was changed for this report.
- This report does not claim that all 53 questions are fully source-backed.
- This report does not claim that Module 1/2 source alignment is complete.
- PR #229 was closed and not merged, so it is not treated here as completed source-backed alignment.

Codex did not inspect Google Drive or the original source files directly. This report records a supplied evidence pack from an assistant source review and aligns that evidence with the current repository question IDs and `source_ref` groups.

## Source materials represented in supplied evidence pack

The supplied evidence pack reported review of:

- Topic folder `Качественные методы исследования`:
  - `Презентация_Качественные+методы_1.pdf`
  - `Презентация_Качественные_методы_исследования_2.pdf`
  - `Качественные_методы_исследования_3.pdf`
  - recommended literature documents for meetings 1, 2, and 3
- Practice transcripts:
  - `Практика №10`
  - `Практика №11`
  - `Практика №12`

Important supplied-source limitation: the PDF presentations had no extractable text layer in the assistant environment and were visually rendered/inspected; practice transcripts and recommended literature documents were text-readable.

## Current source_ref distribution

| source_ref | question count | question_id(s) |
|---|---:|---|
| `module2/qualitative/lecture1_intro` | 9 | `m2_qual_001`, `m2_qual_002`, `m2_qual_003`, `m2_qual_013`, `m2_qual_014`, `m2_qual_017`, `m2_qual_027`, `m2_qual_032`, `m2_qual_041` |
| `module2/qualitative/practice10` | 15 | `m2_qual_004`, `m2_qual_005`, `m2_qual_006`, `m2_qual_016`, `m2_qual_018`, `m2_qual_019`, `m2_qual_020`, `m2_qual_029`, `m2_qual_031`, `m2_qual_035`, `m2_qual_038`, `m2_qual_042`, `m2_qual_044`, `m2_qual_048`, `m2_qual_051` |
| `module2/qualitative/practice11` | 16 | `m2_qual_007`, `m2_qual_008`, `m2_qual_009`, `m2_qual_010`, `m2_qual_021`, `m2_qual_022`, `m2_qual_023`, `m2_qual_028`, `m2_qual_033`, `m2_qual_036`, `m2_qual_039`, `m2_qual_043`, `m2_qual_045`, `m2_qual_047`, `m2_qual_049`, `m2_qual_052` |
| `module2/qualitative/practice12` | 13 | `m2_qual_011`, `m2_qual_012`, `m2_qual_015`, `m2_qual_024`, `m2_qual_025`, `m2_qual_026`, `m2_qual_030`, `m2_qual_034`, `m2_qual_037`, `m2_qual_040`, `m2_qual_046`, `m2_qual_050`, `m2_qual_053` |

## Evidence matrix

| question_id(s) | source_ref | source document(s) | support_status | evidence summary | recommended action |
|---|---|---|---|---|---|
| `m2_qual_001`, `m2_qual_002`, `m2_qual_003`, `m2_qual_017` | `module2/qualitative/lecture1_intro` | Practice 10/11; presentation materials | `supported` | Supplied evidence says qualitative methods are discussed as focused on meaning, experience, context, interpretation, and contrast with quantitative/formalized approaches. | Keep. |
| `m2_qual_004` | `module2/qualitative/practice10` | Practice 11 | `supported` | Supplied evidence says Practice 11 explicitly discusses reflecting on the researcher/practitioner’s assumptions, position, values, and their effect on knowledge production. | Keep. |
| `m2_qual_005`, `m2_qual_051` | `module2/qualitative/practice10` | Practice 10 | `weakly_supported` | Supplied evidence says Practice 10 supports case-focused or targeted study of informative individual cases rather than statistical-majority logic, but the exact term “purposive sampling” was not clearly found. | Keep for now; source wording needs later refinement if strict term-level alignment is required. |
| `m2_qual_010` | `module2/qualitative/practice11` | Practice 10; meeting 2 recommended literature | `supported` | Supplied evidence says case study is discussed as analysis of an individual case, and meeting 2 recommended literature includes case-study methodology. | Keep. |
| `m2_qual_018`, `m2_qual_019`, `m2_qual_020`, `m2_qual_031`, `m2_qual_032`, `m2_qual_033`, `m2_qual_044`, `m2_qual_045`, `m2_qual_046` | mixed: `module2/qualitative/practice10`, `module2/qualitative/practice11`, `module2/qualitative/practice12`, `module2/qualitative/lecture1_intro` | Practice materials | `weakly_supported` | Supplied evidence says qualitative interviews, deep/semistructured interviews, the importance of how questions are asked, and non-leading or clarifying exploration of lived experience are supported. Some exact micro-skill terms were not directly named in readable text. | Keep; later source pass should verify exact terminology if stricter alignment is required. |
| `m2_qual_009`, `m2_qual_022`, `m2_qual_038`, `m2_qual_052` | mixed: `module2/qualitative/practice10`, `module2/qualitative/practice11` | Practice 12 | `weakly_supported` | Supplied evidence says Practice 12 mentions focus groups as group interview/discussion around a shared topic. Moderator-balance items are reasonable applied questions, but not all exact behaviors were directly found in readable text. | Keep; mark as weakly supported. |
| `m2_qual_013`, `m2_qual_014`, `m2_qual_028` | mixed: `module2/qualitative/lecture1_intro`, `module2/qualitative/practice11` | Practice 12 | `supported` | Supplied evidence says qualitative quality criteria differ from quantitative validity/reliability and emphasize transparency, detailed description, and transferability of well-described experience to other contexts. | Keep. |
| `m2_qual_015`, `m2_qual_027`, `m2_qual_039`, `m2_qual_047` | mixed: `module2/qualitative/practice12`, `module2/qualitative/lecture1_intro`, `module2/qualitative/practice11` | Practice 10; Practice 12 | `weakly_supported` | Supplied evidence says confidentiality, ethics, safety, transcription, and context are discussed. Direct pseudonymization or indirect-identifier wording was not strongly found. | Keep; later pass should verify exact source wording. |
| `m2_qual_030`, `m2_qual_050` | `module2/qualitative/practice12` | Practice 12 | `supported` | Supplied evidence says Practice 12 discusses context, detailed description, and avoiding overgeneralization beyond what qualitative evidence supports. | Keep. |
| `m2_qual_006`, `m2_qual_029` | `module2/qualitative/practice10` | Checked transcripts in supplied evidence pack | `needs_human_source_review` | Saturation is plausible qualitative-methods content, but supplied evidence did not find direct readable source evidence for saturation in checked transcripts. | Human/source review before claiming direct source support. |
| `m2_qual_011`, `m2_qual_012` | `module2/qualitative/practice12` | Checked transcripts in supplied evidence pack | `needs_human_source_review` | Thematic-analysis steps and themes are plausible, but supplied evidence did not find direct source evidence for the specific coding-to-theme sequence in checked transcripts. | Human/source review before claiming direct source support. |
| `m2_qual_023`, `m2_qual_041` | mixed: `module2/qualitative/practice11`, `module2/qualitative/lecture1_intro` | Checked transcripts in supplied evidence pack | `needs_human_source_review` | Code/category/theme distinction is plausible, but supplied evidence found only generic “codes” references rather than direct evidence for the exact hierarchy. | Human/source review before claiming direct source support. |
| `m2_qual_024`, `m2_qual_053` | `module2/qualitative/practice12` | Checked transcripts in supplied evidence pack | `needs_human_source_review` | Audit-trail terminology was not found in checked readable source text. | Human/source review before claiming direct source support. |
| `m2_qual_025` | `module2/qualitative/practice12` | Checked transcripts in supplied evidence pack | `needs_human_source_review` | Triangulation terminology was not found in checked readable source text. | Human/source review before claiming direct source support. |
| `m2_qual_026`, `m2_qual_043` | mixed: `module2/qualitative/practice12`, `module2/qualitative/practice11` | Checked transcripts in supplied evidence pack | `needs_human_source_review` | Member checking / respondent validation terminology was not found in checked readable source text. | Human/source review before claiming direct source support. |
| `m2_qual_040` | `module2/qualitative/practice12` | Checked transcripts in supplied evidence pack | `needs_human_source_review` | Team coding calibration / codebook consistency terminology was not found in checked readable source text. | Human/source review before claiming direct source support. |

## Report conclusion

The supplied evidence pack supports keeping many current Module 2 qualitative-methods questions, but several items are only weakly supported and several still require human/source review before direct source-backed completion can be claimed. This report is therefore an evidence-routing and risk-recording document, not a content-completion claim.

No JSON, runtime, database, CI/CD, deploy, dependency, or question-content changes were made as part of this report.
