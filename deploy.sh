#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Invoked from the validated candidate, never from an older host checkout.
EXPECTED_SHA="${1:-}"
PWA_ARCHIVE="${2:-}"
PWA_DIGEST="${3:-}"
BACKEND_ARCHIVE="${4:-}"
BACKEND_DIGEST="${5:-}"
PROJECT_DIR=/opt/psychology-quiz
SERVICES=(psych_quiz_bot psych_quiz_miniapp_api)
log() { printf '[deploy] %s\n' "$*"; }
fail() { log "ERROR: $*" >&2; return 1; }
compose() { docker compose --project-directory "$PROJECT_DIR" -f "$PROJECT_DIR/docker-compose.yml" -p psychology-quiz "$@"; }

[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || fail 'Exact validated main SHA required'
[[ "$PWA_ARCHIVE" =~ ^/tmp/psychology-pwa\.[A-Za-z0-9]{8}/artifact\.zip$ ]] || fail 'Private incoming PWA archive required'
[[ "$PWA_DIGEST" =~ ^[0-9a-f]{64}$ ]] || fail 'Verified PWA archive digest required'
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
    Dockerfile|.dockerignore|docker-compose.yml|requirements.txt|requirements.lock|app/*|scripts/*|sql/*|content/*|deploy.sh|.github/workflows/deploy-production.yml) NEEDS_RUNTIME=1 ;;
  esac
  case "$file" in
    docker-compose.yml) STATEFUL=1 ;;
    app/db.py|app/database.py|app/postgres_*.py|app/homework*.py|app/attempt_content.py|app/*_schema.py|app/pwa_promotion.py|app/web_auth.py|app/glossary.py|app/glossary_projection.py|app/case_content.py|app/content_publication.py|app/publication_certificate.py|app/publication_receipt.py|app/source_evidence.py|sql/*|scripts/init_db.py|scripts/seed_questions.py|content/homework.json|content/questions/*|content/glossary/*|content/publication-reviews.json|content/publication-certificates.json|content/publication-receipts.json|content/publication-review-public-key.hex|content/learning-quality-reviews.json|content/legacy-publication-baseline.json|content/source-corpus.json) STATEFUL=1; MIGRATE=1 ;;
  esac
done <<< "$CHANGED_FILES"
git merge --ff-only "$EXPECTED_SHA"
[[ "$(git rev-parse HEAD)" == "$EXPECTED_SHA" ]] || fail 'Checkout revision mismatch'
# Validate/stage static before changing services; the shared lock remains held.
PWA_PLAN="$(python3 scripts/pwa_cd.py prepare --sha "$EXPECTED_SHA" --archive "$PWA_ARCHIVE" --digest "$PWA_DIGEST")"
read -r PWA_PREVIOUS PWA_TARGET <<< "$PWA_PLAN"
[[ "$PWA_PREVIOUS" =~ ^[0-9a-f]{40}$ && "$PWA_TARGET" =~ ^[0-9a-f]{40}$ ]] || fail 'Invalid PWA delivery plan'
deliver_pwa() {
  # Queue/lock alone does not prevent a newer main appearing during image build.
  git fetch origin main </dev/null
  [[ "$(git rev-parse origin/main)" == "$EXPECTED_SHA" ]] || fail 'Main advanced before static activation'
  nginx -t
  python3 scripts/pwa_cd.py publish --sha "$EXPECTED_SHA" --previous "$PWA_PREVIOUS" --target "$PWA_TARGET"
}
if [[ "$NEEDS_RUNTIME" == 0 && "$DEPLOYED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  compose exec -T psych_quiz_miniapp_api python scripts/deployment_http_smoke.py --require-pwa
  deliver_pwa
  log "SOURCE_SYNC_OK revision=$EXPECTED_SHA runtime_unchanged=$DEPLOYED_SHA"
  exit 0
fi

export APP_REVISION="$EXPECTED_SHA"
[[ "$BACKEND_ARCHIVE" == "${PWA_ARCHIVE%/artifact.zip}/backend.zip" ]] || fail 'Verified backend archive required; no host rebuild'
[[ "$BACKEND_DIGEST" =~ ^[0-9a-f]{64}$ ]] || fail 'Verified backend artifact digest required'
CANDIDATE_IMAGE_ID="$(python3 scripts/backend_artifact.py load --sha "$EXPECTED_SHA" --archive "$BACKEND_ARCHIVE" --digest "$BACKEND_DIGEST" --id-only)"
[[ "$CANDIDATE_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]] || fail 'Invalid loaded image identity'
log "Verified candidate revision=$EXPECTED_SHA image=$CANDIDATE_IMAGE_ID stateful=$STATEFUL migrate=$MIGRATE"
# The trusted CI image is loaded before any backup/migration or service stop.
# No requirements installation or Docker build takes place on the host.
DATABASE_BACKEND="$(compose run --rm --no-deps psych_quiz_bot python scripts/deployment_db.py backend)"
[[ "$DATABASE_BACKEND" == sqlite || "$DATABASE_BACKEND" == postgresql ]] || fail 'Unknown database backend'
compose run --rm --no-deps psych_quiz_bot python scripts/deployment_db.py preflight

PG_IMAGE_STATE=current
if [[ "$DATABASE_BACKEND" == postgresql ]]; then
  PG_IMAGE_STATE="$(python3 scripts/postgres_vps.py image-state --expected-sha "$EXPECTED_SHA" --lock-held)"
  [[ "$PG_IMAGE_STATE" == current || "$PG_IMAGE_STATE" == previous || "$PG_IMAGE_STATE" == resume ]] || fail 'Unknown PostgreSQL image transition state'
  if [[ "$PG_IMAGE_STATE" != current ]]; then
    # Pull and verify the candidate while the old application is still live.
    python3 scripts/postgres_vps.py stage-vector-image --expected-sha "$EXPECTED_SHA" --lock-held
  fi
fi

# Scope: only the two owned local-backup units, never other host jobs.
if [[ "$DATABASE_BACKEND" == postgresql ]]; then
  python3 scripts/install_backup_retention.py preflight --expected-sha "$EXPECTED_SHA" --lock-held
fi

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
  if [[ "$DATABASE_BACKEND" == postgresql ]]; then
    if [[ "$PG_IMAGE_STATE" == current ]]; then
      BACKUP_PATH="$(python3 scripts/postgres_vps.py backup --expected-sha "$EXPECTED_SHA" --lock-held)"
    else
      # The transition owns backup/isolated restore before changing the DB
      # image. A failure after this point needs operator reconciliation.
      MIGRATION_STARTED=1
      BACKUP_PATH="$(python3 scripts/postgres_vps.py upgrade-vector-image --expected-sha "$EXPECTED_SHA" --lock-held)"
    fi
    [[ "$BACKUP_PATH" == "$PROJECT_DIR"/.postgres/backups/release-*/record.json ]] || fail 'Invalid PostgreSQL backup record'
    if [[ "$MIGRATE" == 1 ]]; then
      # Use the existing stopped-writer/lock window. Rebuild only an owned
      # restored copy before any production schema/content change.
      USER_RECOVERY_RECORD="$(python3 scripts/postgres_vps.py rehearse-user-recovery --expected-sha "$EXPECTED_SHA" --lock-held --record "$BACKUP_PATH")"
      [[ "$USER_RECOVERY_RECORD" =~ ^/opt/psychology-quiz/\.postgres/recovery-rehearsals/rehearsal-[A-Za-z0-9_-]+/record\.json$ ]] || fail 'Invalid user recovery record'
      log "USER_RECOVERY_OK record=$USER_RECOVERY_RECORD"
    fi
  else
    BACKUP_PATH="$(compose run --rm --no-deps psych_quiz_bot python scripts/deployment_db.py backup)"
    [[ "$BACKUP_PATH" == /data/backups/release-*/quiz.sqlite3 ]] || fail 'Invalid backup record'
  fi
  log "BACKUP_RESTORE_OK backup=$BACKUP_PATH"
  if [[ "$MIGRATE" == 1 ]]; then
    MIGRATION_STARTED=1
    compose run --rm --no-deps psych_quiz_bot python scripts/init_db.py
    compose run --rm --no-deps psych_quiz_bot python scripts/seed_questions.py
  fi
  if [[ "$DATABASE_BACKEND" == postgresql ]]; then
    python3 scripts/postgres_vps.py verify --expected-sha "$EXPECTED_SHA" --lock-held --record "$BACKUP_PATH"
  else
    compose run --rm --no-deps psych_quiz_bot python scripts/deployment_db.py verify --backup "$BACKUP_PATH"
  fi
