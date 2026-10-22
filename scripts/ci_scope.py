"""Keep required CI jobs active; skip runtime regressions only for pure documentation changes."""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ROOT_DOCS = {"README.md", "AGENTS.md", "ci-cd-rules.md"}


def documentation_only(paths):
    def allowed(name):
        path = PurePosixPath(name)
        return (not path.is_absolute() and ".." not in path.parts and "\\" not in name
                and (name in ROOT_DOCS or (path.parts[0] == "docs" and path.suffix == ".md")))
    return bool(paths) and all(name and allowed(name) for name in paths)


def changed_paths(base, *, root=ROOT):
    if not re.fullmatch(r"[0-9a-f]{40}", base):
        raise ValueError("exact_ci_base_required")
    # Treat a rename as deletion plus addition: moving code into docs is a runtime change.
    return subprocess.check_output(["git", "-C", str(root), "diff", "--no-renames", "--name-only",
                                    "-z", base, "HEAD"]).decode().strip("\0").split("\0")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    base = os.environ.get("PR_BASE") or os.environ.get("PUSH_BASE")
    if not base or base == "0" * 40:
        base = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD^"]).decode().strip()
    paths = changed_paths(base)
    required = os.environ.get("CI_EVENT") == "workflow_dispatch" or not documentation_only(paths)
    with args.github_output.open("a", encoding="utf-8") as output:
        output.write(f"runtime_checks={'true' if required else 'false'}\n")
    print("CI_SCOPE_RUNTIME_REQUIRED" if required else "CI_SCOPE_DOCUMENTATION_ONLY")


if __name__ == "__main__":
    main()
