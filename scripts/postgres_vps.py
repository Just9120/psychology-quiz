"""Project-scoped PostgreSQL operations, executed by the VPS operator/deployer.

No SSH, credentials on the command line, production restore or SQLite rollback.
The native PostgreSQL tools run inside the pinned database container.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.postgres_config import PG_DATABASE, PG_IMAGE, PG_ROLE, PG_SERVICE, private_target
from scripts.postgres_backup import backup_and_rehearse, file_digest, read_verified_record, sync_directory, write_record

PROJECT = Path("/opt/psychology-quiz")
STATE = PROJECT / ".postgres"
SERVICES = ("psych_quiz_bot", "psych_quiz_miniapp_api")
LOCK = Path("/tmp/psychology-quiz-deploy.lock")
RESTORE = re.compile(r"psychology_restore_[0-9a-f]{32}")
FORMAT = "psychology-postgres-vps-v1"


class OperationError(RuntimeError):
    """Static action identifiers only; subprocess output remains private."""


def run(command, *, data=None, input_file=None, environment=None, output=None, timeout=120):
    # Docker otherwise inherits stdin and can consume the remaining commands in
    # an operator's `bash <<'BASH'` block. Only explicit SQL/manifest/dump input
    # belongs to a child process; all other commands must receive EOF.
    stdin = input_file if input_file is not None or data is not None else subprocess.DEVNULL
    try:
        result = subprocess.run(command, input=data, stdin=stdin, env=environment, stdout=output or subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout, cwd=PROJECT)
    except (OSError, subprocess.TimeoutExpired):
        raise OperationError("command_unavailable_or_timeout") from None
    if result.returncode:
        raise OperationError("command_failed")
    return result.stdout or b""


def compose(arguments, **kwargs):
    return run(["docker", "compose", "--project-directory", str(PROJECT), "-f", str(PROJECT / "docker-compose.yml"),
                "-p", "psychology-quiz", "--profile", "postgres", *arguments], **kwargs)


def identifier(value):
    if re.fullmatch(r"[a-z][a-z0-9_]*", value) is None:
        raise OperationError("invalid_database_identifier")
    return '"' + value + '"'


@contextmanager
def delivery_lock(inherited=False):
    import fcntl
    if inherited:
        descriptor = 200
        actual, expected = os.fstat(descriptor), LOCK.stat()
        if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise OperationError("invalid_inherited_deployment_lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    else:
        with LOCK.open("a") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise OperationError("another_deployment_holds_lock") from None
            yield


def assert_checkout(expected):
    if ROOT.resolve() != PROJECT or PROJECT.resolve() != PROJECT or not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise OperationError("unexpected_checkout")
    if os.environ.get("DOCKER_HOST") or os.environ.get("COMPOSE_FILE"):
        raise OperationError("external_runtime_override")
    if run(["git", "rev-parse", "HEAD"]).decode().strip() != expected:
        raise OperationError("checkout_revision_mismatch")
    if run(["git", "rev-parse", "origin/main"]).decode().strip() != expected:
        raise OperationError("checkout_must_match_fetched_main")
    if run(["git", "branch", "--show-current"]).decode().strip() != "main":
        raise OperationError("main_checkout_required")
    origin = run(["git", "remote", "get-url", "origin"]).decode().strip()
    if origin not in {"https://github.com/Just9120/psychology-quiz.git", "git@github.com:Just9120/psychology-quiz.git"}:
        raise OperationError("unexpected_repository")
    run(["git", "diff", "--quiet"])
    run(["git", "diff", "--cached", "--quiet"])
    if run(["docker", "context", "show"]).decode().strip() != "default":
        raise OperationError("unexpected_docker_context")
    if not (PROJECT / ".env").is_file() or (PROJECT / ".env").is_symlink():
        raise OperationError("existing_regular_runtime_config_required")


class Runtime:
    def __init__(self, revision, *, target_override=None):
        self.revision, self.target_override = revision, target_override
        self.owned_restore = set()

    def app(self, arguments, *, data=None):
        environment = os.environ.copy()
        environment["APP_REVISION"] = self.revision
        overrides = []
        if self.target_override is not None:
            environment["DATABASE_URL"] = self.target_override
            overrides = ["--env", "DATABASE_URL"]
        images = compose(["config", "--images", SERVICES[0]], environment=environment).decode().split()
        if len(images) != 1:
            raise OperationError("one_candidate_application_image_required")
        image = json.loads(run(["docker", "image", "inspect", images[0]]))[0]
        if (image["Config"].get("Labels") or {}).get("org.opencontainers.image.revision") != self.revision:
            raise OperationError("candidate_application_image_revision_mismatch")
        return compose(["run", "--rm", "--no-deps", *overrides, SERVICES[0], "python", *arguments],
                       data=data, environment=environment, timeout=300)

    def container(self, service):
        ids = compose(["ps", "--all", "--quiet", service]).decode().split()
        if len(ids) != 1:
            raise OperationError("one_known_container_required")
        item = json.loads(run(["docker", "inspect", ids[0]]))[0]
        labels = item["Config"].get("Labels") or {}
        if labels.get("com.docker.compose.project") != "psychology-quiz" or labels.get("com.docker.compose.service") != service:
            raise OperationError("container_target_mismatch")
        return item

    def require_stopped_writers(self):
        for service in SERVICES:
            if self.container(service)["State"]["Running"]:
                raise OperationError("all_runtime_writers_must_be_stopped")

    def require_running_revision(self):
        for service in SERVICES:
            item = self.container(service)
            if not item["State"]["Running"] or item["Config"]["Labels"].get("org.opencontainers.image.revision") != self.revision:
                raise OperationError("expected_running_revision_required")

    def pg(self, arguments, *, data=None, input_file=None, output=None):
        # Static shell wrapper reads a mounted secret; arguments are separate argv.
        wrapper = 'export PGPASSWORD="$(cat /run/secrets/postgres_admin_password)"; exec "$@"'
        return compose(["exec", "-T", PG_SERVICE, "sh", "-eu", "-c", wrapper, "postgres-tool", *arguments],
                       data=data, input_file=input_file, output=output, timeout=600)

    def sql(self, statement):
        return self.pg(["psql", "-X", "-qAt", "--username", "postgres", "--dbname", "postgres",
                        "--set", "ON_ERROR_STOP=1"], data=statement.encode()).decode().strip()

    def identity(self):
        return {"project": "psychology-quiz", "database": PG_DATABASE, "service": PG_SERVICE,
                "cluster": self.sql("SELECT system_identifier FROM pg_control_system();"), "revision": self.revision}

    def verify_database_container(self):
        item = self.container(PG_SERVICE)
        if not item["State"]["Running"] or item["Config"]["Image"] != PG_IMAGE:
            raise OperationError("unexpected_postgres_image_or_state")
        if item["HostConfig"].get("PortBindings"):
            raise OperationError("postgres_host_port_must_not_be_published")
        if set(item["NetworkSettings"]["Networks"]) != {"psychology-quiz_default"}:
            raise OperationError("unexpected_postgres_network")
        mounts = [mount for mount in item["Mounts"] if mount["Destination"] == "/var/lib/postgresql"]
        if len(mounts) != 1 or mounts[0]["Type"] != "bind" or Path(mounts[0]["Source"]) != STATE / "data":
            raise OperationError("unexpected_postgres_storage")
        if self.sql("SHOW data_checksums;") != "on":
            raise OperationError("postgres_checksums_required")
        if self.sql("SHOW server_version;").split()[0] != "18.6":
            raise OperationError("unexpected_postgres_version")

    def manifest(self, database=None):
        arguments = ["scripts/postgres_manifest.py"]
        if database is not None:
            if RESTORE.fullmatch(database) is None:
                raise OperationError("owned_restore_name_required")
            arguments += ["--database", database]
        return json.loads(self.app(arguments))

    def dump(self, path):
        with path.open("xb") as output:
            self.pg(["pg_dump", "--username", "postgres", "--dbname", PG_DATABASE,
                     "--format=custom", "--no-owner", "--no-acl"], output=output)
            output.flush()
            os.fsync(output.fileno())

    def create_restore_database(self, name):
        if RESTORE.fullmatch(name) is None or self.sql(f"SELECT count(*) FROM pg_database WHERE datname='{name}';") != "0":
            raise OperationError("restore_database_must_be_new")
        try:
            self.sql(f"CREATE DATABASE {identifier(name)} OWNER {identifier(PG_ROLE)} TEMPLATE template0;")
        except OperationError:
            # Read after an uncertain response; don't repeat CREATE blindly.
            if self.sql(f"SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='{name}';") != PG_ROLE:
                raise
        self.owned_restore.add(name)

    def restore(self, dump, database):
        if database not in self.owned_restore:
            raise OperationError("restore_target_not_owned")
        # Only the just-created database is a restore target; never PG_DATABASE.
        with dump.open("rb") as source:
            self.pg(["pg_restore", "--username", "postgres", "--dbname", database, "--role", PG_ROLE,
                     "--exit-on-error", "--single-transaction", "--no-owner", "--no-acl"], input_file=source)

    def drop_restore_database(self, name):
        if name not in self.owned_restore or RESTORE.fullmatch(name) is None:
            raise OperationError("restore_cleanup_target_not_owned")
        if self.sql(f"SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='{name}';") != PG_ROLE:
            raise OperationError("restore_database_owner_changed")
        try:
            self.sql(f"DROP DATABASE {identifier(name)};")
        except OperationError:
            if self.sql(f"SELECT count(*) FROM pg_database WHERE datname='{name}';") != "0":
                raise
        self.owned_restore.remove(name)


def private_file(path):
    info = path.lstat()
    expected_owner = 999 if path == STATE / "admin.password" else os.geteuid()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != expected_owner or info.st_mode & 0o077:
        raise OperationError("private_owned_regular_file_required")
    return path.read_bytes()


def load_state():
    info = STATE.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise OperationError("private_owned_state_directory_required")
    record = json.loads(private_file(STATE / "state.json"))
    if record.get("format") != FORMAT or record.get("project") != str(PROJECT):
        raise OperationError("unknown_postgres_state")
    for name in ("admin.password", "app.password"):
        if re.fullmatch(rb"[0-9a-f]{64}\n", private_file(STATE / name)) is None:
            raise OperationError("invalid_private_credential_file")
    return record


def phase(record, value, **fields):
    record.update(fields, phase=value, updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    write_record(STATE / "state.json", record)


def app_target():
    return private_target(private_file(STATE / "app.password").decode().strip())


def env_target(item):
    values = dict(entry.split("=", 1) for entry in item["Config"]["Env"] if "=" in entry)
    return values.get("DATABASE_URL", "").strip(), values.get("DB_PATH", "")


def source_path(runtime):
    items = [runtime.container(service) for service in SERVICES]
    for item in items:
        mounts = [mount for mount in item["Mounts"] if mount["Destination"] == "/data"]
        if len(mounts) != 1 or mounts[0]["Type"] != "bind" or Path(mounts[0]["Source"]) != PROJECT / "data":
            raise OperationError("unexpected_application_persistent_storage")
    targets = [env_target(item) for item in items]
    if targets[0] != targets[1] or targets[0][0]:
        raise OperationError("both_writers_must_use_same_sqlite_source")
    path = Path(targets[0][1])
    if not path.is_absolute() or not path.is_relative_to("/data") or ".." in path.parts:
        raise OperationError("sqlite_source_must_be_under_data")
    host = PROJECT / "data" / path.relative_to("/data")
    if not host.is_file() or host.is_symlink() or not host.resolve().is_relative_to(PROJECT / "data"):
        raise OperationError("existing_regular_sqlite_source_required")
    return host


def check_space(required):
    free = shutil.disk_usage(PROJECT).free
    if free < required:
        raise OperationError("insufficient_space_for_database_and_restore")
    return free


def preflight(runtime):
    runtime.require_running_revision()
    # Do not start an outage before discovering an ambiguous or public config.
    content = private_file(PROJECT / ".env")
    replace_database_url(content, private_target("preflight-only"))
    source = source_path(runtime)
    # An operation reserve, not a product capacity/SLO guarantee. Import, dump,
    # isolated restore and the preserved SQLite snapshot coexist during cutover.
    required = max(1024 ** 3, source.stat().st_size * 8)
    free = check_space(required)
    if STATE.exists() or STATE.is_symlink():
        record = load_state()
        if record["phase"] not in {"allocated", "database_started", "prepared"}:
            raise OperationError("existing_cutover_requires_resume_not_prepare")
    else:
        if compose(["ps", "--all", "--quiet", PG_SERVICE]).strip():
            raise OperationError("unknown_existing_postgres_container")
    runtime.app(["scripts/deployment_db.py", "preflight"])
    return {"sqlite_bytes": source.stat().st_size, "free_bytes": free, "reserve_bytes": required}


def prepare(runtime):
    capacity = preflight(runtime)
    if not STATE.exists():
        # The pinned Debian image uses uid 999. Verify before creating private
        # material; its entrypoint reads the secret again after dropping root.
        if run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "id", PG_IMAGE, "-u", "postgres"], timeout=600).strip() != b"999":
            raise OperationError("unexpected_postgres_container_uid")
        STATE.mkdir(mode=0o700)
        # Exclusive creation: never replace credentials or adopt unknown data.
        for name in ("admin.password", "app.password"):
            with (STATE / name).open("xb") as output:
                output.write((secrets.token_hex(32) + "\n").encode())
        os.chown(STATE / "admin.password", 999, 999)
        os.chmod(STATE / "admin.password", 0o400)
        (STATE / "data").mkdir(mode=0o700)
        record = {"format": FORMAT, "project": str(PROJECT), "revision": runtime.revision}
        phase(record, "allocated", capacity=capacity)
    record = load_state()
    if (STATE / "data").is_symlink() or not (STATE / "data").is_dir():
        raise OperationError("owned_data_directory_required")
    compose(["up", "-d", "--no-deps", PG_SERVICE], timeout=600)
    for attempt in range(30):
        try:
            runtime.verify_database_container()
            break
        except OperationError:
            if attempt == 29:
                raise
            time.sleep(2)
    identity = runtime.identity()
    if record.get("cluster") not in (None, identity["cluster"]):
        raise OperationError("postgres_cluster_identity_changed")
    phase(record, "database_started", cluster=identity["cluster"])
    # Password is generated hex, carried only on stdin, with server statement
    # logging disabled. Do not ALTER a role on retry or rotate existing secrets.
    role = runtime.sql(f"SELECT rolsuper::int||','||rolcreatedb::int||','||rolcreaterole::int||','||rolcanlogin::int||','||rolreplication::int||','||rolbypassrls::int FROM pg_roles WHERE rolname='{PG_ROLE}';")
    if not role:
        password = private_file(STATE / "app.password").decode().strip()
        runtime.sql(f"CREATE ROLE {identifier(PG_ROLE)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '{password}';")
    elif role != "0,0,0,1,0,0":
        raise OperationError("unexpected_application_role_permissions")
    owner = runtime.sql(f"SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='{PG_DATABASE}';")
    if not owner:
        runtime.sql(f"CREATE DATABASE {identifier(PG_DATABASE)} OWNER {identifier(PG_ROLE)} TEMPLATE template0;")
    elif owner != PG_ROLE:
        raise OperationError("unexpected_application_database_owner")
    target = Runtime(runtime.revision, target_override=app_target())
    target.app(["scripts/postgres_storage.py", "init"])
    phase(record, "prepared", revision=runtime.revision)
    return record


def configured_runtime(revision):
    record = load_state()
    runtime = Runtime(revision, target_override=app_target())
    runtime.verify_database_container()
    if runtime.identity()["cluster"] != record.get("cluster"):
        raise OperationError("postgres_cluster_identity_changed")
    return runtime, record


def backup(runtime):
    size = int(runtime.sql(f"SELECT pg_database_size('{PG_DATABASE}');"))
    check_space(max(1024 ** 3, size * 3))
    return backup_and_rehearse(runtime, STATE / "backups")


def verify_backup(runtime, path):
    path = path.resolve(strict=True)
    if not path.is_relative_to(STATE / "backups") or path.name != "record.json":
        raise OperationError("owned_backup_record_required")
    record = read_verified_record(path)
    if record["source"] != runtime.identity():
        raise OperationError("backup_source_or_revision_mismatch")
    runtime.require_stopped_writers()
    runtime.app(["scripts/postgres_manifest.py", "--verify-user-state"],
                data=json.dumps(record["before"]).encode())


def replace_database_url(content, target):
    """Change exactly one simple dotenv assignment, preserving all other bytes."""
    lines = content.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if re.match(rb"^\s*(?:export\s+)?DATABASE_URL\s*=", line)]
    if len(matches) > 1:
        raise OperationError("duplicate_database_url_config")
    newline = b"\r\n" if b"\r\n" in content else b"\n"
    assignment = b"DATABASE_URL=" + target.encode("ascii") + newline
    if matches:
        value = lines[matches[0]].split(b"=", 1)[1].strip()
        if value not in {b"", b"''", b'""'}:
            raise OperationError("nonempty_database_url_must_not_be_overwritten")
        lines[matches[0]] = assignment
        return b"".join(lines)
    return content + (newline if content and not content.endswith(b"\n") else b"") + assignment


def switch_environment(record):
    path, saved = PROJECT / ".env", STATE / "sqlite.env"
    original = private_file(saved)
    replacement = replace_database_url(original, app_target())
    actual = path.read_bytes()
    if actual == replacement:
        return  # Readback resolves an interrupted atomic replace.
    if actual != original or path.is_symlink():
        raise OperationError("runtime_config_changed_during_cutover")
    temporary = STATE / "postgres.env"
    with temporary.open("wb") as output:
        output.write(replacement)
        output.flush()
        os.fsync(output.fileno())
    info = path.stat()
    os.chown(temporary, info.st_uid, info.st_gid)
    os.chmod(temporary, stat.S_IMODE(info.st_mode))
    os.replace(temporary, path)
    sync_directory(path.parent)
    if path.read_bytes() != replacement:
        raise OperationError("runtime_config_readback_failed")


def cutover(revision):
    runtime, record = configured_runtime(revision)
    original_runtime = Runtime(revision)
    if record["revision"] != revision:
        raise OperationError("prepare_current_revision_before_cutover")
    allowed = {"prepared", "stopping", "stopped", "snapshotted", "imported", "recovery_verified",
               "configured", "postgres_writers_starting", "complete"}
    if record["phase"] not in allowed:
        raise OperationError("complete_prepare_first")
    if record["phase"] == "complete":
        runtime.require_running_revision()
        post_checks(runtime)
        return record
    if record["phase"] == "prepared":
        preflight(original_runtime)
        if (STATE / "sqlite.env").exists():
            raise OperationError("unexpected_saved_runtime_config")
        with (STATE / "sqlite.env").open("xb") as output:
            output.write((PROJECT / ".env").read_bytes())
        phase(record, "stopping")
    try:
        # Stop even on retry after a partial start. Once PostgreSQL writers were
        # attempted, resume only PostgreSQL; never repeat import or switch back.
        compose(["stop", *SERVICES])
        runtime.require_stopped_writers()
        if record["phase"] == "stopping":
            phase(record, "stopped")
        if record["phase"] == "stopped":
            source = original_runtime.app(["scripts/deployment_db.py", "backup"]).decode().strip()
            if re.fullmatch(r"/data/backups/release-[a-zA-Z0-9_-]+/quiz.sqlite3", source) is None:
                raise OperationError("invalid_sqlite_backup_record")
            host = PROJECT / "data" / Path(source).relative_to("/data")
            phase(record, "snapshotted", sqlite_snapshot=source, sqlite_sha256=file_digest(host))
        if record["phase"] == "snapshotted":
            source = record["sqlite_snapshot"]
            host = PROJECT / "data" / Path(source).relative_to("/data")
            if file_digest(host) != record["sqlite_sha256"]:
                raise OperationError("sqlite_snapshot_changed")
            # Import is idempotent only before PostgreSQL writes. Output report
            # path is new on each attempt; a prior commit is verified, not reset.
            report = str(Path(source).with_name("postgres-import-" + secrets.token_hex(8) + ".json"))
            runtime.app(["scripts/postgres_storage.py", "import", "--source", source, "--report", report])
            runtime.app(["scripts/deployment_db.py", "smoke"])
            phase(record, "imported", import_report=report)
        if record["phase"] == "imported":
            recovery = backup(runtime)
            verify_backup(runtime, recovery)
            phase(record, "recovery_verified", recovery_record=str(recovery))
        if record["phase"] == "recovery_verified":
            switch_environment(record)
            phase(record, "configured")
        if record["phase"] == "configured":
            # Persist this boundary BEFORE either service can write to PG.
            phase(record, "postgres_writers_starting")
        if record["phase"] == "postgres_writers_starting":
            replacement = replace_database_url(private_file(STATE / "sqlite.env"), app_target())
            if (PROJECT / ".env").read_bytes() != replacement:
                raise OperationError("postgres_config_changed_before_start")
            runtime.app(["scripts/deployment_db.py", "smoke"])
            environment = os.environ.copy()
            environment["APP_REVISION"] = revision
            compose(["up", "-d", "--no-build", "--force-recreate", "--no-deps", *SERVICES], environment=environment)
            runtime.require_running_revision()
            post_checks(runtime)
            images = {service: runtime.container(service)["Image"] for service in SERVICES}
            phase(record, "complete", images=images)
        return record
    except BaseException as error:
        record["last_error_type"] = type(error).__name__
        write_record(STATE / "state.json", record)
        try:
            compose(["stop", *SERVICES])
        except Exception:
            pass
        raise


def post_checks(runtime):
    for service in SERVICES:
        if env_target(runtime.container(service))[0] != app_target():
            raise OperationError("running_database_target_mismatch")
    compose(["exec", "-T", SERVICES[1], "python", "scripts/deployment_http_smoke.py"], timeout=120)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "prepare", "cutover", "status", "backup", "verify"))
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--lock-held", action="store_true", help="Only deploy.sh with inherited fd 200")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if os.geteuid() != 0:
            raise OperationError("root_vps_operator_required")
        with delivery_lock(args.lock_held):
            assert_checkout(args.expected_sha)
            runtime = Runtime(args.expected_sha)
            if args.action == "preflight":
                print(json.dumps(preflight(runtime), sort_keys=True))
                print("POSTGRES_PREFLIGHT_OK")
            elif args.action == "prepare":
                prepare(runtime)
                print("POSTGRES_PREPARED; SQLite runtime unchanged")
            elif args.action == "cutover":
                record = cutover(args.expected_sha)
                print("POSTGRES_CUTOVER_OK revision=" + record["revision"])
                print("RECORD=" + str(STATE / "state.json"))
            elif args.action == "status":
                record = load_state()
                print(json.dumps({key: record.get(key) for key in ("phase", "revision", "cluster", "updated_at", "last_error_type")}, sort_keys=True))
            else:
                runtime, record = configured_runtime(args.expected_sha)
                if record["phase"] != "complete":
                    raise OperationError("completed_cutover_required_for_routine_delivery")
                # The candidate's .env must select this exact private database.
                if Runtime(args.expected_sha).app(["scripts/deployment_db.py", "backend"]).strip() != b"postgresql":
                    raise OperationError("postgres_runtime_config_required")
                for service in SERVICES:
                    if env_target(runtime.container(service))[0] != app_target():
                        raise OperationError("existing_writer_database_target_mismatch")
                if args.action == "backup":
                    print(backup(runtime))
                else:
                    if args.record is None:
                        raise OperationError("backup_record_required")
                    verify_backup(runtime, args.record)
                    print("POSTGRES_USER_STATE_PRESERVED")
        return 0
    except Exception as error:
        reason = str(error) if isinstance(error, OperationError) else type(error).__name__
        print("POSTGRES_OPERATION_STOP: " + reason + "; preserve .postgres/state.json and recovery records", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
