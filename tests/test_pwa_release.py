from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.pwa_release import activate, current_revision, manifest_at, release_lock, stage, REQUIRED, MARKER

FIRST = "a" * 40
SECOND = "b" * 40
THIRD = "c" * 40


def make_artifact(path, sha=FIRST):
    path.mkdir()
    hashes = {}
    for name in sorted(REQUIRED | {"assets/app.js", "assets/app.css"}):
        target = path / name
        target.parent.mkdir(exist_ok=True)
        target.write_text(sha + name, encoding="utf-8")
        hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (path / "build.json").write_text(json.dumps({"revision": sha, "dirty": False, "files": hashes}))
    return path


@pytest.fixture
def artifact(tmp_path):
    return make_artifact(tmp_path / "artifact")


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "site"
    path.mkdir()
    (path / ".pwa-root").write_text(MARKER)
    return path


def need_symlinks(tmp_path):
    probe = tmp_path / "probe"
    try:
        probe.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        if os.name == "nt":
            pytest.skip("Windows symlink privilege unavailable; Linux CI is required")
        raise
    probe.unlink()


@pytest.mark.parametrize("mutation", ["changed", "missing", "extra", "dirty", "revision", "digest", "duplicate", "traversal"])
def test_rejects_untrusted_or_damaged_artifact(artifact, mutation):
    path = artifact / "build.json"
    data = json.loads(path.read_text())
    if mutation == "changed": (artifact / "index.html").write_text("changed")
    elif mutation == "missing": (artifact / "sw.js").unlink()
    elif mutation == "extra": (artifact / "private.env").write_text("synthetic only")
    elif mutation == "dirty": data["dirty"] = True
    elif mutation == "revision": data["revision"] = SECOND
    elif mutation == "digest": data["files"]["index.html"] = "invalid"
    elif mutation == "traversal": data["files"]["../outside"] = "0" * 64
    if mutation == "duplicate":
        path.write_text('{"revision":"' + FIRST + '",' + json.dumps(data)[1:])
    else:
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        manifest_at(artifact, FIRST)


def test_staging_is_verified_idempotent_and_never_overwrites_immutable_release(artifact, root):
    first = stage(artifact, root, FIRST)
    original = (first / "index.html").read_bytes()
    assert stage(artifact, root, FIRST) == first
    assert current_revision(root) == "NONE"
    data = manifest_at(artifact, FIRST)
    (artifact / "index.html").write_text("different but valid content")
    data["files"]["index.html"] = hashlib.sha256((artifact / "index.html").read_bytes()).hexdigest()
    (artifact / "build.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="immutable"):
        stage(artifact, root, FIRST)
    assert (first / "index.html").read_bytes() == original


def test_existing_lock_and_unmarked_root_fail_closed(artifact, root):
    with release_lock(root):
        with pytest.raises(FileExistsError):
            stage(artifact, root, FIRST)
        assert (root / ".release.lock").exists()
    (root / ".pwa-root").write_text("some other site")
    with pytest.raises(ValueError, match="marker"):
        stage(artifact, root, FIRST)


def test_atomic_activation_cas_retry_and_explicit_static_rollback(artifact, root, tmp_path):
    need_symlinks(tmp_path)
    stage(artifact, root, FIRST)
    stage(make_artifact(tmp_path / "next", SECOND), root, SECOND)
    assert activate(root, FIRST, "NONE") == "NONE"
    assert activate(root, FIRST, "NONE") == FIRST
    with pytest.raises(ValueError, match="changed"):
        activate(root, SECOND, "NONE")
    assert current_revision(root) == FIRST
    assert activate(root, SECOND, FIRST) == FIRST
    assert current_revision(root) == SECOND
    assert (root / "releases" / FIRST / "index.html").exists()
    assert activate(root, FIRST, SECOND) == SECOND
    assert current_revision(root) == FIRST
    assert not list(root.glob(".current-*"))


def test_tampered_next_release_preserves_current_pointer(artifact, root, tmp_path):
    need_symlinks(tmp_path)
    stage(artifact, root, FIRST)
    activate(root, FIRST, "NONE")
    second = stage(make_artifact(tmp_path / "next", SECOND), root, SECOND)
    (second / "sw.js").write_text("tampered")
    with pytest.raises(ValueError, match="checksum"):
        activate(root, SECOND, FIRST)
    assert current_revision(root) == FIRST


def test_external_links_and_regular_current_are_preserved_and_rejected(artifact, root, tmp_path):
    need_symlinks(tmp_path)
    outside = tmp_path / "outside"
    outside.write_text("untouched")
    (artifact / "icon.svg").unlink()
    (artifact / "icon.svg").symlink_to(outside)
    with pytest.raises(ValueError, match="link"):
        manifest_at(artifact, FIRST)
    (root / "current").write_text("unrelated")
    with pytest.raises(ValueError, match="symlink"):
        current_revision(root)
    assert (root / "current").read_text() == "unrelated"
    assert outside.read_text() == "untouched"


def test_two_activations_cannot_replace_each_others_revision(artifact, root, tmp_path):
    need_symlinks(tmp_path)
    stage(artifact, root, FIRST)
    stage(make_artifact(tmp_path / "second", SECOND), root, SECOND)
    stage(make_artifact(tmp_path / "third", THIRD), root, THIRD)
    activate(root, FIRST, "NONE")
    def attempt(sha):
        try:
            activate(root, sha, FIRST)
            return True
        except (ValueError, FileExistsError):
            return False
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(attempt, [SECOND, THIRD])) == 1
    assert current_revision(root) in {SECOND, THIRD}
