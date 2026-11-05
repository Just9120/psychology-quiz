import subprocess

import pytest

from scripts.ci_scope import changed_paths, documentation_only, dependency_lock


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


@pytest.mark.parametrize('decision,expected', [(False, 'requirements.lock'),
    (True, 'requirements-dev.lock'), (None, 'requirements-dev.lock'),
    ('false', 'requirements-dev.lock')])
def test_only_explicit_docs_selection_omits_unused_development_toolchain(decision, expected):
    assert dependency_lock(decision) == expected


def test_selected_lock_retains_every_runtime_pin_and_hash():
    from pathlib import Path
    import re
    def entries(path):
        text = Path(path).read_text(encoding='utf-8')
        return {match[1]: (match[2], set(re.findall(r'sha256:([a-f0-9]{64})', match[3])))
                for match in re.finditer(r'(?ms)^([a-z0-9_.-]+)==([^\s]+)(.*?)(?=^[a-z0-9_.-]+==|\Z)', text)}
    runtime, dev = entries('requirements.lock'), entries('requirements-dev.lock')
    assert runtime and all(dev.get(name) == value and value[1] for name, value in runtime.items())
    assert set(dev) - set(runtime) == {'pytest', 'iniconfig', 'packaging', 'pluggy', 'pygments'}


@pytest.mark.parametrize('lock,expected', [('', 'requirements-dev.lock'),
    ('requirements-dev.lock', 'requirements-dev.lock'), ('requirements.lock', 'requirements.lock'),
    ('untrusted.lock', None)])
def test_real_workflow_install_step_preserves_hashes_and_fails_closed(lock, expected):
    import os
    from pathlib import Path
    import shutil
    import textwrap
    workflow = Path('.github/workflows/ci.yml').read_text(encoding='utf-8')
    step = workflow.split('- name: Install dependencies', 1)[1]
    step = step.split('- name: Behavioral regression suite', 1)[0].split('run: |', 1)[1]
    bash = 'C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else shutil.which('bash')
    assert bash, 'Bash is required on the Linux CI runner'
    if os.name == 'nt':
        probe = subprocess.run([bash, '-c', ':'], capture_output=True, text=True, timeout=15)
        if probe.returncode and 'not found' in probe.stderr:
            pytest.skip('Local Windows Git Bash runtime missing; real shell test remains required in Linux CI')
    # The actual shell executes; its package boundary records commands instead
    # of downloading or installing anything in the test environment.
    script = 'python() { printf "PACKAGE_COMMAND %s\\n" "$*"; }\n' + textwrap.dedent(step)
    result = subprocess.run([bash, '-c', script], capture_output=True, text=True, timeout=15,
                            env={**os.environ, 'DEPENDENCY_LOCK': lock})
    if expected is None:
        assert result.returncode != 0 and 'PACKAGE_COMMAND' not in result.stdout
        assert 'Unknown dependency selection' in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == [
            'PACKAGE_COMMAND -m pip install --require-hashes -r requirements-bootstrap.lock',
            'PACKAGE_COMMAND -m pip install --require-hashes -r ' + expected]
