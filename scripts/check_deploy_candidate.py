"""Validate the primary GitHub CI record before allowing access to SSH secrets."""
import json
import os
import re
import subprocess
import sys


def select_candidate(event: dict, event_name: str, repository: str, sha: str, ref: str = "") -> str:
    if repository != "Just9120/psychology-quiz":
        raise ValueError("Unexpected repository")
    if event_name == "workflow_run":
        run = event["workflow_run"]
        if (run["conclusion"] != "success" or run["event"] != "push"
                or run["head_branch"] != "main"
                or run["head_repository"]["full_name"] != repository):
            raise ValueError("Untrusted or unsuccessful triggering run")
        sha = run["head_sha"]
    elif event_name != "workflow_dispatch" or ref != "refs/heads/main":
        raise ValueError("Only trusted main CI or manual main delivery is allowed")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Invalid candidate SHA")
    return sha


def validate_records(sha: str, branch: dict, runs: dict) -> None:
    if branch["commit"]["sha"] != sha:
        raise ValueError("Stale candidate: newer main exists")
    records = runs["workflow_runs"]
    # API returns newest first. Later failed/in-progress runs forbid older green reuse.
    if not records:
        raise ValueError("No CI record for this revision")
    run = records[0]
    if (run["head_sha"] != sha or run["head_branch"] != "main"
            or run["event"] != "push" or run["status"] != "completed"
            or run["conclusion"] != "success" or run["path"] != ".github/workflows/ci.yml"
            or run["repository"]["full_name"] != "Just9120/psychology-quiz"):
        raise ValueError("Latest exact-revision CI is not successful and trusted")


def api(path: str) -> dict:
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))


def main() -> None:
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as stream:
        event = json.load(stream)
    repository = os.environ["GITHUB_REPOSITORY"]
    sha = select_candidate(event, os.environ["GITHUB_EVENT_NAME"], repository,
                           os.environ["GITHUB_SHA"], os.environ["GITHUB_REF"])
    branch = api(f"repos/{repository}/branches/main")
    runs = api(f"repos/{repository}/actions/workflows/ci.yml/runs?branch=main&event=push&head_sha={sha}&per_page=1")
    validate_records(sha, branch, runs)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
        stream.write(f"sha={sha}\n")
    print(f"CANDIDATE_VALIDATED revision={sha} ci_run={runs['workflow_runs'][0]['id']}")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError) as error:
        sys.exit(str(error))
