"""Obtain public assets from the latest trusted main CI; verify before SSH access."""
import argparse
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.check_deploy_candidate import api, validate_records
from scripts.pwa_release import manifest_at, revision

REPOSITORY = "Just9120/psychology-quiz"
MAX_BYTES = 64 * 1024 * 1024  # Transport limit, including uncompressed public files.


def all_records(path, key):
    records = []
    page = 1
    while True:
        response = api(f"{path}?per_page=100&page={page}")
        batch = response[key]
        records.extend(batch)
        if len(records) == response["total_count"]:
            return records
        if not batch or len(records) > response["total_count"]:
            raise ValueError("Incomplete or changing GitHub record listing")
        page += 1


def select_artifact(sha, run, jobs, artifacts):
    if (run["repository"]["full_name"] != REPOSITORY
            or run["head_repository"]["full_name"] != REPOSITORY):
        raise ValueError("Untrusted build repository")
    required = {}
    for name in ("pwa-client", "validate-and-smoke-test"):
        matching = [job for job in jobs if job["name"] == name]
        if (len(matching) != 1 or matching[0]["status"] != "completed"
                or matching[0]["conclusion"] != "success"
                or matching[0]["head_sha"] != sha or matching[0]["run_id"] != run["id"]):
            raise ValueError("Required job was not successful for this revision/attempt")
        required[name] = matching[0]
    matching = [item for item in artifacts if item["name"] == f"pwa-{sha}"]
    if len(matching) != 1:
        raise ValueError("Expected exactly one versioned PWA artifact")
    item = matching[0]
    source = item["workflow_run"]
    if (item["expired"] is not False or not 0 < item["size_in_bytes"] <= MAX_BYTES
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", item.get("digest", ""))
            or source["id"] != run["id"] or source["head_sha"] != sha
            or source["head_branch"] != "main"
            or source["repository_id"] != run["repository"]["id"]
            or source["head_repository_id"] != run["repository"]["id"]):
        raise ValueError("Invalid, expired or untrusted artifact identity")
    # Reruns share a run ID. Never reuse an artifact left by an earlier attempt.
    job = required["pwa-client"]
    parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not parse(job["started_at"]) <= parse(item["created_at"]) <= parse(job["completed_at"]):
        raise ValueError("Artifact does not belong to the validated job attempt")
    return item


def authorize(sha, run_id):
    revision(sha)
    prefix = f"repos/{REPOSITORY}"
    branch = api(f"{prefix}/branches/main")
    runs = api(f"{prefix}/actions/workflows/ci.yml/runs?branch=main&event=push&head_sha={sha}&per_page=1")
    validate_records(sha, branch, runs)
    run = runs["workflow_runs"][0]
    if run["id"] != run_id:
        raise ValueError("The authorized CI run is no longer the latest")
    jobs = all_records(f"{prefix}/actions/runs/{run_id}/attempts/{run['run_attempt']}/jobs", "jobs")
    artifacts = all_records(f"{prefix}/actions/runs/{run_id}/artifacts", "artifacts")
    return select_artifact(sha, run, jobs, artifacts)


def extract_verified(archive, destination, sha, digest):
    revision(sha)
    archive, destination = Path(archive), Path(destination)
    if (not re.fullmatch(r"[0-9a-f]{64}", digest) or archive.is_symlink()
            or not archive.is_file() or archive.stat().st_size > MAX_BYTES):
        raise ValueError("Invalid archive or digest")
    payload = archive.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("Archive digest differs from GitHub")
    # Extract these exact verified bytes, not a second read of a mutable path.
    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        entries = bundle.infolist()
        names = set()
        if len(entries) > 2000 or sum(item.file_size for item in entries) > MAX_BYTES:
            raise ValueError("Oversized public artifact")
        for item in entries:
            name = item.filename.rstrip("/") if item.is_dir() else item.filename
            parts = PurePosixPath(name).parts
            mode = stat.S_IFMT(item.external_attr >> 16)
            if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", name)
                    or item.orig_filename != item.filename
                    or PurePosixPath(name).as_posix() != name
                    or any(part.startswith(".") for part in parts)
                    or name.casefold() in names or item.flag_bits & 1
                    or mode not in (0, stat.S_IFDIR if item.is_dir() else stat.S_IFREG)):
                raise ValueError("Unsafe or duplicate archive path/type")
            names.add(name.casefold())
        destination.mkdir(mode=0o755)
        destination.chmod(0o755)
        for item in entries:
            target = destination / item.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            if item.is_dir():
                target.mkdir(exist_ok=True)
            else:
                with target.open("xb") as stream:
                    stream.write(bundle.read(item))
                target.chmod(0o644)
        for directory in destination.rglob("*"):
            if directory.is_dir():
                directory.chmod(0o755)
    manifest_at(destination, sha)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("download", "check"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    artifact = authorize(args.sha, args.run_id)
    digest = artifact["digest"].removeprefix("sha256:")
    if args.action == "download":
        with args.archive.open("xb") as stream:
            args.archive.chmod(0o600)
            subprocess.run(["gh", "api", f"repos/{REPOSITORY}/actions/artifacts/{artifact['id']}/zip"],
                           stdin=subprocess.DEVNULL, stdout=stream, check=True)
    with tempfile.TemporaryDirectory() as temporary:
        extract_verified(args.archive, Path(temporary) / "artifact", args.sha, digest)
    if args.action == "download":
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"digest={digest}\nartifact_id={artifact['id']}\n")
    print(f"PWA_ARTIFACT_VALIDATED revision={args.sha} ci_run={args.run_id} "
          f"artifact={artifact['id']} digest=sha256:{digest}")


if __name__ == "__main__":
    main()
