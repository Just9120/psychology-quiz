#!/usr/bin/env bash
# Owner-authorized config cutover on the existing VPS, after verified code delivery.
set -Eeuo pipefail
umask 077
cd /opt/psychology-quiz
EXPECTED_SHA="${1:?expected delivered revision required}"
[[ "$(id -u)" == 0 && "$(git rev-parse HEAD)" == "$EXPECTED_SHA" ]]
[[ "$(python3 scripts/postgres_vps.py image-state --expected-sha "$EXPECTED_SHA" </dev/null)" == current ]]
exec 200>/tmp/psychology-quiz-deploy.lock
flock -n 200 || { echo 'MINIAPP_DOMAIN_STOP: deployment in progress'; exit 1; }
[[ "$(git rev-parse HEAD)" == "$EXPECTED_SHA" ]]
[[ "$(pwd -P)" == /opt/psychology-quiz && "$(git branch --show-current)" == main ]]
[[ "$(docker context show)" == default && -z "${DOCKER_HOST:-}" && -z "${COMPOSE_FILE:-}" ]]
[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]
export APP_REVISION="$EXPECTED_SHA"
[[ "$(docker image inspect "psychology-quiz-runtime:$EXPECTED_SHA" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" == "$EXPECTED_SHA" ]]
for service in psych_quiz_bot psych_quiz_miniapp_api; do
    id="$(docker compose -p psychology-quiz -f docker-compose.yml ps -q "$service")"
    [[ -n "$id" && "$(docker inspect "$id" --format '{{.State.Running}}')" == true ]]
    [[ "$(docker inspect "$id" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" == "$EXPECTED_SHA" ]]
done
RECORD="$(mktemp -d /root/psychology-miniapp-domain-XXXXXXXX)"
compose() { docker compose -p psychology-quiz -f docker-compose.yml "$@"; }
recover() {
    local code=$?
    trap - EXIT
    set +e
    if (( code != 0 )); then
        if [[ -f "$RECORD/env.updated-sha256" ]]; then
            if python3 scripts/miniapp_domain_config.py restore --env .env --backup "$RECORD/env"; then
                compose up -d --no-deps --no-build --force-recreate psych_quiz_bot psych_quiz_miniapp_api </dev/null
                compose exec -T psych_quiz_miniapp_api python scripts/deployment_http_smoke.py </dev/null
            fi
        fi
        printf 'MINIAPP_DOMAIN_STOP RECORD=%s\n' "$RECORD"
    fi
    exit "$code"
}
trap recover EXIT
python3 scripts/miniapp_domain_config.py apply --env .env --backup "$RECORD/env"
compose up -d --no-deps --no-build --force-recreate psych_quiz_bot psych_quiz_miniapp_api </dev/null
compose exec -T psych_quiz_miniapp_api python scripts/deployment_http_smoke.py </dev/null
compose exec -T psych_quiz_miniapp_api python - <<'PY'
import os
import urllib.request
from scripts.miniapp_domain_config import migrated_url
expected = 'https://miniapp.psy.cloud-nodes.net'
actual = os.environ['MINI_APP_URL']
assert migrated_url(actual) == actual
for origin in ['https://miniapp.librechat.online', expected, 'https://untrusted.example']:
    request = urllib.request.Request('http://127.0.0.1:8081/miniapp/state', method='OPTIONS', headers={'Origin': origin})
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 204
        assert response.headers.get('Access-Control-Allow-Origin') == (None if origin.endswith('untrusted.example') else origin)
print('MINIAPP_URL_AND_CORS_OK')
PY
for service in psych_quiz_bot psych_quiz_miniapp_api; do
    id="$(compose ps -q "$service")"
    [[ -n "$id" && "$(docker inspect "$id" --format '{{.State.Running}}')" == true ]]
    [[ "$(docker inspect "$id" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" == "$EXPECTED_SHA" ]]
done
printf 'MINIAPP_DOMAIN_OK REVISION=%s RECORD=%s\n' "$EXPECTED_SHA" "$RECORD"
