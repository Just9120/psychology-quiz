# AI Coding Workflow

## Purpose

This document defines the repository workflow for AI-assisted development.

It is a process contract, not a project specification and not an implementation guide.

The goal is to keep the repository self-contained enough for a human, reasoning model, or coding agent to understand:

- what the project is building;
- where current delivery state is tracked;
- which source should be trusted when files conflict;
- when documentation must be updated;
- what a focused AI-assisted PR is allowed to change.

Implementation details may evolve. The workflow should guide decisions without blocking reasonable model-assisted implementation.

Universal workflow documents define boundaries, not one rigid implementation style.

Reasoning models and coding agents may choose different valid approaches based on the actual repository context, as long as they preserve source priority, task scope, non-goals, safety boundaries, expected checks, and documentation update rules.

---

## Core principle

The repository is the source of truth after documentation is synchronized.

External chats, drafts, generated bundles, exports, old documents, historical notes, GitHub Issues, external trackers, and connector history may be used as supporting inputs, but they do not override current repository source-of-truth files.

GitHub Issues and connectors are not the primary backlog or delivery state for this workflow.

Current project state should be recoverable from repository source-of-truth documents, especially `docs/project-spec.md` and `docs/delivery-plan.md`.

Do not require a connector to understand ordinary project status.

---

## Standard repository document model

Recommended baseline repository documents:

```text
README.md
AGENTS.md
docs/project-spec.md
docs/delivery-plan.md
docs/ai-coding-workflow.md
```

Optional repository documents:

```text
docs/architecture.md
docs/ci-cd-rules.md
docs/runbooks/
docs/context-bundle-builder/MASTER_SPEC.md
docs/ai-delivery-infrastructure-plan.md
```

On-demand delivery-history archive path:

```text
docs/delivery-plan-archive.md
```

`docs/delivery-plan-archive.md` is not created as a baseline document. It is created only when a reasoning model prepares an explicit archival or reconciliation task for Codex to move old delivery history out of `docs/delivery-plan.md`.

Other optional files are used only when relevant.

This workflow does not define or require `docs/project-archive.md`.

---

## Source roles

| File | Role |
|---|---|
| `README.md` | Repository navigation, quickstart, and links to source documents. |
| `AGENTS.md` | Lightweight coding-agent routing rules. Read first. |
| `docs/project-spec.md` | Active product/project source of truth for humans and reasoning models; coding agents read only relevant sections when needed. |
| `docs/delivery-plan.md` | Active delivery source of truth: current state, active item, next item, near backlog, and blockers. |
| `docs/delivery-plan-archive.md` | Optional on-demand historical delivery archive. Created only by an explicit archival/reconciliation task. Not active delivery authority. |
| `docs/architecture.md` | Supporting architecture reference and component map. |
| `docs/ai-coding-workflow.md` | AI-assisted workflow rules. |
| `docs/ci-cd-rules.md` | CI/CD and deployment boundaries. Read only for CI/CD/deploy/operations tasks. |
| `docs/runbooks/*` | Opt-in operational, audit, evidence, rollout, maintenance, or troubleshooting detail. |
| `docs/context-bundle-builder/MASTER_SPEC.md` | Source of truth only for the Context Bundle Builder utility. |
| `docs/ai-delivery-infrastructure-plan.md` | Optional operational plan for AI workflow/tooling adoption when that workstream is large enough. |

---

## README contract

The root `README.md` should be the repository entrypoint and navigation layer.

It should include:

- short project description;
- current high-level status;
- minimal install/run/check commands;
- project structure;
- links to core documents;
- short contributor or coding-agent orientation.

It should not duplicate:

- the full project specification;
- the delivery plan;
- delivery history;
- architecture detail;
- CI/CD rules;
- operational runbooks;
- historical status chains.

If README content becomes long, move detail to the appropriate document and keep a link.

---

## Project specification contract

`docs/project-spec.md` is the active product/project source of truth.

It is used by:

- humans for product intent and durable decisions;
- reasoning models for broad context, audit, planning, decomposition, and focused task preparation;
- coding agents only when a task changes or depends on product scope, behavior, architecture, safety/runtime boundaries, data model, integrations, or acceptance criteria.

It should be a living current product contract, not a historical archive and not a Codex-only short checklist.

It should define:

- product goal;
- current active scope;
- out-of-scope boundaries;
- release/milestone/track boundaries;
- user roles or actors;
- domain entities and states;
- core scenarios/workflows;
- business rules;
- functional requirements;
- non-functional requirements;
- data/storage authority;
- integration boundaries;
- security, privacy, runtime, or safety constraints when relevant;
- acceptance/readiness criteria;
- open questions, blockers, and deferred/future scope;
- supporting-detail map.

