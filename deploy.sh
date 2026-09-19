#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Invoked from the validated candidate, never from an older host checkout.
EXPECTED_SHA="${1:-}"
PROJECT_DIR=/opt/psychology-quiz
SERVICES=(psych_quiz_bot psych_quiz_miniapp_api)
log() { printf '[deploy] %s\n' "$*"; }
fail() { log "ERROR: $*" >&2; return 1; }
compose() { docker compose --project-directory "$PROJECT_DIR" -f "$PROJECT_DIR/docker-compose.yml" -p psychology-quiz "$@"; }

[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || fail 'Exact validated main SHA required'
exec 200>/tmp/psychology-quiz-deploy.lock
flock -w 60 200 || fail 'Another deployment holds the lock'
cd "$PROJECT_DIR"
[[ "$(pwd -P)" == "$PROJECT_DIR" ]] || fail 'Unexpected physical target directory'
[[ "$(git rev-parse --show-toplevel)" == "$PROJECT_DIR" ]] || fail 'Unexpected worktree root'
[[ "$(git branch --show-current)" == main ]] || fail 'Expected main checkout'
case "$(git remote get-url origin)" in
  https://github.com/Just9120/psychology-quiz.git|git@github.com:Just9120/psychology-quiz.git) ;;
  *) fail 'Unexpected origin repository' ;;
esac
git diff --quiet && git diff --cached --quiet || fail 'Tracked local changes present'
[[ -f .env && -f docker-compose.yml ]] || fail 'Existing runtime configuration required; no bootstrap'
[[ "$(docker context show)" == default ]] || fail 'Unexpected Docker context'
[[ -z "${DOCKER_HOST:-}" && -z "${COMPOSE_FILE:-}" ]] || fail 'External Docker/Compose override refused'

OLD_HEAD="$(git rev-parse HEAD)"
git fetch origin main
[[ "$(git rev-parse origin/main)" == "$EXPECTED_SHA" ]] || fail 'Stale candidate: main has changed; no deployment'
git merge-base --is-ancestor "$OLD_HEAD" "$EXPECTED_SHA" || fail 'Host checkout cannot fast-forward'

# Verify the existing deployment unit before changing checkout or services.
DEPLOYED_SHA=''
for service in "${SERVICES[@]}"; do
  container_id="$(compose ps -q "$service")"
  [[ -n "$container_id" ]] || fail "Missing existing service: $service"
  [[ "$(docker inspect -f '{{.State.Running}}' "$container_id")" == true ]] || fail "Service is not running: $service"
  [[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$container_id")" == psychology-quiz ]] || fail 'Unexpected Compose project'
  [[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$container_id")" == "$service" ]] || fail 'Unexpected Compose service'
  revision="$(docker inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$container_id")"
  if [[ -z "$DEPLOYED_SHA" ]]; then DEPLOYED_SHA="$revision"; fi
  [[ "$DEPLOYED_SHA" == "$revision" ]] || fail 'Mixed runtime revisions require reconciliation'
done

STATEFUL=0
MIGRATE=0
if [[ "$DEPLOYED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  git cat-file -e "${DEPLOYED_SHA}^{commit}" || fail 'Unknown deployed source revision'
  BASE_SHA="$DEPLOYED_SHA"
else
  # First adoption: image identity was not recorded; rehearse backup conservatively.
  BASE_SHA="$OLD_HEAD"
  STATEFUL=1
fi
CHANGED_FILES="$(git diff --name-only "$BASE_SHA" "$EXPECTED_SHA")"
NEEDS_RUNTIME=0
while IFS= read -r file; do
  case "$file" in
    Dockerfile|docker-compose.yml|requirements.txt|app/*|scripts/*|sql/*|content/*|deploy.sh|.github/workflows/deploy-production.yml) NEEDS_RUNTIME=1 ;;
  esac
  case "$file" in
    app/db.py|sql/*|scripts/init_db.py|scripts/seed_questions.py|content/questions/*) STATEFUL=1; MIGRATE=1 ;;
  esac
done <<< "$CHANGED_FILES"
git merge --ff-only "$EXPECTED_SHA"
[[ "$(git rev-parse HEAD)" == "$EXPECTED_SHA" ]] || fail 'Checkout revision mismatch'
if [[ "$NEEDS_RUNTIME" == 0 && "$DEPLOYED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  log "SOURCE_SYNC_OK revision=$EXPECTED_SHA runtime_unchanged=$DEPLOYED_SHA"
  exit 0
fi

export APP_REVISION="$EXPECTED_SHA"
log "Building candidate revision=$EXPECTED_SHA stateful=$STATEFUL migrate=$MIGRATE"
# Build both images before any candidate migration. Runtime .env remains untouched.
compose build "${SERVICES[@]}"
compose run --rm --no-deps psych_quiz_bot python scripts/deployment_db.py preflight

STOPPED=0
MIGRATION_STARTED=0
recover_pre_migration() {
  code=$?
  if [[ "$STOPPED" == 1 && "$MIGRATION_STARTED" == 0 ]]; then
    log 'Pre-migration failure; starting unchanged existing containers'
    compose start "${SERVICES[@]}" || true
  fi
  log 'Deployment failed; no automatic data restore or application rollback' >&2
  exit "$code"
}
trap recover_pre_migration ERR
if [[ "$STATEFUL" == 1 ]]; then
  compose stop "${SERVICES[@]}"
  STOPPED=1
  BACKUP_PATH="$(compose run --rm --no-deps psych_quiz_bot python scripts/deployment_db.py backup)"
  [[ "$BACKUP_PATH" == /data/backups/release-*/quiz.sqlite3 ]] || fail 'Invalid backup record'
  log "BACKUP_RESTORE_OK backup=$BACKUP_PATH"
  if [[ "$MIGRATE" == 1 ]]; then
    MIGRATION_STARTED=1
    compose run --rm --no-deps psych_quiz_bot python scripts/init_db.py
    compose run --rm --no-deps psych_quiz_bot python scripts/seed_questions.py
  fi
  compose run --rm --no-deps psych_quiz_bot python scripts/deployment_db.py verify --backup "$BACKUP_PATH"
fi
compose run --rm --no-deps psych_quiz_bot python scripts/deployment_db.py smoke
compose up -d --no-build --force-recreate --no-deps "${SERVICES[@]}"
STOPPED=0
compose exec -T psych_quiz_miniapp_api python scripts/deployment_http_smoke.py
for service in "${SERVICES[@]}"; do
  container_id="$(compose ps -q "$service")"
  [[ -n "$container_id" ]] || fail "Missing deployed service: $service"
  [[ "$(docker inspect -f '{{.State.Running}}' "$container_id")" == true ]] || fail "Service stopped: $service"
  [[ "$(docker inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$container_id")" == "$EXPECTED_SHA" ]] || fail 'Running image revision mismatch'
  image_id="$(docker inspect -f '{{.Image}}' "$container_id")"
  log "RUNTIME_OK service=$service revision=$EXPECTED_SHA image=$image_id"
done
trap - ERR
log "DEPLOY_OK revision=$EXPECTED_SHA"
