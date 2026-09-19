"""Opt-in public static releases. No host bootstrap, DB operations or automatic cleanup."""
from contextlib import contextmanager
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import uuid

SHA = re.compile(r"[0-9a-f]{40}")
HASH = re.compile(r"[0-9a-f]{64}")
REQUIRED = {"index.html", "manifest.webmanifest", "sw.js", "offline.html", "icon.svg",
            "icons/icon-192.png", "icons/icon-512.png", "icons/maskable-512.png", "icons/apple-touch-icon.png"}
MARKER = "psychology-atlas-pwa"


def revision(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("Expected a full lowercase commit SHA")
    return value


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate manifest key")
        result[key] = value
    return result


def manifest_at(directory, expected):
    revision(expected)
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Artifact must be a regular directory")
    actual = set()
    for path in directory.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Artifact contains a link or special file")
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
    data = json.loads((directory / "build.json").read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    if data.get("revision") != expected or data.get("dirty") is not False:
        raise ValueError("Wrong revision or dirty artifact")
    files = data.get("files")
    if not isinstance(files, dict) or not REQUIRED.issubset(files):
        raise ValueError("Incomplete public artifact")
    if actual != set(files) | {"build.json"}:
        raise ValueError("Unexpected or missing artifact files")
    for name, expected_hash in files.items():
        parts = PurePosixPath(name).parts
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", name)
                or any(part in {".", ".."} or part.startswith(".") for part in parts)
                or PurePosixPath(name).as_posix() != name or name == "build.json"
                or not isinstance(expected_hash, str) or not HASH.fullmatch(expected_hash)):
            raise ValueError("Invalid asset path or digest")
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected_hash:
            raise ValueError("Artifact checksum mismatch")
    return data


def release_root(root):
    root = Path(root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir() or root.parent == root:
        raise ValueError("An existing dedicated absolute release root is required")
    marker = root / ".pwa-root"
    if marker.is_symlink() or marker.read_text(encoding="utf-8").strip() != MARKER:
        raise ValueError("Release root marker does not match this application")
    releases = root / "releases"
    if releases.is_symlink() or (releases.exists() and not releases.is_dir()):
        raise ValueError("Invalid releases directory")
    return root


@contextmanager
def release_lock(root):
    root = release_root(root)
    lock = root / ".release.lock"
    # Existing/stale locks fail closed. Only this invocation's lock is removed.
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        yield root
    finally:
        os.close(fd)
        lock.unlink()


def stage(artifact, root, expected):
    manifest = manifest_at(artifact, expected)
    with release_lock(root) as root:
        releases = root / "releases"
        releases.mkdir(exist_ok=True)
        target = releases / expected
        if target.exists() or target.is_symlink():
            if manifest_at(target, expected) != manifest:
                raise ValueError("An immutable release with different content already exists")
            return target
        with tempfile.TemporaryDirectory(dir=releases, prefix=".stage-") as temporary:
            candidate = Path(temporary) / "artifact"
            shutil.copytree(artifact, candidate, symlinks=True)
            if manifest_at(candidate, expected) != manifest:
                raise ValueError("Artifact changed during staging")
            candidate.rename(target)
        return target


def current_revision(root):
    current = root / "current"
    if not current.exists() and not current.is_symlink():
        return "NONE"
    if not current.is_symlink():
        raise ValueError("Current must be an application-owned release symlink")
    link = os.readlink(current).replace("\\", "/")
    match = re.fullmatch(r"releases/([0-9a-f]{40})", link)
    if not match:
        raise ValueError("Current points outside the release namespace")
    manifest_at(root / link, match[1])
    return match[1]


def activate(root, expected, previous):
    revision(expected)
    if previous != "NONE":
        revision(previous)
    with release_lock(root) as root:
        manifest_at(root / "releases" / expected, expected)
        actual = current_revision(root)
        if actual == expected:
            return actual  # Readback makes a repeated activation idempotent.
        if actual != previous:
            raise ValueError("Current release changed; reread before activation")
        temporary = root / (".current-" + uuid.uuid4().hex)
        try:
            temporary.symlink_to(Path("releases") / expected, target_is_directory=True)
            os.replace(temporary, root / "current")
        finally:
            if temporary.is_symlink():
                temporary.unlink()
        if current_revision(root) != expected:
            raise RuntimeError("Release readback failed")
        return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify", "stage", "activate"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--previous", help="Observed current SHA, or NONE for first activation")
    args = parser.parse_args()
    if args.action in {"verify", "stage"} and args.artifact is None:
        parser.error("--artifact is required")
    if args.action != "verify" and args.root is None:
        parser.error("--root is required")
    if args.action == "verify":
        manifest_at(args.artifact, args.sha)
    elif args.action == "stage":
        stage(args.artifact, args.root, args.sha)
    else:
        if args.previous is None:
            parser.error("--previous is required")
        previous = activate(args.root, args.sha, args.previous)
        print(f"PWA_PREVIOUS revision={previous}")
    print(f"PWA_{args.action.upper()}_OK revision={args.sha}")


if __name__ == "__main__":
    main()
