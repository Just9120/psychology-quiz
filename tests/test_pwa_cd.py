import os
from pathlib import Path
import stat
import subprocess

import pytest

from scripts import pwa_cd
from scripts.pwa_release import activate, current_revision, stage, MARKER
from tests.test_pwa_artifact import archive_for
from tests.test_pwa_release import make_artifact, need_symlinks, FIRST


@pytest.mark.parametrize("paths,expected", [
    (["README.md", "docs/pwa-delivery.md", "pwa/README.md"], False),
    (["app/web_api.py", "tests/test_pwa_cd.py", "pwa/tests/quiz.spec.ts"], False),
    (["pwa/src/App.tsx"], True), (["pwa/package-lock.json"], True),
    (["pwa/public/sw.js"], True), (["pwa/new-build.config.js"], True), ([], False),
    ([".github/workflows/ci.yml"], True),
])
def test_static_selection_uses_component_build_inputs(paths, expected):
    assert pwa_cd.needs_static(paths) is expected


def test_cd_requires_existing_pwa_without_bootstrapping(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / ".pwa-root").write_text(MARKER)
    with pytest.raises(ValueError, match="bootstrap"):
        pwa_cd.prepare(tmp_path / "unused.zip", FIRST, "a" * 64, root=root)
    assert not (root / "releases").exists()


@pytest.fixture
def deployed(tmp_path, monkeypatch):
    need_symlinks(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    def git(*args):
        return subprocess.check_output(["git", "-c", "user.name=Synthetic Test", "-c", "user.email=test@example.test",
                                        *args], cwd=repo, stdin=subprocess.DEVNULL, text=True).strip()
    git("init", "-q")
    (repo / "pwa").mkdir()
    (repo / "pwa/index.html").write_text("initial")
    git("add", ".")
    git("commit", "-qm", "initial")
    previous = git("rev-parse", "HEAD")
    root = tmp_path / "site"
    root.mkdir()
    (root / ".pwa-root").write_text(MARKER)
    stage(make_artifact(tmp_path / "old", previous), root, previous)
    activate(root, previous, "NONE")
    return root, previous, repo, git


@pytest.mark.parametrize("changed,expected_update", [("pwa/index.html", True), ("README.md", False)])
def test_real_git_delta_stage_activate_and_retry_preserve_releases(tmp_path, monkeypatch, deployed, changed, expected_update):
    root, previous, repo, git = deployed
    (repo / changed).write_text("next")
    git("add", ".")
    git("commit", "-qm", "next")
    sha = git("rev-parse", "HEAD")
    archive, digest = archive_for(tmp_path, sha)
    old_umask = os.umask(0o077)
    try:
        observed, target = pwa_cd.prepare(archive, sha, digest, root=root)
    finally:
        os.umask(old_umask)
    assert observed == previous
    assert target == (sha if expected_update else previous)
    assert current_revision(root) == previous  # Stage cannot publish before backend gates.
    checked = []
    def smoke(origin, artifact, expected):
        assert current_revision(root) == expected
        assert artifact == root / "releases" / expected
        checked.append(expected)
    monkeypatch.setattr(pwa_cd, "smoke", smoke)
    pwa_cd.publish(sha, previous, target, root=root)
    pwa_cd.publish(sha, previous, target, root=root)
    assert current_revision(root) == target and checked == [target, target]
    assert (root / "releases" / previous / "index.html").exists()
    if os.name != "nt" and expected_update:
        assert stat.S_IMODE((root / "releases" / sha).stat().st_mode) == 0o755
        assert stat.S_IMODE((root / "releases" / sha / "assets").stat().st_mode) == 0o755
        assert stat.S_IMODE((root / "releases" / sha / "index.html").stat().st_mode) == 0o644


def test_failed_public_smoke_is_failure_without_implicit_rollback(tmp_path, monkeypatch, deployed):
    root, previous, repo, git = deployed
    (repo / "pwa/index.html").write_text("next")
    git("add", ".")
    git("commit", "-qm", "next")
    sha = git("rev-parse", "HEAD")
    archive, digest = archive_for(tmp_path, sha)
    pwa_cd.prepare(archive, sha, digest, root=root)
    def fail(*args):
        raise ValueError("Public version mismatch")
    monkeypatch.setattr(pwa_cd, "smoke", fail)
    with pytest.raises(ValueError, match="Public version"):
        pwa_cd.publish(sha, previous, sha, root=root)
    assert current_revision(root) == sha
    assert (root / "releases" / previous).is_dir()


def test_stale_pointer_cannot_be_published(tmp_path, monkeypatch, deployed):
    root, previous, repo, git = deployed
    stage(make_artifact(tmp_path / "other", FIRST), root, FIRST)
    activate(root, FIRST, previous)
    monkeypatch.setattr(pwa_cd, "smoke", lambda *args: pytest.fail("Cannot smoke an unvalidated pointer"))
    with pytest.raises(ValueError, match="changed"):
        pwa_cd.publish("b" * 40, previous, previous, root=root)
    assert current_revision(root) == FIRST
