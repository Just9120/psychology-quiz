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
