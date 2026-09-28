#!/usr/bin/env bash
# Disposable same-volume PG18.6 -> PG18.6/pgvector rehearsal for CI only.
set -Eeuo pipefail

old_image='postgres:18.6-bookworm@sha256:3725f4e2499eef5134592b3b4ab79a543ed7f8e533b05b5b637af926630f6650'
new_image='pgvector/pgvector:0.8.6-pg18-bookworm@sha256:1d50c689b0a6511b9ea0a15615281c81a59fd04a08eb35057ec8646fb3a2118a'
volume=''
container=''

cleanup() {
    if [[ -n "$container" ]]; then
        docker rm -f "$container" >/dev/null 2>&1 || true
    fi
    if [[ -n "$volume" ]]; then
        docker volume rm "$volume" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

[[ "$old_image" == "$(python -c 'from app.postgres_config import PG_PREVIOUS_IMAGE; print(PG_PREVIOUS_IMAGE)')" ]]
[[ "$new_image" == "$(python -c 'from app.postgres_config import PG_IMAGE; print(PG_IMAGE)')" ]]
docker pull --quiet "$old_image" >/dev/null
docker pull --quiet "$new_image" >/dev/null
volume="$(docker volume create)"

start_database() {
    local image="$1"
    container="$(docker run -d --rm --pull=never --network none \
        -e POSTGRES_DB=psychology_upgrade_test \
        -e POSTGRES_PASSWORD=synthetic-upgrade-only \
        -e 'POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256 --auth-local=scram-sha-256 --data-checksums' \
        -v "$volume:/var/lib/postgresql" "$image")"
    for attempt in {1..40}; do
        if docker exec "$container" pg_isready -U postgres \
            -d psychology_upgrade_test >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo 'DISPOSABLE_POSTGRES_NOT_READY' >&2
    return 1
}

query() {
    docker exec -e PGPASSWORD=synthetic-upgrade-only "$container" \
        psql -X -qAt -v ON_ERROR_STOP=1 -U postgres \
        -d psychology_upgrade_test -c "$1"
}

start_database "$old_image"
query "CREATE TABLE public.learning_state_probe(actor bigint PRIMARY KEY, progress integer NOT NULL); INSERT INTO public.learning_state_probe VALUES (7,42);" >/dev/null
cluster_before="$(query 'SELECT system_identifier FROM pg_control_system();')"
[[ "$cluster_before" =~ ^[0-9]+$ ]]
[[ "$(query 'SELECT actor,progress FROM public.learning_state_probe;')" == '7|42' ]]
docker stop "$container" >/dev/null
container=''

start_database "$new_image"
[[ "$(query "SELECT split_part(current_setting('server_version'),' ',1);")" == '18.6' ]]
[[ "$(query 'SELECT system_identifier FROM pg_control_system();')" == "$cluster_before" ]]
[[ "$(query 'SELECT actor,progress FROM public.learning_state_probe;')" == '7|42' ]]
query "CREATE SCHEMA private_search; CREATE EXTENSION vector WITH SCHEMA private_search VERSION '0.8.6';" >/dev/null
[[ "$(query "SELECT e.extversion || ':' || n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector';")" == '0.8.6:private_search' ]]
[[ "$(query 'SELECT actor,progress FROM public.learning_state_probe;')" == '7|42' ]]

echo PGVECTOR_SAME_VOLUME_TRANSITION_OK
