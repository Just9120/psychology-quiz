#!/usr/bin/env bash
set -Eeuo pipefail

LOCK_FILE="/tmp/psychology-quiz-deploy.lock"
exec 200>"${LOCK_FILE}"
flock -n 200 || {
  echo "[deploy] Another deployment is already running. Exiting."
  exit 0
}

PROJECT_DIR="${PROJECT_DIR:-/opt/psychology-quiz}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-psych_quiz_bot}"

log() {
  echo "[deploy] $*"
}

fail() {
  echo "[deploy] ERROR: $*" >&2
  exit 1
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "${value}"
}

require_file() {
  local path="$1"
  [[ -f "${path}" ]] || fail "Required file is missing: ${path}"
  log "Required file present: ${path}"
}

current_branch() {
  git branch --show-current
}

ensure_expected_directory() {
  local actual_dir
  local expected_dir

  actual_dir="$(pwd -P)"
  expected_dir="$(cd "${PROJECT_DIR}" && pwd -P)"

  [[ "${actual_dir}" == "${expected_dir}" ]] || fail "Current directory does not match the expected deploy directory."
  log "Deploy directory check passed."
}

ensure_git_worktree() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "Deploy directory is not a git worktree."
  log "Git worktree check passed."
}

ensure_expected_branch() {
  local branch
  branch="$(current_branch)"
  [[ "${branch}" == "${DEPLOY_BRANCH}" ]] || fail "Current branch must be ${DEPLOY_BRANCH}."
  log "Branch check passed: ${DEPLOY_BRANCH}"
}

ensure_safe_service_name() {
  [[ "${SERVICE_NAME}" =~ ^[A-Za-z0-9_.-]+$ ]] || fail "Configured service name contains unsupported characters."
}

ensure_service_identity() {
  ensure_safe_service_name
  local raw_line=""
  local trimmed_line=""
  local service_key=""

  while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
    trimmed_line="$(trim "${raw_line}")"
    [[ "${trimmed_line}" == *":"* ]] || continue
    service_key="$(trim "${trimmed_line%%:*}")"
    if [[ "${service_key}" == "${SERVICE_NAME}" ]]; then
      log "Service identity check passed: ${SERVICE_NAME}"
      return 0
    fi
  done < docker-compose.yml

  fail "Expected service is not present in docker-compose.yml."
}

ensure_required_runtime_files() {
  require_file ".env"
  require_file ".env.example"
  require_file "docker-compose.yml"
}

ensure_remote_identity() {
  local actual_remote

  actual_remote="$(git remote get-url origin)" || fail "Unable to read origin remote."

  if [[ -n "${EXPECTED_REMOTE:-}" ]]; then
    [[ "${actual_remote}" == "${EXPECTED_REMOTE}" ]] || fail "Origin remote does not match EXPECTED_REMOTE."
    log "Remote identity check passed."
  else
    log "Remote identity pinning skipped because EXPECTED_REMOTE is not set."
  fi
}

ensure_no_local_tracked_changes() {
  git diff --quiet || fail "Local tracked changes are present; refusing to deploy."
  git diff --cached --quiet || fail "Local staged changes are present; refusing to deploy."
  log "Local tracked/staged change check passed."
}

