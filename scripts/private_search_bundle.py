"""Transfer reviewed private search inputs without publishing them in Git/CI."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIR = ROOT / ".private-search/input"
ENVELOPE = "_bundle.json"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_FILE = 20_000_000
MAX_TOTAL = 100_000_000
MAX_MEMBERS = 1000


class BundleError(ValueError):
    pass


def filename(value: object) -> str:
    if not isinstance(value, str) or not NAME.fullmatch(value) or value == ENVELOPE:
        raise BundleError("private_bundle_filename_required")
    return value


def private_bytes(directory: Path, name: str) -> bytes:
    path = directory / filename(name)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FILE:
        raise BundleError("private_regular_file_required")
    content = path.read_bytes()
    if len(content) != info.st_size:
        raise BundleError("private_file_changed_during_read")
    return content


def required_names(manifest: dict, cases: dict, manifest_name: str, cases_name: str) -> set[str]:
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or not isinstance(manifest.get("sources"), list)
            or not isinstance(manifest.get("notes", []), list)
            or not isinstance(cases, dict) or cases.get("schema_version") != 1
            or not isinstance(cases.get("cases"), list)):
        raise BundleError("invalid_private_search_inputs")
    names = {filename(manifest_name), filename(cases_name)}
    if manifest["sources"]:
        names.add(filename(manifest.get("processing_path")))
    if "private_registry_path" in manifest:
        names.add(filename(manifest["private_registry_path"]))
    for item in [*manifest["sources"], *manifest.get("notes", [])]:
        if not isinstance(item, dict):
            raise BundleError("invalid_private_search_inputs")
        names.add(filename(item.get("text_path")))
    if len(names) > MAX_MEMBERS:
        raise BundleError("too_many_private_search_files")
    return names


def bundle_inputs(directory: Path, manifest_name: str, cases_name: str) -> dict[str, bytes]:
    manifest = json.loads(private_bytes(directory, manifest_name))
    cases = json.loads(private_bytes(directory, cases_name))
    names = required_names(manifest, cases, manifest_name, cases_name)
    result = {name: private_bytes(directory, name) for name in names}
    if sum(map(len, result.values())) > MAX_TOTAL:
        raise BundleError("private_bundle_too_large")
    return result


def create(directory: Path, manifest_name: str, cases_name: str, output: Path) -> dict:
    directory = directory.resolve(strict=True)
    if (output.resolve(strict=False).parent != directory.parent.resolve(strict=True)
            or output.suffix != ".zip" or output.exists() or output.is_symlink()):
        raise BundleError("ignored_private_bundle_target_required")
    files = bundle_inputs(directory, manifest_name, cases_name)
    envelope = {"schema_version": 1, "manifest": manifest_name, "cases": cases_name,
                "files": {name: {"sha256": hashlib.sha256(content).hexdigest(),
                                 "size": len(content)} for name, content in sorted(files.items())}}
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as destination:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(files.items()):
                archive.writestr(name, content)
            archive.writestr(ENVELOPE, json.dumps(envelope, sort_keys=True).encode())
        destination.flush()
        os.fsync(destination.fileno())
    return {"files": len(files), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def read_bundle(archive_path: Path, expected_sha256: str) -> tuple[dict, dict[str, bytes]]:
    if not isinstance(expected_sha256, str) or not SHA256.fullmatch(expected_sha256):
        raise BundleError("expected_bundle_digest_required")
    info = archive_path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_TOTAL:
        raise BundleError("private_archive_required")
    if os.name == "posix" and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise BundleError("private_archive_permissions_required")
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != expected_sha256:
        raise BundleError("private_archive_digest_changed")
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        names = [item.filename for item in members]
        if (len(names) != len(set(names)) or len(names) > MAX_MEMBERS + 1
                or ENVELOPE not in names or any(item.is_dir() or item.file_size > MAX_FILE
                                                or stat.S_IFMT(item.external_attr >> 16)
                                                not in {0, stat.S_IFREG} for item in members)
                or sum(item.file_size for item in members) > MAX_TOTAL
                or any(name != ENVELOPE and not NAME.fullmatch(name) for name in names)):
            raise BundleError("invalid_private_archive_members")
        envelope = json.loads(archive.read(ENVELOPE))
        files = envelope.get("files") if isinstance(envelope, dict) else None
        if (not isinstance(envelope, dict) or envelope.get("schema_version") != 1
                or not isinstance(files, dict) or set(files) != set(names) - {ENVELOPE}
                or filename(envelope.get("manifest")) not in files
                or filename(envelope.get("cases")) not in files):
            raise BundleError("invalid_private_archive_envelope")
        contents = {}
        for name, item in files.items():
            filename(name)
            if (not isinstance(item, dict) or set(item) != {"sha256", "size"}
                    or not isinstance(item["sha256"], str) or not SHA256.fullmatch(item["sha256"])
                    or type(item["size"]) is not int or not 0 < item["size"] <= MAX_FILE):
                raise BundleError("invalid_private_archive_envelope")
            content = archive.read(name)
            if len(content) != item["size"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
                raise BundleError("private_archive_member_changed")
            contents[name] = content
    if required_names(json.loads(contents[envelope["manifest"]]),
                      json.loads(contents[envelope["cases"]]),
                      envelope["manifest"], envelope["cases"]) != set(contents):
        raise BundleError("private_archive_unreferenced_file")
    return envelope, contents


def install(archive_path: Path, expected_sha256: str, directory: Path) -> dict:
    envelope, files = read_bundle(archive_path, expected_sha256)
    parent = directory.parent
    shared_data = parent.parent / "data"
    if any((shared_data / name).exists() or (shared_data / name).is_symlink()
           for name in ("search-input", "search-model-cache")):
        raise BundleError("legacy_private_search_exposed_to_app")
    if not parent.exists() and not parent.is_symlink():
        parent.mkdir(mode=0o700)
    if not parent.is_dir() or parent.is_symlink():
        raise BundleError("private_data_directory_required")
    if os.name == "posix":
        info = parent.stat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise BundleError("private_data_directory_permissions_required")
    if directory.exists() or directory.is_symlink():
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or directory.is_symlink():
            raise BundleError("private_search_directory_required")
    else:
        directory.mkdir(mode=0o700)
    if os.name == "posix":
        info = directory.stat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise BundleError("private_search_directory_permissions_required")
    # Preflight every destination. Interrupted installs resume only with
    # identical bytes; no existing file is overwritten.
    for name, content in files.items():
        target = directory / name
        if target.exists() or target.is_symlink():
            info = target.lstat()
            if (not stat.S_ISREG(info.st_mode) or target.read_bytes() != content
                    or (os.name == "posix" and
                        (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077))):
                raise BundleError("private_search_file_collision")
    created = 0
    for name in [*(name for name in sorted(files) if name != envelope["manifest"]),
                 envelope["manifest"]]:
        target = directory / name
        if target.exists():
            continue
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(files[name])
            output.flush()
            os.fsync(output.fileno())
        created += 1
    if any((directory / name).read_bytes() != content for name, content in files.items()):
        raise BundleError("private_search_install_readback_failed")
    return {"files": len(files), "created": created,
            "manifest": envelope["manifest"], "cases": envelope["cases"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Private reviewed search input transfer")
    parser.add_argument("action", choices=("create", "install"))
    parser.add_argument("--manifest")
    parser.add_argument("--cases")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args(argv)
    try:
        if args.action == "create":
            if args.manifest is None or args.cases is None or args.output is None:
                raise BundleError("create_arguments_required")
            ignored = subprocess.run(["git", "check-ignore", "-q", "--", str(args.output)],
                                     cwd=ROOT, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ignored.returncode != 0:
                raise BundleError("ignored_private_bundle_target_required")
            result = create(PRIVATE_DIR, filename(args.manifest), filename(args.cases), args.output)
        else:
            if (os.name != "posix" or os.geteuid() != 0 or ROOT.resolve() != Path("/opt/psychology-quiz")
                    or args.archive is None or args.sha256 is None):
                raise BundleError("vps_operator_install_required")
            result = install(args.archive, args.sha256, PRIVATE_DIR)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (BundleError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print("PRIVATE_SEARCH_BUNDLE_STOP: " +
              (str(error) if isinstance(error, BundleError) else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