It should not contain:

- long historical rationale;
- full old specs;
- old chats or generated bundles;
- detailed PR history;
- detailed delivery sequencing;
- giant evidence matrices;
- raw logs;
- large examples better suited to runbooks;
- obsolete decisions not relevant to current product behavior.

When detailed supporting material is needed, link to subordinate runbooks, design docs, architecture docs, CI/CD rules, or delivery documents.

Do not create a competing active product specification.

This workflow does not use `docs/project-archive.md` as a baseline place for old product history. Old product text should be removed from the active spec unless it still defines the current product contract.

Supporting documents must not silently expand active product scope beyond `docs/project-spec.md`.

---

## Delivery documentation model

`docs/project-spec.md` is primarily read by the reasoning model for analysis, source-of-truth reconciliation, task decomposition, and focused Codex task preparation.

`docs/delivery-plan.md` is read by both the reasoning model and Codex.

`docs/delivery-plan-archive.md` is created and maintained only through explicit archival or reconciliation tasks prepared by the reasoning model.

Codex must not create, read, or modify `docs/delivery-plan-archive.md` for ordinary focused tasks.

---

## Delivery plan contract

`docs/delivery-plan.md` shows the current operational delivery state.

It should define:

- current checkpoint or milestone;
- active item;
- last completed item or PR when useful for the current next step;
- next recommended item;
- near backlog;
- blocked/deferred/superseded notes that affect current or near work;
- open risks and blockers;
- validation notes for active/near items.

It should not duplicate the full project specification or become a complete historical journal.

Recommended top dashboard format:

```text
- ✅ <ID> — <item title> — Done / merged into main
- 👉 <ID> — <item title> — Current recommended next item
- 📋 <ID> — <item title> — Planned
- ⛔ <ID> — <item title> — Blocked: <reason>
```

Do not use standard Markdown task-list checkboxes (`[x]`, `[ ]`) for the top progress dashboard.

Historical checkpoints, old status chains, detailed PR history, old validation notes, and historical delivery narrative should be moved to `docs/delivery-plan-archive.md` only by an explicit archival or reconciliation task when they stop being operationally useful.

---

## Delivery plan archive contract

`docs/delivery-plan-archive.md` is an optional historical delivery archive.

It may be absent until old delivery history needs to be moved out of `docs/delivery-plan.md`.

It is created or updated by Codex only when a reasoning model prepares an explicit focused task for delivery-history archival, reconciliation, migration, or broad audit.

It may contain:

- old checkpoints;
- completed delivery phases that are no longer operationally useful;
- long PR/status chains;
- historical delivery narrative;
- old validation notes that are no longer needed for current or near work;
- superseded delivery sequencing.

It is not:

- the active delivery plan;
- the product/project specification;
- implementation authorization;
- a baseline repository document;
- a required document for ordinary focused tasks.

Coding agents must not create, read, or modify it unless the task explicitly asks for historical delivery review, delivery reconciliation, migration from old delivery history, or broad source-of-truth audit.

Archived delivery items do not authorize implementation by themselves.

When `docs/delivery-plan.md` becomes long because of old checkpoints, long PR notes, or historical status chains, a reasoning model should prepare a focused archival task for Codex to move that material to `docs/delivery-plan-archive.md` and keep only the current operational summary in `docs/delivery-plan.md`.

---

## Delivery item conventions

When the project uses tracked delivery items, each item should have:

- stable ID;
- status;
- scope;
- non-goals;
- acceptance criteria;
- validation notes;
- documentation update expectations.

Recommended minimal statuses:

```text
Backlog
Ready for Codex
In PR
Done
Blocked
Partially done
Deferred
Split
Superseded
Removed
```

Delivery item IDs are useful for PR links, Codex prompts, review comments, and handoff between chats or models.

When a PR addresses a tracked delivery item, the PR body should state the Delivery Item ID.

If the PR completes, changes, blocks, splits, supersedes, defers, or otherwise changes the state of that item, `docs/delivery-plan.md` should be updated in the same PR.

---

## Source priority

When sources conflict:

