import copy
import os
from pathlib import Path
import shutil
import subprocess
import textwrap

import pytest

from scripts.check_deploy_candidate import select_candidate, validate_records

SHA = "a" * 40
OLD = "b" * 40
REPO = "Just9120/psychology-quiz"


def records():
    return {"workflow_runs": [{"head_sha": SHA, "head_branch": "main", "event": "push",
            "status": "completed", "conclusion": "success", "path": ".github/workflows/ci.yml",
            "repository": {"full_name": REPO}}]}


def test_exact_trusted_success_allows_candidate():
    event = {"workflow_run": {**records()["workflow_runs"][0], "head_repository": {"full_name": REPO}}}
    assert select_candidate(event, "workflow_run", REPO, OLD) == SHA
    validate_records(SHA, {"commit": {"sha": SHA}}, records())
    assert select_candidate({}, "workflow_dispatch", REPO, SHA, "refs/heads/main") == SHA


@pytest.mark.parametrize("field,value", [("event", "pull_request"), ("conclusion", "failure"), ("head_branch", "feature")])
def test_untrusted_trigger_refused(field, value):
    run = {**records()["workflow_runs"][0], "head_repository": {"full_name": REPO}, field: value}
    with pytest.raises(ValueError):
        select_candidate({"workflow_run": run}, "workflow_run", REPO, SHA)


def test_fork_and_manual_feature_refused():
    run = {**records()["workflow_runs"][0], "head_repository": {"full_name": "fork/project"}}
    with pytest.raises(ValueError):
        select_candidate({"workflow_run": run}, "workflow_run", REPO, SHA)
    with pytest.raises(ValueError):
        select_candidate({"ref": "refs/heads/feature"}, "workflow_dispatch", REPO, SHA)


@pytest.mark.parametrize("field,value", [("status", "in_progress"), ("conclusion", "failure"), ("head_sha", OLD), ("path", ".github/workflows/other.yml")])
def test_later_incomplete_failed_or_wrong_run_cannot_reuse_old_success(field, value):
    runs = records()
    latest = copy.deepcopy(runs["workflow_runs"][0])
    latest[field] = value
    runs["workflow_runs"].insert(0, latest)
    with pytest.raises(ValueError):
        validate_records(SHA, {"commit": {"sha": SHA}}, runs)


def test_stale_or_missing_primary_record_refused():
    with pytest.raises(ValueError):
        validate_records(SHA, {"commit": {"sha": OLD}}, records())
    with pytest.raises(ValueError):
        validate_records(SHA, {"commit": {"sha": SHA}}, {"workflow_runs": []})


