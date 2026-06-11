# CI/CD Rules

## Purpose

This document defines CI/CD boundaries for repositories that use GitHub Actions, deploy automation, Docker, server/VPS deploy, runtime secrets, or stateful services.

It is a safety and responsibility contract, not a detailed implementation recipe.

Project-specific implementation may evolve, but it must preserve the boundaries below.

---

## Core principle

CI verifies the project.

CD delivers the project.

CI must not deploy.

CD must not perform cleanup, hardening, destructive operations, uncontrolled migrations, backup/restore, or stateful service maintenance unless this is an explicit separate maintenance task.

---

## Scope

This document applies when a task touches:

- GitHub Actions;
- CI workflows;
- CD workflows;
- deploy scripts;
- server/VPS deploy;
- Docker or Docker Compose deploy;
- runtime `.env`;
- Repository Secrets;
- post-checks;
- rollback;
- databases, Redis, queues, vector databases, object/file storage, volumes, or other stateful services.

For ordinary product/code tasks, do not read or apply this document unless CI/CD, deployment, operations, runtime environment, or stateful infrastructure is affected.

---

## Required project inputs

Before preparing or changing CI/CD, determine the relevant values from the repository or safe diagnostics.

Do not invent unknown values.

Minimum CI inputs:

- repository;
- production branch;
- stack and package manager;
- install command;
- lint command, if available;
- typecheck command, if available;
- test command, if available;
- build command, if available;
- lockfile presence;
- existing workflows.

Additional CD inputs:

- target environment;
- deploy branch;
- deploy directory, for example `APP_DIR`;
- expected remote, for example `EXPECTED_REMOTE`;
- expected branch, for example `EXPECTED_BRANCH`;
- target service, for example `COMPOSE_SERVICE`;
- deploy command/model;
- runtime env model;
- health check or post-check;
- secrets required by the workflow, usually `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`;
- stateful services and volumes;
- rollback expectation, if any.

If values are unknown, ask for them or provide safe read-only diagnostic commands.

---

## CI boundaries

CI should:

- run on `pull_request`;
- run on `push` to the production branch, usually `main`;
- support `workflow_dispatch`;
- use minimal `permissions`;
- use a `concurrency` guard;
- use existing project commands;
- use lockfiles when present;
- install dependencies reproducibly where possible;
- run available checks;
- avoid production secrets;
- avoid production infrastructure;
- not deploy;
- clearly report success, for example with `CI_OK`.

If the project has no tests, CI may run the smallest available useful checks.

Do not introduce heavy testing infrastructure as part of a CI setup unless explicitly requested.

Do not add auto-fix commits, direct pushes to the production branch, or self-modifying workflow behavior unless explicitly requested and reviewed as a separate automation policy.

---

## CD boundaries

CD should:

- run only on intended production delivery events or `workflow_dispatch`;
- use minimal `permissions`;
- use a `concurrency` guard;
- use Repository Secrets without printing values;
- explicitly verify target directory, branch, remote, and service identity before deploy;
- fail safely when required inputs are missing;
- refuse deploy when local tracked changes make update unsafe;
- update code safely, preferably by fast-forward when using git-based deploy;
- preserve existing runtime secrets;
- block deploy when required runtime secrets are unresolved;
- deploy only the intended application service;
- run a post-check;
- report success, for example `DEPLOY_OK`, only after post-check passes.

CD implementation details may differ by project. The safety boundaries above must remain intact.

For git-based server/VPS deploy, the expected repository access model must be explicit.

Prefer SSH-based repository access on the target server when that is the established project model. Do not introduce HTTPS/PAT-based deploy access unless explicitly requested.

Initial server bootstrap, SSH/server hardening, deploy-user setup, firewall changes, directory migration, and production cleanup are not standard CD.

They require a separate explicit setup, maintenance, or migration task with scope, validation, and rollback expectations.

Do not hide bootstrap or hardening inside an ordinary CD workflow change.

---

## Secrets and `.env`

Secrets must not be committed, printed, logged, copied into prompts, copied into generated bundles, exposed in examples, or written into tests.

`.env.example`, `.env.sample`, or `.env.template` may describe required runtime variables.

Runtime `.env` values must be preserved.

If `.env.example` is used as a runtime schema, CD should safely add missing keys to runtime `.env` without overwriting existing values.

