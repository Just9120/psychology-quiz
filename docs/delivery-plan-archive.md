# Delivery Plan Archive

## Purpose

This file stores historical delivery checkpoints and completed PR groups that no longer need to live in the active delivery plan.

It is not active delivery authority. Current active delivery state remains in `docs/delivery-plan.md`, and archived items do not authorize new implementation by themselves.

## Archived completed PRs

### Operational diagnostics and classic reply keyboard baseline (#199–#204)

- #199: webhook/logging/security cleanup and safer operational diagnostics.
- #200: classic inline callback diagnostics for update ingress and callback latency investigation.
- #201: Mini App telemetry for answer/setup state, retries, and safe diagnostics.
- #202: Mini App production diagnostics/operational follow-up for stalled answer reports.
- #203: Mini App hedge mitigation for answer stalls, reducing hedged-case wait time.
- #204: classic reply keyboard mode for `/quiz`, moving answer/`Далее` controls to bottom Telegram reply keyboard text updates.

### UX polish loop (#207–#211)

- #207: main menu, `/start`, `/help`, `/ping`, and `/ui` UX cleanup.
- #208: Reading Mode UX polish.
- #209: classic chat quiz feedback and final screen polish.
- #210: Mini App P1 UX polish for setup/question/result flow.
- #211: Mini App P2 visual cleanup for product-facing setup/result screens.

Completed outcome:
- Classic `/quiz` with reply keyboard mode remained stable after the polish loop.
- UX-polish smoke passed with no current bugs reported after manual Telegram/Mini App checks.
- Mini App opt-in flow gained product-facing setup, question, and result screens after P1/P2 polish.


### Learning contours, Mini App glossary, contour entrypoint, and CD service-set fixes

- LEARN-CONTOURS-PHASE1-001 follow-up: docs-only topic registry/schema validation proposal.
- LEARN-CONTOURS-PHASE1B-001: static `content/topics.json` registry and `scripts/validate_topics.py`.
- LEARN-CONTOURS-CI-001: CI validation for topic registry.
- LEARN-CONTOURS-LITERATURE-MVP-001: first static literature reading-tracker scaffold and validator.
- LEARN-CONTOURS-LITERATURE-CI-001: CI validation for literature scaffold.
- LEARN-CONTOURS-GLOSSARY-MVP-001 and LEARN-CONTOURS-GLOSSARY-BATCH2-001: first static glossary content batches.
- LEARN-CONTOURS-GLOSSARY-CI-001: CI validation for glossary content.
- LEARN-CONTOURS-GLOSSARY-RUNTIME-MVP-001: read-only Telegram chat glossary MVP backed by static glossary JSON.
- LEARN-CONTOURS-GLOSSARY-QUIZ-MVP-001: Telegram glossary converted to quiz mode.
- LEARN-CONTOURS-GLOSSARY-V2-EXPERIMENTAL-PSYCHOLOGY-001: second glossary topic and chat quiz UX alignment.
- LEARN-CONTOURS-GLOSSARY-MINIAPP-MVP-001: Mini App glossary quiz contour.
- LEARN-CONTOURS-GLOSSARY-MINIAPP-OPEN-HOTFIX-001, SETUP-FALLBACK-HOTFIX-001, EXISTING-ENDPOINTS-HOTFIX-001, CONTEXT-HOTFIX-001, and START-HOTFIX-001: production hotfix chain that made Mini App glossary open/start reliably through existing Mini App endpoints while keeping source_refs internal.
- INFRA-CD-MINIAPP-API-DEPLOY-001: production CD/deploy rebuilds and recreates the runtime service set `psych_quiz_bot` + `psych_quiz_miniapp_api`.
- MINIAPP-CONTOUR-ENTRYPOINT-RESTORE-001: `/ui` and `🚀 В окне` restored as setup/contour chooser entrypoints even when a normal quiz runner is active.