# Real shell procedure, fake system boundaries: no Docker/SSH/Git mutations.
BOUNDARIES = r'''
FAKE_HEAD="$OLD"
DEPLOY_STARTED=0
cd() { :; }
pwd() { echo /opt/psychology-quiz; }
flock() { [[ "$FAULT" != lock ]]; }
git() {
  printf 'git %s\n' "$*" >> "$COMMAND_LOG"
  case "$*" in
    'rev-parse --show-toplevel') echo /opt/psychology-quiz ;;
    'branch --show-current') echo main ;;
    'remote get-url origin') echo https://github.com/Just9120/psychology-quiz.git ;;
    'diff --quiet') [[ "$FAULT" != dirty ]] ;;
    'rev-parse HEAD') echo "$FAKE_HEAD" ;;
    'rev-parse origin/main') if [[ "$FAULT" == stale ]]; then echo "$OLD"; else echo "$EXPECTED"; fi ;;
    'diff --name-only '*)
      if [[ "$FAULT" == docs ]]; then echo README.md;
      elif [[ "$FAULT" == first_adoption ]]; then echo app/main.py;
      elif [[ "$FAULT" == snapshot_change ]]; then echo app/attempt_content.py;
      elif [[ "$FAULT" == identity_change ]]; then echo app/identity_schema.py;
      elif [[ "$FAULT" == auth_change ]]; then echo app/auth_schema.py;
      else echo app/db.py; fi ;;
    'merge --ff-only '*) FAKE_HEAD="$EXPECTED" ;;
    *) return 0 ;;
  esac
}
docker() {
  printf 'docker %s\n' "$*" >> "$COMMAND_LOG"
  if [[ "$1" == context ]]; then echo default; return; fi
  if [[ "$1" == inspect ]]; then
    case "$3" in
      *State.Running*) echo true ;;
      *com.docker.compose.project*) if [[ "$FAULT" == project ]]; then echo foreign; else echo psychology-quiz; fi ;;
      *com.docker.compose.service*) echo "${@: -1}" ;;
      *org.opencontainers.image.revision*)
        if [[ "$DEPLOY_STARTED" == 1 && "$FAULT" != image ]]; then echo "$EXPECTED";
        elif [[ "$FAULT" == first_adoption ]]; then echo '<no value>';
        else echo "$OLD"; fi ;;
      *Image*) echo sha256:test-image ;;
    esac
    return
  fi
  shift 7
  if [[ "$1 $2" == 'ps -q' ]]; then echo "$3"; return; fi
  case "$*" in
    build*) [[ "$FAULT" != build ]] ;;
    *deployment_db.py\ backend) if [[ "$FAULT" == pg* ]]; then echo postgresql; else echo sqlite; fi ;;
    *deployment_db.py\ preflight) cat >/dev/null ;;
    *deployment_db.py\ backup) [[ "$FAULT" != backup ]] || return 2; echo /data/backups/release-test/quiz.sqlite3 ;;
    *scripts/init_db.py) [[ "$FAULT" != migration ]] ;;
    *deployment_db.py\ verify*) [[ "$FAULT" != preservation ]] ;;
    *deployment_db.py\ smoke) [[ "$FAULT" != content_parity ]] ;;
    up*) DEPLOY_STARTED=1 ;;
    *deployment_http_smoke.py) [[ "$FAULT" != health ]] ;;
    *) return 0 ;;
  esac
}
python3() {
  printf 'python3 %s\n' "$*" >> "$COMMAND_LOG"
  case "$*" in
    *postgres_vps.py\ backup*) [[ "$FAULT" != pg_backup ]] || return 2; echo /opt/psychology-quiz/.postgres/backups/release-test/record.json ;;
    *postgres_vps.py\ verify*) [[ "$FAULT" != pg_preservation ]] ;;
    *) return 99 ;;
  esac
}
'''


