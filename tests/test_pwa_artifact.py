import copy
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import stat
import zipfile

import pytest

from scripts import pwa_artifact as subject
from tests.test_pwa_release import make_artifact, FIRST


def primary_records():
    repo = {"id": 1, "full_name": subject.REPOSITORY}
    run = {"id": 12, "repository": repo, "head_repository": repo, "run_attempt": 2}
    jobs = [{"name": name, "status": "completed", "conclusion": "success", "head_sha": FIRST,
             "run_id": 12, "started_at": "2026-09-20T12:00:00Z", "completed_at": "2026-09-20T12:02:00Z"}
            for name in ("pwa-client", "validate-and-smoke-test")]
    artifacts = [{"id": 30, "name": f"pwa-{FIRST}", "expired": False, "size_in_bytes": 123,
                  "digest": "sha256:" + "d" * 64, "created_at": "2026-09-20T12:01:00Z",
                  "workflow_run": {"id": 12, "head_sha": FIRST, "head_branch": "main",
                                   "repository_id": 1, "head_repository_id": 1}}]
    return run, jobs, artifacts


def test_selects_exact_current_attempt_artifact():
    run, jobs, artifacts = primary_records()
    assert subject.select_artifact(FIRST, run, jobs, artifacts)["id"] == 30


@pytest.mark.parametrize("failure", ["fork", "skipped", "missing-job", "duplicate-job", "wrong-job-sha",
    "expired", "missing-digest", "wrong-artifact-sha", "wrong-artifact-run", "foreign-artifact", "old-attempt",
    "missing-artifact", "duplicate-artifact", "oversized"])
def test_rejects_untrusted_or_incomplete_records(failure):
    run, jobs, artifacts = copy.deepcopy(primary_records())
    if failure == "fork": run["head_repository"] = {"full_name": "fork/repo"}
    elif failure == "skipped": jobs[0]["conclusion"] = "skipped"
    elif failure == "missing-job": jobs.pop()
    elif failure == "duplicate-job": jobs.append(jobs[0])
    elif failure == "wrong-job-sha": jobs[0]["head_sha"] = "b" * 40
    elif failure == "expired": artifacts[0]["expired"] = True
    elif failure == "missing-digest": artifacts[0].pop("digest")
    elif failure == "wrong-artifact-sha": artifacts[0]["workflow_run"]["head_sha"] = "b" * 40
    elif failure == "wrong-artifact-run": artifacts[0]["workflow_run"]["id"] = 13
    elif failure == "foreign-artifact": artifacts[0]["workflow_run"]["head_repository_id"] = 2
    elif failure == "old-attempt": artifacts[0]["created_at"] = "2026-09-20T11:59:00Z"
    elif failure == "missing-artifact": artifacts.clear()
    elif failure == "duplicate-artifact": artifacts.append(artifacts[0])
    elif failure == "oversized": artifacts[0]["size_in_bytes"] = subject.MAX_BYTES + 1
    with pytest.raises(ValueError):
        subject.select_artifact(FIRST, run, jobs, artifacts)


def test_pagination_requires_complete_listing(monkeypatch):
    calls = []
    def api(path):
        calls.append(path)
        return {"total_count": 2, "jobs": [{"id": len(calls)}]}
    monkeypatch.setattr(subject, "api", api)
    assert subject.all_records("records", "jobs") == [{"id": 1}, {"id": 2}]
    assert calls[-1].endswith("page=2")
    monkeypatch.setattr(subject, "api", lambda path: {"total_count": 2, "jobs": []})
    with pytest.raises(ValueError, match="Incomplete"):
        subject.all_records("records", "jobs")


def archive_for(tmp_path, sha=FIRST):
    artifact = make_artifact(tmp_path / "source", sha)
    archive = tmp_path / "artifact.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in artifact.rglob("*"):
            if path.is_file(): bundle.write(path, path.relative_to(artifact).as_posix())
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_exact_zip_bytes_are_verified_and_extracted(tmp_path):
    archive, digest = archive_for(tmp_path)
    target = subject.extract_verified(archive, tmp_path / "unpacked", FIRST, digest)
    assert json.loads((target / "build.json").read_text())["revision"] == FIRST
    assert (target / "assets/app.js").read_bytes() == (tmp_path / "source/assets/app.js").read_bytes()
    with pytest.raises(ValueError, match="digest"):
        subject.extract_verified(archive, tmp_path / "tampered", FIRST, "f" * 64)
    assert not (tmp_path / "tampered").exists()


@pytest.mark.parametrize("path,mode", [("../outside", stat.S_IFREG), ("/outside", stat.S_IFREG),
    ("assets/../../outside", stat.S_IFREG), ("link", stat.S_IFLNK), ("pipe", stat.S_IFIFO),
    (".env", stat.S_IFREG), ("assets\\outside", stat.S_IFREG), ("index.html", stat.S_IFREG)])
def test_archive_paths_types_and_duplicates_cannot_escape(tmp_path, path, mode):
    archive, _ = archive_for(tmp_path)
    with zipfile.ZipFile(archive, "a") as bundle:
        item = zipfile.ZipInfo(path)
        item.filename = path  # Preserve raw ZIP separators even on Windows.
        item.external_attr = (mode | 0o777) << 16
        with pytest.warns(UserWarning) if path == "index.html" else nullcontext():
            bundle.writestr(item, "untrusted")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="Unsafe"):
        subject.extract_verified(archive, tmp_path / "unpacked", FIRST, digest)
    assert not (tmp_path / "unpacked").exists()
    assert not (tmp_path / "outside").exists()


def test_authorize_rechecks_latest_primary_records_before_transfer(monkeypatch):
    run, jobs, artifacts = primary_records()
    run.update(head_sha=FIRST, head_branch="main", event="push", status="completed",
               conclusion="success", path=".github/workflows/ci.yml")
    calls = []
    def api(path):
        calls.append(path)
        if path.endswith("branches/main"): return {"commit": {"sha": FIRST}}
        if "workflows/ci.yml/runs" in path: return {"workflow_runs": [run]}
        if "/attempts/2/jobs" in path: return {"total_count": len(jobs), "jobs": jobs}
        if "/artifacts" in path: return {"total_count": len(artifacts), "artifacts": artifacts}
        pytest.fail(path)
    monkeypatch.setattr(subject, "api", api)
    assert subject.authorize(FIRST, 12)["id"] == 30
    assert any("/attempts/2/jobs" in path for path in calls)
    run["conclusion"] = "failure"
    with pytest.raises(ValueError, match="Latest"):
        subject.authorize(FIRST, 12)
    run["conclusion"] = "success"
    with pytest.raises(ValueError, match="latest"):
        subject.authorize(FIRST, 11)
