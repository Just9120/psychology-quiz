import copy
import os
from pathlib import Path
import shutil
import subprocess

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
    'diff --name-only '*) if [[ "$FAULT" == docs ]]; then echo README.md; else echo app/db.py; fi ;;
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
        if [[ "$DEPLOY_STARTED" == 1 && "$FAULT" != image ]]; then echo "$EXPECTED"; else echo "$OLD"; fi ;;
      *Image*) echo sha256:test-image ;;
    esac
    return
  fi
  shift 7
  if [[ "$1 $2" == 'ps -q' ]]; then echo "$3"; return; fi
  case "$*" in
    build*) [[ "$FAULT" != build ]] ;;
    *deployment_db.py\ backup) [[ "$FAULT" != backup ]] || return 2; echo /data/backups/release-test/quiz.sqlite3 ;;
    *scripts/init_db.py) [[ "$FAULT" != migration ]] ;;
    *deployment_db.py\ verify*) [[ "$FAULT" != preservation ]] ;;
    up*) DEPLOY_STARTED=1 ;;
    *deployment_http_smoke.py) [[ "$FAULT" != health ]] ;;
    *) return 0 ;;
  esac
}
'''


def run_deploy(tmp_path, fault=""):
    bash = ("C:/Program Files/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash"))
    assert bash and Path(bash).exists(), "Bash is required for deployment behavior tests"
    (tmp_path / ".env").write_text("BOT_TOKEN=synthetic\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    log = tmp_path / "commands.log"
    env = {**os.environ, "COMMAND_LOG": log.as_posix(), "FAULT": fault, "OLD": OLD, "EXPECTED": SHA}
    env.pop("DOCKER_HOST", None)
    env.pop("COMPOSE_FILE", None)
    script = Path("deploy.sh").read_text(encoding="utf-8")
    result = subprocess.run([bash, "-c", BOUNDARIES + "\n" + script, "deploy-test", SHA],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    return result, log.read_text() if log.exists() else ""


def test_deployment_builds_before_backup_migration_and_checks_running_revision(tmp_path):
    result, log = run_deploy(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    ordered = ["build psych_quiz_bot psych_quiz_miniapp_api", "deployment_db.py preflight", "stop psych_quiz_bot",
               "deployment_db.py backup", "scripts/init_db.py", "scripts/seed_questions.py", "deployment_db.py verify",
               "deployment_db.py smoke", "up -d --no-build", "deployment_http_smoke.py"]
    positions = [log.index(command) for command in ordered]
    assert positions == sorted(positions)
    assert f"DEPLOY_OK revision={SHA}" in result.stdout
    assert (tmp_path / ".env").read_text() == "BOT_TOKEN=synthetic\n"


@pytest.mark.parametrize("fault,forbidden", [("lock", "git fetch"), ("dirty", "git fetch"),
        ("stale", "git merge --ff-only"), ("project", "git merge --ff-only"),
        ("build", "deployment_db.py backup"), ("backup", "scripts/init_db.py"),
        ("migration", "up -d"), ("preservation", "up -d")])
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
