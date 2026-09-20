"""PWA portion of the existing locked VPS deployment; no bootstrap or DB writes."""
import argparse
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.pwa_artifact import extract_verified
from scripts.pwa_release import activate, current_revision, release_root, revision, stage
from scripts.pwa_smoke import smoke

SITE_ROOT = Path("/var/www/psychology-atlas")
ORIGIN = "https://psy.cloud-nodes.net"


def needs_static(paths):
    # Compare the actually published revision with the candidate, not host HEAD.
    # Tests/docs alone need no new static release; unknown build files fail broad.
    return any(path == ".github/workflows/ci.yml" or (
        path.startswith("pwa/") and not path.startswith(("pwa/tests/", "pwa/e2e/"))
        and not path.endswith(".md")) for path in paths)


def prepare(archive, sha, digest, *, root=SITE_ROOT):
    root = release_root(root)
    previous = current_revision(root)
    if previous == "NONE":
        raise ValueError("Existing PWA activation required; CD does not bootstrap")
    with tempfile.TemporaryDirectory() as temporary:
        artifact = extract_verified(archive, Path(temporary) / "artifact", sha, digest)
        subprocess.run(["git", "merge-base", "--is-ancestor", previous, sha],
                       stdin=subprocess.DEVNULL, check=True)
        paths = subprocess.check_output(["git", "diff", "--name-only", previous, sha],
                                        stdin=subprocess.DEVNULL, text=True).splitlines()
        target = sha if needs_static(paths) or previous == sha else previous
        if target == sha:
            stage(artifact, root, sha)
    return previous, target


def publish(sha, previous, target, *, root=SITE_ROOT, origin=ORIGIN):
    for value in (sha, previous, target):
        revision(value)
    root = release_root(root)
    if target not in (sha, previous):
        raise ValueError("Unexpected static target")
    if target == sha:
        activate(root, target, previous)
    elif current_revision(root) != previous:
        raise ValueError("Current release changed during deployment")
    smoke(origin, root / "releases" / target, target)
    print(f"PWA_DELIVERY_OK revision={target} source={sha} previous={previous}")


def private_archive(path):
    # The workflow creates one private temporary directory and transfers one ZIP.
    if not re.fullmatch(r"/tmp/psychology-pwa\.[A-Za-z0-9]{8}/artifact\.zip", str(path)):
        raise ValueError("Unexpected incoming archive path")
    for candidate, kind, mode in ((path.parent, stat.S_ISDIR, 0o700), (path, stat.S_ISREG, 0o600)):
        info = candidate.lstat()
        if not kind(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != mode:
            raise ValueError("Incoming artifact must be private and owned by deploy identity")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "publish"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--digest")
    parser.add_argument("--previous")
    parser.add_argument("--target")
    args = parser.parse_args()
    revision(args.sha)
    if args.action == "prepare":
        if args.archive is None or args.digest is None:
            parser.error("prepare requires archive and digest")
        private_archive(args.archive)
        print(*prepare(args.archive, args.sha, args.digest))
    else:
        publish(args.sha, args.previous, args.target)


if __name__ == "__main__":
    main()