sync_missing_env_keys() {
  log "Syncing missing .env keys from .env.example"
  local env_backup_created=0
  local env_backup_path=""
  local raw_line=""
  local trimmed_line=""
  local raw_key=""
  local key=""

  while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
    trimmed_line="$(trim "${raw_line}")"
    [[ -z "${trimmed_line}" ]] && continue
    [[ "${trimmed_line}" == \#* ]] && continue
    [[ "${raw_line}" != *"="* ]] && continue

    raw_key="${raw_line%%=*}"
    key="$(trim "${raw_key}")"

    if [[ ! "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      log "Warning: skipped invalid env key: ${key}"
      continue
    fi

    if grep -qE "^[[:space:]]*${key}[[:space:]]*=" ".env"; then
      continue
    fi

    if [[ "${env_backup_created}" -eq 0 ]]; then
      env_backup_path=".env.backup.$(date +%Y%m%d%H%M%S)"
      cp ".env" "${env_backup_path}"
      log "Backed up .env before adding missing keys."
      env_backup_created=1
    fi

    printf '%s\n' "${raw_line}" >> ".env"
    log "Added missing env key: ${key}"
  done < ".env.example"
}

env_value() {
  local target_key="$1"
  local raw_line=""
  local trimmed_line=""
  local raw_key=""
  local key=""
  local raw_value=""
  local value=""

  while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
    raw_line="${raw_line%$'\r'}"
    trimmed_line="$(trim "${raw_line}")"
    [[ -z "${trimmed_line}" ]] && continue
    [[ "${trimmed_line}" == \#* ]] && continue
    [[ "${raw_line}" != *"="* ]] && continue

    raw_key="${raw_line%%=*}"
    key="$(trim "${raw_key}")"
    [[ "${key}" == "${target_key}" ]] || continue

    raw_value="${raw_line#*=}"
    value="$(trim "${raw_value}")"
    if [[ "${#value}" -ge 2 ]]; then
      if [[ "${value:0:1}" == '"' && "${value: -1}" == '"' ]]; then
        value="${value:1:${#value}-2}"
      elif [[ "${value:0:1}" == "'" && "${value: -1}" == "'" ]]; then
        value="${value:1:${#value}-2}"
      fi
    fi
    printf '%s' "${value}"
    return 0
  done < ".env"

  return 1
}

require_env_value() {
  local key="$1"
  local value=""

  value="$(env_value "${key}" || true)"
  [[ -n "${value}" ]] || fail "Required runtime env value is missing or empty: ${key}"
  log "Required runtime env check passed: ${key}"
}

validate_runtime_env() {
  if grep -q "__REQUIRED_SECRET__" ".env"; then
    fail "Unresolved required secret placeholder found in .env."
  fi
  log "Required secret placeholder check passed."

  require_env_value "BOT_TOKEN"

  local update_mode=""
  update_mode="$(env_value "TELEGRAM_UPDATE_MODE" || true)"
  if [[ "${update_mode}" == "webhook" ]]; then
    require_env_value "TELEGRAM_WEBHOOK_URL"
    require_env_value "TELEGRAM_WEBHOOK_LISTEN"
    require_env_value "TELEGRAM_WEBHOOK_PORT"
    require_env_value "TELEGRAM_WEBHOOK_SECRET_TOKEN"
  else
    log "Webhook env checks skipped because TELEGRAM_UPDATE_MODE is not webhook."
  fi
}

post_check() {
  if [[ "${NEEDS_RESTART}" -eq 1 ]]; then
    log "Running post-check for ${SERVICE_NAME} container state."
    local container_id=""
    container_id="$(docker compose ps -q "${SERVICE_NAME}")"
    [[ -n "${container_id}" ]] || fail "Post-check failed: expected service container was not found."
    [[ "$(docker inspect -f '{{.State.Running}}' "${container_id}")" == "true" ]] \
      || fail "Post-check failed: expected service container is not running."
    log "Post-check passed: ${SERVICE_NAME} container is running."
  else
    log "No restart post-check required because restart was not needed."
  fi
}

[[ -d "${PROJECT_DIR}" ]] || fail "Deploy directory does not exist."
cd "${PROJECT_DIR}"

ensure_expected_directory
ensure_git_worktree
ensure_expected_branch
ensure_remote_identity
ensure_no_local_tracked_changes

OLD_HEAD="$(git rev-parse HEAD)"
log "old head: ${OLD_HEAD}"

log "Fetching origin ${DEPLOY_BRANCH}"
git fetch origin "${DEPLOY_BRANCH}" || fail "Unable to fetch expected deploy branch from origin."

log "Updating by fast-forward only."
git merge --ff-only "origin/${DEPLOY_BRANCH}" || fail "Fast-forward update failed; refusing unsafe deploy."

NEW_HEAD="$(git rev-parse HEAD)"
log "new head: ${NEW_HEAD}"

ensure_expected_directory
ensure_expected_branch
ensure_required_runtime_files
ensure_service_identity
sync_missing_env_keys
validate_runtime_env

CHANGED_FILES="$(git diff --name-only "${OLD_HEAD}" "${NEW_HEAD}")"
log "changed files:"
if [[ -n "${CHANGED_FILES}" ]]; then
  printf '%s\n' "${CHANGED_FILES}"
else
  echo "(none)"
fi

NEEDS_BUILD=0
NEEDS_RESTART=0
NEEDS_SEED=0

while IFS= read -r file; do
  [[ -z "${file}" ]] && continue

  case "${file}" in
    Dockerfile|docker-compose.yml|requirements.txt|app/*|scripts/*|sql/*)
      NEEDS_BUILD=1
      ;;
  esac

  case "${file}" in
    Dockerfile|docker-compose.yml|requirements.txt|app/*)
      NEEDS_RESTART=1
      ;;
  esac

  case "${file}" in
    content/*|scripts/seed_questions.py|app/db.py|sql/*)
      NEEDS_SEED=1
      ;;
  esac
done <<< "${CHANGED_FILES}"

log "needs build: ${NEEDS_BUILD}"
log "needs seed: ${NEEDS_SEED}"
log "needs restart: ${NEEDS_RESTART}"

if [[ "${NEEDS_BUILD}" -eq 1 ]]; then
  log "Running build for ${SERVICE_NAME}"
  docker compose build "${SERVICE_NAME}"
else
  log "Skipping build"
fi

if [[ "${NEEDS_SEED}" -eq 1 ]]; then
  log "Initializing DB schema before seed"
  docker compose run --rm "${SERVICE_NAME}" python scripts/init_db.py
  log "Running seed"
  docker compose run --rm "${SERVICE_NAME}" python scripts/seed_questions.py
else
  log "Skipping seed"
fi

if [[ "${NEEDS_RESTART}" -eq 1 ]]; then
  log "Restarting ${SERVICE_NAME}"
  docker compose up -d --force-recreate "${SERVICE_NAME}"
else
  log "Skipping restart"
fi

post_check
log "Completed successfully"
echo "DEPLOY_OK"