fi
compose run --rm --no-deps psych_quiz_bot python scripts/deployment_db.py smoke
compose up -d --no-build --force-recreate --no-deps "${SERVICES[@]}"
STOPPED=0
compose exec -T psych_quiz_miniapp_api python scripts/deployment_http_smoke.py --require-pwa
for service in "${SERVICES[@]}"; do
  container_id="$(compose ps -q "$service")"
  [[ -n "$container_id" ]] || fail "Missing deployed service: $service"
  [[ "$(docker inspect -f '{{.State.Running}}' "$container_id")" == true ]] || fail "Service stopped: $service"
  [[ "$(docker inspect -f '{{.Image}}' "$container_id")" == "$CANDIDATE_IMAGE_ID" ]] || fail 'Running image differs from verified CI image'
  [[ "$(docker inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$container_id")" == "$EXPECTED_SHA" ]] || fail 'Running image revision mismatch'
  python3 scripts/runtime_exposure.py --service "$service" --container-id "$container_id" --expected-sha "$EXPECTED_SHA"
  image_id="$(docker inspect -f '{{.Image}}' "$container_id")"
  log "RUNTIME_OK service=$service revision=$EXPECTED_SHA image=$image_id"
done
deliver_pwa
if [[ "$DATABASE_BACKEND" == postgresql ]]; then
  python3 scripts/install_backup_retention.py install --expected-sha "$EXPECTED_SHA" --lock-held
fi
trap - ERR
log "DEPLOY_OK revision=$EXPECTED_SHA"
