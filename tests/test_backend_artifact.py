import gzip
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts import backend_artifact as subject
from scripts.pwa_artifact import select_artifact
from tests.test_pwa_artifact import primary_records, FIRST

ID = "sha256:" + "a" * 64


def bundle(tmp_path, **overrides):
    image = gzip.compress(b"synthetic docker image", mtime=0)
    manifest = {"schema_version": 1, "revision": FIRST, "tag": subject.tag(FIRST), "image_id": ID,
                "platform": "linux/amd64", "image_sha256": hashlib.sha256(image).hexdigest()}
    manifest.update(overrides)
    archive = tmp_path / "backend.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        output.writestr("image.tar.gz", image)
    return archive, subject.digest(archive)


def test_backend_selection_uses_its_own_successful_producer_attempt():
    run, jobs, artifacts = primary_records()
    artifacts[0]["name"] = "backend-" + FIRST
    jobs[0]["completed_at"] = "2026-09-20T12:00:30Z"
    assert select_artifact(FIRST, run, jobs, artifacts, kind="backend")["id"] == 30
    jobs[1]["started_at"] = "2026-09-20T12:01:30Z"
    with pytest.raises(ValueError, match="validated job attempt"):
        select_artifact(FIRST, run, jobs, artifacts, kind="backend")


@pytest.mark.parametrize("mutation", [{"revision": "b" * 40}, {"image_sha256": "c" * 64}, {"platform": "linux/arm64"}, {"image_id": []}])
def test_corrupt_or_wrong_identity_never_reaches_docker(tmp_path, monkeypatch, mutation):
    archive, digest = bundle(tmp_path, **mutation)
    monkeypatch.setattr(subject.subprocess, "run", lambda *args, **kwargs: pytest.fail("unverified load reached Docker"))
    with pytest.raises(ValueError):
        subject.load(archive, FIRST, digest)


def test_archive_digest_and_path_injection_refused_before_extraction(tmp_path):
    archive, digest = bundle(tmp_path)
    with pytest.raises(ValueError, match="differs from GitHub"):
        subject.verify(archive, tmp_path / "out", FIRST, "b" * 64)
    assert not (tmp_path / "out").exists()
    with zipfile.ZipFile(archive, "a") as output:
        output.writestr("../intruder", b"unsafe")
    with pytest.raises(ValueError, match="layout"):
        subject.verify(archive, tmp_path / "out", FIRST, subject.digest(archive))
    assert not (tmp_path / "intruder").exists()


def test_load_requires_actual_loaded_image_id_platform_and_revision(tmp_path, monkeypatch):
    archive, digest = bundle(tmp_path)
    calls = []
    monkeypatch.setattr(subject.subprocess, "run", lambda args, **kwargs: calls.append(args))
    actual = {"Id": ID, "Os": "linux", "Architecture": "amd64", "Config": {"Labels": {"org.opencontainers.image.revision": FIRST}}}
    monkeypatch.setattr(subject.subprocess, "check_output", lambda args, **kwargs: "linux/amd64" if args[1] == "version" else json.dumps([actual]))
    assert subject.load(archive, FIRST, digest)["image_id"] == ID
    assert calls[0][:3] == ["docker", "image", "load"]
    actual["Id"] = "sha256:" + "c" * 64
    with pytest.raises(ValueError, match="identity/platform/revision"):
        subject.load(archive, FIRST, digest)


def test_wrong_target_platform_refused_before_image_load(tmp_path, monkeypatch):
    archive, digest = bundle(tmp_path)
    monkeypatch.setattr(subject.subprocess, "check_output", lambda *args, **kwargs: "linux/arm64")
    monkeypatch.setattr(subject.subprocess, "run", lambda *args, **kwargs: pytest.fail("unsupported target reached load"))
    with pytest.raises(ValueError, match="target Docker platform"):
        subject.load(archive, FIRST, digest)
