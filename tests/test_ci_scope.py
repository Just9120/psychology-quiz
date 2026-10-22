import subprocess

import pytest

from scripts.ci_scope import changed_paths, documentation_only


@pytest.mark.parametrize("paths,expected", [
    (["README.md", "AGENTS.md", "ci-cd-rules.md", "docs/project-spec.md"], True),
    (["docs/new-supporting-procedure.md"], True), ([], False),
    (["docs/project-spec.md", "app/main.py"], False),
    (["content/vault-notes.json"], False), (["vault/generated/Note.md"], False),
    (["requirements-bootstrap.lock"], False), ([".github/workflows/ci.yml"], False),
    (["docs/../app/main.md"], False), (["unknown.md"], False), (["docs/config.json"], False),
])
def test_only_explicit_non_runtime_documentation_can_skip_regressions(paths, expected):
    assert documentation_only(paths) is expected


def test_code_renamed_into_documentation_still_requires_runtime_checks(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args]).decode().strip()
    git("init", "-q")
    git("config", "user.name", "Synthetic CI test")
    git("config", "user.email", "ci@example.test")
    (tmp_path / "app").mkdir()
    (tmp_path / "app/main.py").write_text("synthetic code\n")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "docs").mkdir()
    git("mv", "app/main.py", "docs/example.md")
    git("commit", "-qm", "rename")
    paths = changed_paths(base, root=tmp_path)
    assert set(paths) == {"app/main.py", "docs/example.md"}
    assert not documentation_only(paths)
    with pytest.raises(ValueError, match="exact_ci_base_required"):
        changed_paths("HEAD~1", root=tmp_path)
