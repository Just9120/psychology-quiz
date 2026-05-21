#!/usr/bin/env bash
set -Eeuo pipefail

LOCK_FILE="/tmp/psychology-quiz-deploy.lock"
exec 200>"${LOCK_FILE}"
flock -n 200 || {
  echo "[deploy] Another deployment is already running. Exiting."
  exit 0
}

PROJECT_DIR="/opt/psychology-quiz"
SERVICE_NAME="psych_quiz_bot"

cd "${PROJECT_DIR}"

OLD_HEAD="$(git rev-parse HEAD)"
echo "[deploy] old head: ${OLD_HEAD}"

git fetch origin main

git reset --hard origin/main

NEW_HEAD="$(git rev-parse HEAD)"
echo "[deploy] new head: ${NEW_HEAD}"

if [[ -f ".env.example" ]]; then
  if [[ -f ".env" ]]; then
    echo "[deploy] Syncing missing .env keys from .env.example"
    env_backup_created=0

    while IFS= read -r raw_line || [[ -n "${raw_line}" ]]; do
      trimmed_line="$(printf '%s' "${raw_line}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
      [[ -z "${trimmed_line}" ]] && continue
      [[ "${trimmed_line}" == \#* ]] && continue
      [[ "${raw_line}" != *"="* ]] && continue

      raw_key="${raw_line%%=*}"
      key="$(printf '%s' "${raw_key}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

      if [[ ! "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        echo "[deploy] Warning: skipped invalid env key: ${key}"
        continue
      fi

      if grep -qE "^${key}=" ".env"; then
        continue
      fi

      if [[ "${env_backup_created}" -eq 0 ]]; then
        env_backup_path=".env.backup.$(date +%Y%m%d%H%M%S)"
        cp ".env" "${env_backup_path}"
        echo "[deploy] Backed up .env to ${env_backup_path}"
        env_backup_created=1
      fi

      printf '%s\n' "${raw_line}" >> ".env"
      echo "[deploy] Added missing env key: ${key}"
    done < ".env.example"
  else
    echo "[deploy] Warning: .env is missing; env sync skipped"
  fi
else
  echo "[deploy] .env.example is missing; env sync skipped"
fi

if [[ "${OLD_HEAD}" == "${NEW_HEAD}" ]]; then
  echo "[deploy] No new commits. Nothing to do."
  exit 0
fi

CHANGED_FILES="$(git diff --name-only "${OLD_HEAD}" "${NEW_HEAD}")"
echo "[deploy] changed files:"
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

echo "[deploy] needs build: ${NEEDS_BUILD}"
echo "[deploy] needs seed: ${NEEDS_SEED}"
echo "[deploy] needs restart: ${NEEDS_RESTART}"

if [[ "${NEEDS_BUILD}" -eq 1 ]]; then
  echo "[deploy] Running build for ${SERVICE_NAME}"
  docker compose build "${SERVICE_NAME}"
else
  echo "[deploy] Skipping build"
fi

if [[ "${NEEDS_SEED}" -eq 1 ]]; then
  echo "[deploy] Initializing DB schema before seed"
  docker compose run --rm "${SERVICE_NAME}" python scripts/init_db.py
  echo "[deploy] Running seed"
  docker compose run --rm "${SERVICE_NAME}" python scripts/seed_questions.py
else
  echo "[deploy] Skipping seed"
fi

if [[ "${NEEDS_RESTART}" -eq 1 ]]; then
  echo "[deploy] Restarting ${SERVICE_NAME}"
  docker compose up -d --force-recreate "${SERVICE_NAME}"
else
  echo "[deploy] Skipping restart"
fi

echo "[deploy] Completed successfully"