After safe `.env.example` to runtime `.env` sync, deploy scripts must check runtime `.env` for unresolved required placeholders and block deployment with a non-zero exit code before `docker build`, `docker compose up`, restart, migration, or any action that touches the target service.

Use placeholders such as `__REQUIRED_SECRET__` only as schema markers, not as real values.

Do not print or validate runtime secrets with unsafe commands such as `cat .env`, `docker compose config`, or any command that can expose resolved secret values.

---

## Stateful services

Stateful services include:

- databases;
- Redis;
- queues;
- vector databases;
- object/file storage;
- persistent volumes;
- any service that owns data that cannot be casually recreated.

Standard CD must not:

- delete or recreate stateful services;
- remove volumes;
- run destructive migrations;
- run backup/restore;
- reindex vector databases;
- move persistent data;
- perform cleanup that can affect state.

Any stateful service work must be a separate explicit maintenance or migration task with scope, validation, and rollback expectations.

---

## Forbidden by default

Do not add these to standard CI/CD unless an explicit separate maintenance task justifies them:

- deploy from CI;
- production SSH from CI;
- printing secret values;
- destructive file deletion;
- broad cleanup;
- `rm -rf` cleanup against broad or variable paths;
- `git reset --hard`;
- `git clean -fdx`;
- destructive Docker prune/down operations such as `docker compose down`, `docker system prune -a`, `docker volume prune`, or `docker image prune -a`;
- deleting or recreating volumes;
- printing or validating secrets by unsafe commands such as `cat .env`;
- using `docker compose config` when it can expose resolved secrets;
- changing ownership or permissions recursively with broad `chmod -R` or `chown -R`;
- uncontrolled database migrations;
- backup/restore;
- vector reindex;
- moving production directories;
- changing production `.env` values;
- CI auto-fix commits;
- direct pushes to the production branch from automation;
- workflow self-modification without explicit request and review.

---

## Rollback boundary

Automatic rollback is allowed only when the project has an explicit, safe, documented rollback strategy.

If rollback is not clearly safe, CD should fail loudly after failed post-check and avoid destructive recovery attempts.

Rollback must not violate stateful service boundaries.

Rollback must not delete or recreate persistent data unless the maintenance task explicitly scopes that action and includes validation and recovery expectations.

---

## Deploy Key vs Repository Secrets

Do not confuse:

```text
Deploy Key = target server access to the GitHub repository
DEPLOY_* Repository Secrets = GitHub Actions access to the target server
```

Use the model that matches the project. Do not invent access details.

---

## Environment and branch identity

CD must verify that it is deploying the intended repository, branch, directory, and service before changing runtime state.

Recommended checks for git-based deploy:

- current directory matches expected deploy directory;
- configured remote matches expected repository;
- current branch matches expected deploy branch;
- working tree has no unsafe local tracked changes;
- target service name matches configured service;
- required runtime files exist;
- required runtime placeholders are resolved.

If any identity check fails, deployment must stop before build/restart/up.

---

## Codex task boundary

For CI/CD tasks, Codex may create or update workflow files and supporting scripts only within the requested scope.

Codex must not:

- add real secrets;
- change unrelated application behavior;
- change architecture;
- touch stateful services;
- add migrations or backup/restore;
- perform cleanup/hardening;
- expand CI/CD beyond the requested task;
- introduce a new deploy access model without explicit request;
- convert local/dev Docker usage into production deployment semantics unless explicitly scoped.

---

## Done means

CI is done when:

- it runs on `pull_request`;
- it runs on `push` to the production branch;
- `workflow_dispatch` is available;
- minimal `permissions` and a `concurrency` guard are present;
- it uses existing project checks;
- it avoids deploy and production secrets;
- it passes with a clear success marker such as `CI_OK` or reports clear missing project prerequisites.

CD is done when:

- it deploys only the intended target service;
- target directory, expected remote, expected branch, and service identity are explicit;
- required secrets and runtime env are handled safely;
- unresolved required runtime secrets block deploy before build/up/restart;
- stateful services and volumes are not touched;
- post-check is present;
- failed post-check cannot produce a success marker such as `DEPLOY_OK`;
- success is reported only after validation;
- rollback behavior is explicit or safely absent.