1. Current explicit user instruction.
2. `docs/project-spec.md` for product intent, requirements, business rules, durable constraints, and acceptance criteria.
3. `docs/delivery-plan.md` for current delivery state and active item.
4. `AGENTS.md` and `docs/ai-coding-workflow.md` for AI-assisted workflow and coding-agent behavior.
5. `docs/ci-cd-rules.md` for CI/CD and deployment boundaries.
6. Devtool specifications only for their own devtool scope.
7. `docs/architecture.md` as supporting architecture reference where it does not conflict with the product spec.
8. Current code/configuration as implementation evidence.
9. Tests and CI as verification evidence.
10. Runbooks, supporting docs, generated bundles, exports, old notes, and `docs/delivery-plan-archive.md`.

If sources conflict, report the drift. Do not silently choose code, tests, old notes, generated context, or delivery archive content over current requirements.

---

## Normal workflow

Normal flow:

```text
project-spec.md + delivery-plan.md
→ reasoning / planning
→ prepared focused task
→ Codex implementation PR
→ checks/review
→ documentation update when needed
→ merge
```

For normal focused PRs, the coding agent should not read every document.

It should follow `AGENTS.md`, rely on prepared task context when provided, and read only additional context relevant to the task.

---

## Two-stage AI-assisted workflow

AI-assisted work may use two different model roles:

```text
reasoning model / analyst
→ may inspect broader repository context
→ prepares a focused Codex task

Codex / coding agent
→ implements the focused task
→ reads only minimal additional context needed for the change
```

When a focused task is prepared by a reasoning model, the task prompt should include:

- one clear goal;
- delivery item ID, if applicable;
- relevant source-of-truth excerpts or section references;
- target files or likely file scope;
- explicit non-goals;
- expected checks;
- documentation update expectations;
- files or document areas not to read unless a conflict is detected.

Codex should treat the prepared task prompt as the primary working context.

Codex should not re-read full `docs/project-spec.md`, full `docs/delivery-plan.md`, `docs/delivery-plan-archive.md`, architecture docs, generated bundles, logs, or historical notes unless the task explicitly requires broad audit, migration, handoff, or source-of-truth reconciliation.

If Codex finds that the prepared task conflicts with repository source-of-truth files, it must report the conflict and keep the implementation scope narrow.

---

## Focused task rules

A focused task should have:

- one clear goal;
- limited file scope;
- explicit non-goals when risk exists;
- relevant source-of-truth references or excerpts;
- expected checks;
- documentation update expectations.

The coding agent should not expand the task into broad cleanup, architecture change, dependency upgrade, CI/CD change, generated-context rebuild, or unrelated backlog work unless explicitly requested.

Do not mix product delivery work, AI workflow/tooling work, CI/CD work, and Context Bundle Builder work in one PR unless the task explicitly scopes the mixed change and explains why it should not be split.

---

## PR body minimum

When a PR is prepared by a coding agent or completes a tracked delivery item, the PR body should include:

- summary of the requested change;
- Delivery Item ID, if applicable;
- validation/checks run, or why they were not run;
- documentation updates made, or why none were needed;
- project-spec impact: changed / unchanged / not applicable;
- risks, blockers, or remaining follow-up.

Keep the PR body concise. Do not duplicate the full specification, delivery plan, delivery archive, logs, or generated bundle content.

---

## PR review and merge check

Review PRs against:

```text
project-spec.md + delivery-plan.md + relevant workflow/CI/CD/runbook rules + diff + tests/CI
```

A PR is merge-ready only when:

- it stays within the selected task scope;
- non-goals are respected;
- acceptance criteria are met or remaining work is explicit;
- required documentation updates are included;
- validation was run or limitations are stated;
- there is no unrelated refactoring, hidden dependency, or unapproved scope change.

---

## Documentation update rules

Update `docs/delivery-plan.md` when a task:

- completes an item;
- changes item status;
- blocks, splits, cancels, or supersedes an item;
- creates a new tracked item;
- changes the current next recommended item.

Create or update `docs/delivery-plan-archive.md` only when:

- old delivery history is explicitly moved out of `docs/delivery-plan.md`;
- historical delivery state is reconciled;
- the task explicitly asks for delivery-history archive maintenance.

Do not create a placeholder `docs/delivery-plan-archive.md` during normal repository bootstrap.

Update `docs/project-spec.md` when a task intentionally changes:

- product scope;
- requirements;
- business rules;
- data/state model;
- user-facing behavior;
- integrations;
- durable constraints;
- acceptance criteria.

Update `docs/architecture.md` when a task intentionally changes:

- component boundaries;
- runtime model;
- deployment/runtime architecture;
- important data flow;
- integration shape;
- architectural constraints.

Update `docs/ci-cd-rules.md` only when CI/CD or deployment boundaries intentionally change.

Update `AGENTS.md` or this file only when workflow/coding-agent rules intentionally change.

