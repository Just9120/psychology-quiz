# AGENTS.md

## Purpose

This file is the lightweight operating guide for coding agents in this repository.

It tells the agent what context to read, what to avoid, how to keep changes focused, and when documentation must be updated.

This file is not the project specification, not the delivery plan, not an implementation guide, and not a replacement for repository documentation.

Keep this file short. Put detailed product, delivery, CI/CD, architecture, runbook, or devtool rules in the referenced documents.

---

## Default behavior

For normal focused tasks:

1. Read this `AGENTS.md` first.
2. Treat the user task or prepared task prompt as the primary working context.
3. Before opening additional documentation, decide the minimal context needed.
4. Read only the files and sections relevant to the requested change.
5. Inspect only code, tests, configuration, and docs directly related to the task.
6. Make the smallest safe change that satisfies the task.
7. Run relevant existing checks when available.
8. Report what changed, what was checked, and what was not checked.

Do not perform broad audits, large refactors, dependency upgrades, architecture changes, cleanup, CI/CD changes, deployment changes, or documentation rewrites unless explicitly requested.

---

## Repository documents

Typical repository documents:

| File | Role |
|---|---|
| `README.md` | Repository entrypoint and navigation. |
| `AGENTS.md` | Lightweight coding-agent routing rules. Read first. |
| `docs/project-spec.md` | Active product/project source of truth. |
| `docs/delivery-plan.md` | Active delivery state, active item, next item, blockers, and near backlog. |
| `docs/delivery-plan-archive.md` | Optional on-demand delivery-history archive. Created only by an explicit archival/reconciliation task. Not active source of truth. |
| `docs/architecture.md` | Supporting architecture reference and component map. |
| `docs/ai-coding-workflow.md` | AI-assisted development workflow rules. |
| `docs/ci-cd-rules.md` | CI/CD and deployment safety boundaries. |
| `docs/runbooks/*` | Opt-in operational, audit, evidence, rollout, maintenance, or troubleshooting detail. |
| `docs/context-bundle-builder/MASTER_SPEC.md` | Source of truth only for the Context Bundle Builder utility. |
| `docs/ai-delivery-infrastructure-plan.md` | Optional plan for AI delivery infrastructure/tooling workstreams. |

If a referenced document is missing, do not invent its content. State the limitation and continue only with available evidence.

This workflow does not use `docs/project-archive.md` as a baseline repository document.

---

## Project specification reading rule

`docs/project-spec.md` is the active product/project source of truth for humans and reasoning models.

For coding agents, it is a source to consult only when needed. For ordinary focused implementation tasks, do not read the full file by default.

Read only the relevant sections of `docs/project-spec.md` when the task changes or depends on:

- product scope;
- new feature behavior;
- business rules;
- user-facing behavior;
- architecture;
- data/state model;
- integrations;
- runtime authority;
- safety, security, risk, or execution boundaries;
- acceptance criteria;
- source-of-truth conflict resolution.

When a reasoning model provides relevant excerpts from `docs/project-spec.md` in the task prompt, treat those excerpts as the primary working context. Open the full file only if the excerpt is insufficient, stale, contradictory, or the task explicitly requires broader source-of-truth reconciliation.

Future or deferred sections do not authorize implementation by themselves. Active implementation scope must come from the current user task and, when applicable, `docs/delivery-plan.md`.

---

## Delivery plan reading rule

Use `docs/delivery-plan.md` to determine:

- the current checkpoint or milestone;
- the active delivery item;
- the next recommended item;
- current blockers;
- near backlog;
- item-specific acceptance criteria and validation notes.

For implementation tasks, update `docs/delivery-plan.md` only when the task changes delivery state, completes an item, blocks an item, splits an item, cancels an item, supersedes an item, changes the current next recommended item, or creates a new tracked item.

Do not turn `docs/delivery-plan.md` into a historical journal. Historical checkpoints, old PR notes, long status chains, and old delivery narrative should be moved to `docs/delivery-plan-archive.md` only when an explicit archival or reconciliation task asks for it.

---

## Delivery archive and runbook boundary

`docs/delivery-plan-archive.md` is optional historical delivery context.

It may be absent in a repository until a reasoning model prepares an explicit task to archive old delivery history from `docs/delivery-plan.md`.

Coding agents must not create, read, or modify `docs/delivery-plan-archive.md` for ordinary focused tasks.

Create, read, or modify `docs/delivery-plan-archive.md` only when the task explicitly asks for historical delivery review, delivery reconciliation, migration from old delivery history, or broad source-of-truth audit.

Archived delivery items do not authorize implementation by themselves.

`docs/runbooks/*` are opt-in detail documents.

Do not read runbooks unless the task explicitly names a runbook or touches the exact operational, audit, evidence, rollout, troubleshooting, or maintenance surface covered by that runbook.

Runbooks and delivery archives must not silently expand active product scope beyond `docs/project-spec.md` and `docs/delivery-plan.md`.

---

## Prepared task context

When the user prompt already provides a focused task, delivery item ID, relevant source excerpts, target files, non-goals, and expected checks, treat that prompt as the primary working context.

Use repository documents only to resolve specific uncertainty:

