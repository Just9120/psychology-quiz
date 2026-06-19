# Glossary distractor engine

## Previous behavior

Glossary quiz generation previously selected distractors by sampling any three other short definitions from the same topic. The `confusable_with` field in glossary JSON was validated as metadata, but it was not loaded into `GlossaryEntry` and had no runtime effect.

That made some questions too easy because distractors could be unrelated to the target term.

## Ranked same-topic selection policy

Glossary quiz generation now builds distractors from same-topic glossary entries and ranks candidates before filling the three distractor slots:

1. **Tier 1 — direct confusables:** entries listed in the current entry's `confusable_with` metadata.
2. **Tier 2 — reciprocal confusables:** entries whose `confusable_with` metadata lists the current entry ID.
3. **Tier 3 — remaining same-topic entries:** valid same-topic entries not already selected by the first two tiers.

Within a tier, candidate order may be randomized by the supplied RNG. A seeded RNG therefore keeps tests and controlled runs deterministic while still avoiding fixed option order.

The generator keeps the existing output contract: each generated question contains the correct entry, four answer options, and the correct option index. It returns `None` only when four distinct, non-empty options are genuinely impossible.

## Quality guards

The runtime generator rejects invalid option sets instead of silently creating weaker questions:

- no empty option text;
- no duplicate glossary entry in one question;
- no duplicate short definitions after normalized comparison;
- no current entry reused as a distractor;
- no downgrade to fewer than four answer options.

## Why `confusable_with` is product-facing metadata

`confusable_with` now directly controls which distractors learners see first. This makes it product-facing educational metadata rather than passive validation-only data. Curated relations should therefore be treated as part of glossary quiz quality: adding, removing, or changing them can affect question difficulty and pedagogical relevance.

## Limitations

This engine improves structural pedagogical relevance by using explicit same-topic glossary relationships before generic fallback. It does **not** certify that every relation is source-pack complete, semantically optimal, or reviewed by a subject-matter expert. Future source or SME review remains a separate optional quality layer.

## Coverage by topic

| Topic ID | Entries | Entries with direct confusables | Entries requiring Tier 3 fallback |
|---|---:|---:|---:|
| `vvedenie_v_professiyu` | 12 | 9 | 3 |
| `obschaya_psihologiya` | 12 | 6 | 6 |
| `fiziologiya_cheloveka` | 12 | 6 | 6 |
| `fiziologiya_vnd` | 12 | 5 | 7 |
| `psihofiziologiya` | 12 | 7 | 5 |
| `osnovy_eksperimentalnoy_psihologii` | 10 | 9 | 1 |
| `kachestvennye_metody_issledovaniya` | 14 | 11 | 3 |
| `psychological_consulting` | 12 | 7 | 5 |