def run_deploy(tmp_path, fault="", through_workflow=False):
    bash = ("C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash"))
    assert bash and Path(bash).exists(), "Bash is required for deployment behavior tests"
    (tmp_path / ".env").write_text("BOT_TOKEN=synthetic\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    log = tmp_path / "commands.log"
    env = {**os.environ, "COMMAND_LOG": log.as_posix(), "FAULT": fault, "OLD": OLD, "EXPECTED": SHA}
    env.pop("DOCKER_HOST", None)
    env.pop("COMPOSE_FILE", None)
    script = Path("deploy.sh").read_text(encoding="utf-8")
    code = BOUNDARIES + "\n" + script
    if through_workflow:
        # Execute the actual workflow step; fake SSH runs its received remote command.
        (tmp_path / "deploy.sh").write_text(code, encoding="utf-8", newline="\n")
        workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
        step = workflow.split("- name: Deploy exact revision over verified SSH", 1)[1]
        step = step.split("run: |", 1)[1].split("\n      - name:", 1)[0]
        code = 'ssh() { bash -c "${@: -1}"; }\n' + textwrap.dedent(step)
        env.update(EXPECTED_SHA=SHA, DEPLOY_USER="test", DEPLOY_HOST="localhost", RUNNER_TEMP=tmp_path.as_posix())
    # Windows truncates a long bash -c command at the process argument limit.
    test_script = tmp_path / "deployment-test.sh"
    test_script.write_text(code, encoding="utf-8", newline="\n")
    result = subprocess.run([bash, test_script.as_posix(), SHA], input="",
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    return result, log.read_text() if log.exists() else ""


@pytest.mark.parametrize("change", ["", "snapshot_change", "identity_change", "auth_change"])
def test_deployment_builds_before_backup_migration_and_checks_running_revision(tmp_path, change):
    result, log = run_deploy(tmp_path, change)
    assert result.returncode == 0, result.stderr + result.stdout
    ordered = ["build psych_quiz_bot psych_quiz_miniapp_api", "deployment_db.py preflight", "stop psych_quiz_bot",
               "deployment_db.py backup", "scripts/init_db.py", "scripts/seed_questions.py", "deployment_db.py verify",
               "deployment_db.py smoke", "up -d --no-build", "deployment_http_smoke.py"]
    positions = [log.index(command) for command in ordered]
    assert positions == sorted(positions)
    assert f"DEPLOY_OK revision={SHA}" in result.stdout
    assert (tmp_path / ".env").read_text() == "BOT_TOKEN=synthetic\n"


@pytest.mark.parametrize('fault', ['pg', 'pg_backup', 'pg_preservation'])
def test_postgres_delivery_requires_native_restore_and_preservation(tmp_path, fault):
    result, log = run_deploy(tmp_path, fault)
    assert 'deployment_db.py backup' not in log
    assert 'postgres_vps.py backup' in log
    if fault == 'pg':
        assert result.returncode == 0, result.stdout + result.stderr
        commands = ['stop psych_quiz_bot', 'postgres_vps.py backup', 'scripts/init_db.py', 'postgres_vps.py verify', 'up -d', 'deployment_http_smoke.py']
        positions = [log.index(value) for value in commands]
        assert positions == sorted(positions)
    else:
        assert result.returncode != 0
        assert 'up -d' not in log and 'DEPLOY_OK' not in result.stdout
        if fault == 'pg_backup': assert 'scripts/init_db.py' not in log


@pytest.mark.parametrize("fault,forbidden", [("lock", "git fetch"), ("dirty", "git fetch"),
        ("stale", "git merge --ff-only"), ("project", "git merge --ff-only"),
        ("build", "deployment_db.py backup"), ("backup", "scripts/init_db.py"),
        ("migration", "up -d"), ("preservation", "up -d"), ("content_parity", "up -d")])
def test_failure_stops_before_dependent_operation(tmp_path, fault, forbidden):
    result, log = run_deploy(tmp_path, fault)
    assert result.returncode != 0
    assert forbidden not in log
    assert "DEPLOY_OK" not in result.stdout
    if fault == "backup":
        assert "start psych_quiz_bot psych_quiz_miniapp_api" in log
    if fault in {"migration", "preservation"}:
        assert "start psych_quiz_bot" not in log


@pytest.mark.parametrize("fault", ["health", "image"])
def test_failed_postcheck_does_not_report_success_or_restore(tmp_path, fault):
    result, log = run_deploy(tmp_path, fault)
    assert result.returncode != 0
    assert "DEPLOY_OK" not in result.stdout
    assert "restore" not in log


def test_documentation_change_only_syncs_source(tmp_path):
    result, log = run_deploy(tmp_path, "docs")
    assert result.returncode == 0, result.stderr
    assert "SOURCE_SYNC_OK" in result.stdout
    assert "build psych_quiz_bot" not in log


def test_first_versioned_image_rehearses_backup_without_unneeded_seed(tmp_path):
    result, log = run_deploy(tmp_path, "first_adoption")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "deployment_db.py backup" in log
    assert "deployment_db.py verify" in log
    assert "scripts/init_db.py" not in log
    assert "scripts/seed_questions.py" not in log


def test_ssh_transport_cannot_lose_script_to_a_child_reading_stdin(tmp_path):
    result, log = run_deploy(tmp_path, through_workflow=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "scripts/init_db.py" in log
    assert "deployment_http_smoke.py" in log
    assert f"DEPLOY_OK revision={SHA}" in result.stdout


def test_workflow_rejects_zero_exit_without_completion_record(tmp_path):
    # A command may end successfully without executing the complete remote procedure.
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
    step = workflow.split("- name: Deploy exact revision over verified SSH", 1)[1]
    step = step.split("run: |", 1)[1].split("\n      - name:", 1)[0]
    (tmp_path / "deploy.sh").write_text("# synthetic script\n", encoding="utf-8")
    env = {**os.environ, "EXPECTED_SHA": SHA, "DEPLOY_USER": "test", "DEPLOY_HOST": "localhost", "RUNNER_TEMP": tmp_path.as_posix()}
    bash = "C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
    result = subprocess.run([bash, "-c", 'ssh() { cat >/dev/null; echo PREFLIGHT_OK; }\n' + textwrap.dedent(step)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