- read `docs/delivery-plan.md` only to verify or update the referenced delivery item;
- read relevant sections of `docs/project-spec.md` only when product scope, behavior, architecture, safety, data, integrations, or acceptance criteria are affected;
- read or create `docs/delivery-plan-archive.md` only when the task explicitly requires historical delivery archival or reconciliation;
- read `docs/ai-coding-workflow.md` only for workflow, PR process, documentation-rule, or AI delivery setup tasks;
- read `docs/ci-cd-rules.md` only for CI/CD, deploy, Docker, VPS/server, secrets, runtime environment, rollback, or stateful-service tasks;
- read `docs/context-bundle-builder/MASTER_SPEC.md` only for Context Bundle Builder tasks.

Do not re-read full repository documentation just because it exists.

---

## Broad audit and planning tasks

For broad audit, handoff, docs-vs-code audit, architecture review, release review, migration, or source-of-truth reconciliation:

- read the relevant source-of-truth documents;
- preserve source priority;
- report docs/code/test drift clearly;
- distinguish facts from assumptions and recommendations;
- do not turn findings into implementation unless explicitly requested.

---

## Source priority

When sources conflict, use this priority:

1. Explicit user request in the current task.
2. `docs/project-spec.md` for product scope, requirements, business rules, durable constraints, and acceptance criteria.
3. `docs/delivery-plan.md` for current delivery state and active work.
4. `AGENTS.md` and `docs/ai-coding-workflow.md` for AI-assisted workflow and coding-agent rules.
5. `docs/ci-cd-rules.md` for CI/CD and deployment boundaries.
6. Devtool specifications only for their own devtool scope.
7. `docs/architecture.md` as supporting architecture reference where it does not conflict with the product spec.
8. Current code/configuration as evidence of actual behavior.
9. Tests and CI as verification evidence.
10. Runbooks, supporting docs, generated bundles, exports, old notes, and `docs/delivery-plan-archive.md`.

If requirements, architecture, code, and tests conflict, report the conflict. Do not silently rewrite requirements or architecture to match current code or historical notes.

---

## Documentation update rules

Update `docs/delivery-plan.md` only when delivery state changes.

Create or update `docs/delivery-plan-archive.md` only when explicitly moving old delivery history out of `docs/delivery-plan.md`, reconciling historical delivery state, or performing a broad delivery-history audit.

Update `docs/project-spec.md` only when the task intentionally changes product scope, business logic, requirements, constraints, data model, integrations, acceptance criteria, or intended behavior.

Update `docs/architecture.md` only when the task intentionally changes architecture, component boundaries, runtime model, or important implementation structure.

Update `docs/ci-cd-rules.md` only when CI/CD or deployment rules intentionally change.

Update `docs/ai-coding-workflow.md` or this `AGENTS.md` only when the task explicitly concerns workflow, coding-agent behavior, or AI delivery infrastructure.

Update `docs/ai-delivery-infrastructure-plan.md` only when that file exists and the task changes AI workflow/tooling adoption state, Context Bundle Builder delivery state, or related validation/evidence.

Do not casually rewrite documentation as a side effect of code work.

---

## AGENTS.md edit policy

Do not edit this file during ordinary product/code tasks.

Edit this file only when:

- the user explicitly asks to update coding-agent instructions;
- the task is specifically about repository workflow or AI delivery setup;
- repeated agent mistakes need durable routing guidance;
- a repository-specific command, path, or rule changed and the user asked to persist it.

Keep this file compact. If a rule becomes long, move details to a referenced document and keep only the routing rule here.

---

## CI/CD and deployment safety

Do not modify CI/CD, Docker, deploy scripts, server/VPS configuration, secrets, `.env`, stateful services, database migrations, backups, restores, or rollback logic unless explicitly requested.

For CI/CD or deployment tasks, read `docs/ci-cd-rules.md` before making changes.

Never print secret values.

Never add real secrets to code, docs, logs, prompts, tests, examples, generated bundles, or archives.

Standard CI must not deploy.

Standard CD must not perform cleanup, hardening, destructive commands, database maintenance, volume changes, or stateful service recreation unless this is a separate explicit maintenance task.

---

## Implementation boundaries

Do not:

- implement unrelated backlog items;
- expand scope without explicit approval;
- perform broad refactors unless requested;
- add production dependencies without justification;
- change architecture as a side effect of a local fix;
- rewrite working code only for style;
- remove backward compatibility unless requested;
- change public behavior without checking relevant requirements;
- treat generated files, delivery archives, logs, or old notes as source of truth;
- introduce persistence, queues, caches, migrations, or external services as a side effect of unrelated work.

Prefer small, focused, reviewable changes.

---

## Repository-specific commands

Use existing project commands where available.

```text
Install:
Lint:
Typecheck:
Test:
Build:
Run:
```

If commands are unknown, inspect package/config files and use the smallest relevant checks.

If checks cannot be run, explain why.

Do not introduce heavy testing infrastructure unless explicitly requested.

---

## Done means

A task is done when:

- the requested focused change is implemented;
- the change stays within scope;
- relevant checks were run or limitations are stated;
- risky assumptions and source conflicts are called out;
- required documentation updates were made only when applicable;
- the final response explains changed files, validation, and remaining risks.
