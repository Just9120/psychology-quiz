#!/usr/bin/env bash
# Operator-only VPS verification of a privately transferred reviewed bundle.
set -Eeuo pipefail
umask 077

[[ $# == 3 ]] || { echo 'Usage: bash scripts/private_search_verify.sh EXPECTED_SHA /root/BUNDLE.zip BUNDLE_SHA256'; exit 2; }
expected=$1
archive=$2
archive_sha=$3
[[ "$expected" =~ ^[0-9a-f]{40}$ && "$archive_sha" =~ ^[0-9a-f]{64}$ ]]
[[ "$archive" =~ ^/root/[A-Za-z0-9][A-Za-z0-9._-]*\.zip$ ]]
[[ "$(id -u)" == 0 && -f "$archive" && ! -L "$archive" ]]
cd /opt/psychology-quiz
[[ "$(pwd -P)" == /opt/psychology-quiz ]]

exec 200>/tmp/psychology-quiz-deploy.lock
flock -n 200 || { echo 'STOP: another deployment holds the lock'; exit 1; }
# Reuse the same verified descriptor, rather than taking a second lock.
[[ "$(python3 scripts/postgres_vps.py image-state --expected-sha "$expected" --lock-held </dev/null)" == current ]]
compose=(docker compose -p psychology-quiz -f docker-compose.yml)
for service in psych_quiz_bot psych_quiz_miniapp_api; do
    container_id="$("${compose[@]}" ps -q "$service")"
    [[ -n "$container_id" ]]
    [[ "$(docker inspect "$container_id" --format '{{.State.Running}} {{index .Config.Labels "org.opencontainers.image.revision"}}')" == "true $expected" ]]
done

record="$(mktemp -d /root/psychology-search-check-XXXXXXXX)"
on_exit() {
    code=$?
    trap - EXIT
    if (( code != 0 )); then
        # Also verify personal data after a failed rebuild/QA. Preserve the
        # original failure and records; never print the private manifest.
        if [[ -s "$record/before.json" ]]; then
            if "${compose[@]}" exec -T psych_quiz_miniapp_api python scripts/postgres_manifest.py \
                --verify-user-state < "$record/before.json" \
                > "$record/failure-user-state-check.txt" 2> "$record/failure-user-state-check.log"; then
                printf 'PRIVATE_SEARCH_FAILURE_USER_STATE=PRESERVED\n'
            else
                printf 'PRIVATE_SEARCH_FAILURE_USER_STATE=UNVERIFIED\n'
            fi
        fi
        printf 'PRIVATE_SEARCH_CHECKS_STOP RECORD=%s\n' "$record"
    fi
    exit "$code"
}
trap on_exit EXIT
printf '%s\n' "$expected" > "$record/revision.txt"
printf '%s\n' "$archive_sha" > "$record/bundle-sha256.txt"
"${compose[@]}" exec -T psych_quiz_miniapp_api python scripts/postgres_manifest.py > "$record/before.json" </dev/null
chmod 600 "$archive"
python3 scripts/private_search_bundle.py install --archive "$archive" --sha256 "$archive_sha" > "$record/install.json" </dev/null
mapfile -t names < <(python3 -c 'import json,sys; data=json.load(open(sys.argv[1])); print(data["manifest"]); print(data["cases"])' "$record/install.json")
[[ ${#names[@]} == 2 ]]
manifest="/data/search-input/${names[0]}"
cases="/data/search-input/${names[1]}"
"${compose[@]}" --profile search build psych_quiz_private_search > "$record/build.log" 2>&1 </dev/null
docker image inspect psychology-quiz-psych_quiz_private_search --format '{{.Id}}' > "$record/search-image.txt"
for action in estimate probe rebuild status qa benchmark; do
    printf 'STEP=%s\n' "$action"
    case "$action" in
        probe|status) args=("$action") ;;
        estimate) args=(estimate --manifest "$manifest") ;;
        *) args=("$action" --manifest "$manifest" --cases "$cases") ;;
    esac
    "${compose[@]}" --profile search run --rm psych_quiz_private_search "${args[@]}" > "$record/$action.json" 2> "$record/$action.log" </dev/null
done
"${compose[@]}" exec -T psych_quiz_miniapp_api python scripts/postgres_manifest.py --verify-user-state < "$record/before.json" > "$record/user-state-check.txt"
# This command never publishes source text or before.json to the terminal.
printf 'PRIVATE_SEARCH_CHECKS_OK REVISION=%s RECORD=%s\n' "$expected" "$record"