Update `docs/ai-delivery-infrastructure-plan.md` only when that file exists and the task changes AI workflow/tooling adoption state, Context Bundle Builder delivery state, or related validation/evidence.

Do not rewrite docs casually as a side effect of code work.

---

## Large source-of-truth edit guardrail

Large source-of-truth documents, especially `docs/project-spec.md`, must not be fully rewritten, shortened, summarized, or regenerated unless the user explicitly requests that exact change.

When only a local requirement change is needed, use a targeted patch to the relevant section.

If safe direct editing is not possible, create a proposal file such as:

```text
docs/proposals/scope-update-<ITEM_ID>.md
```

The proposal should include:

- target document;
- target section;
- reason for change;
- related delivery item;
- exact proposed text;
- exact `diff` or `SEARCH / REPLACE` blocks when possible;
- non-goals and risks.

---

## Runbook boundary

Runbooks are subordinate supporting documents.

Use runbooks for:

- operational procedures;
- audit/evidence contracts;
- rollout checklists;
- troubleshooting;
- maintenance tasks;
- detailed verification matrices;
- implementation-specific handoff notes.

Runbooks must not silently expand active product scope beyond `docs/project-spec.md`.

Coding agents should read runbooks only when the task explicitly names the runbook or touches the exact surface covered by it.

---

## Context Bundle Builder boundary

Context Bundle Builder is optional and independent.

It may help collect repository context for audit, handoff, review, or planning.

It does not replace the workflow, project specification, delivery plan, PR review, tests, or CI.

Generated bundles and archives are context snapshots. They are not source of truth.

Codex should not read or modify `docs/context-bundle-builder/MASTER_SPEC.md` unless the task explicitly concerns the Context Bundle Builder utility.

When both AI Coding Workflow and Context Bundle Builder are present, changes to shared assumptions must be checked against both documents.

Shared assumptions include source-of-truth paths, baseline documents, generated bundle authority, source priority, analysis profiles/scenarios, split/chunk behavior, and Builder-related workflow expectations.

Normal product scope changes do not require Builder changes unless they affect context collection rules, repository structure, source-of-truth paths, safety exclusions, generated output contract, scenarios, presets, or profiles.

---

## CI/CD boundary

CI/CD rules live in `docs/ci-cd-rules.md`.

Read that file only when the task touches:

- GitHub Actions;
- CI;
- CD;
- deploy;
- Docker or Docker Compose deploy;
- server/VPS operations;
- runtime secrets;
- `.env`;
- Repository Secrets;
- post-check;
- rollback;
- databases, queues, caches, volumes, or other stateful services.

CI/CD implementation may evolve, but it must preserve the safety boundaries defined there.

---

## Data and storage boundary

For projects with persistent data, `docs/project-spec.md` should define:

- what data exists;
- canonical system of record;
- derived indexes/caches/vector stores;
- data that can be rebuilt;
- data that must not be lost;
- scaling or migration candidates when relevant.

Do not add a database, persistence layer, vector store, cache, queue, migration, backup, or stateful service as a side effect of an unrelated task.

For server/VPS projects, the repository should explicitly state whether Docker or Docker Compose is part of the intended runtime/deploy model.

Kubernetes is not a baseline requirement unless the project explicitly needs it.

For notebook, Colab, runtime-only, or managed-environment projects, Docker and VPS deploy are not required by default.

---

## New repository bootstrap

For a new repository, create only the minimal structure first:

```text
README.md
AGENTS.md
docs/project-spec.md
docs/delivery-plan.md
docs/ai-coding-workflow.md
docs/ci-cd-rules.md, if CI/CD or deploy is relevant
docs/context-bundle-builder/MASTER_SPEC.md, only if the utility is adopted
```

Do not create `docs/delivery-plan-archive.md` during repository bootstrap. Create it later only through an explicit reasoning-model-prepared archival task when old delivery checkpoints, long PR/status chains, or historical delivery narrative need to be retained outside the active delivery plan.

Placeholders are not source of truth. Missing content must be stated, not invented.

Create `docs/architecture.md`, runbooks, or `docs/ai-delivery-infrastructure-plan.md` only when there is enough real content or a meaningful workstream.

Do not create `docs/project-archive.md` as a baseline workflow document.

---

## Done means

A workflow-compliant task is done when:

- the requested scope is implemented;
- unrelated scope was not added;
- relevant checks were run or limitations were stated;
- source conflicts or risky assumptions were reported;
- required docs were updated only when applicable;
- the final response explains changed files, validation, and remaining risks.
