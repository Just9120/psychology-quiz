"""Package and verify an exact-revision backend image without a registry."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.pwa_artifact import authorize, REPOSITORY
from scripts.pwa_release import revision

MAX_BYTES = 512 * 1024 * 1024
FILES = {"manifest.json", "image.tar.gz"}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tag(sha):
    revision(sha)
    return "psychology-quiz-runtime:" + sha


def inspect_image(name, sha, expected_id=None):
    value = json.loads(subprocess.check_output(["docker", "image", "inspect", name], text=True))
    if (len(value) != 1 or value[0].get("Os") != "linux" or value[0].get("Architecture") != "amd64"
            or value[0].get("Config", {}).get("Labels", {}).get("org.opencontainers.image.revision") != sha
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", value[0].get("Id", ""))
            or expected_id is not None and value[0]["Id"] not in ({expected_id} if isinstance(expected_id, str) else expected_id)):
        raise ValueError("Backend image identity/platform/revision differs")
    return value[0]["Id"]


def package(sha, destination):
    image = tag(sha)
    image_id = inspect_image(image, sha)
    destination = Path(destination)
    destination.mkdir(mode=0o700)
    archive = destination / "image.tar.gz"
    with archive.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
        # No shell, secrets, Docker context or private files enter the archive.
        with subprocess.Popen(["docker", "image", "save", image], stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE) as process:
            while block := process.stdout.read(1024 * 1024):
                compressed.write(block)
            if process.wait() != 0:
                raise ValueError("Docker image save failed")
    if not 0 < archive.stat().st_size <= MAX_BYTES:
        raise ValueError("Backend image transport too large")
    manifest = {"schema_version": 1, "revision": sha, "tag": image, "image_id": image_id,
                "platform": "linux/amd64", "image_sha256": digest(archive)}
    with (destination / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, sort_keys=True)
        stream.write("\n")
    return manifest


def verify(archive, destination, sha, expected_digest):
    revision(sha)
    archive, destination = Path(archive), Path(destination)
    if (not re.fullmatch(r"[0-9a-f]{64}", expected_digest) or archive.is_symlink()
            or not archive.is_file() or not 0 < archive.stat().st_size <= MAX_BYTES):
        raise ValueError("Invalid backend archive")
    with archive.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != expected_digest:
            raise ValueError("Backend archive digest differs from GitHub")
        source.seek(0)
        with zipfile.ZipFile(source) as bundle:
            entries = bundle.infolist()
            if (len(entries) != 2 or {item.filename for item in entries} != FILES
                    or sum(item.file_size for item in entries) > MAX_BYTES):
                raise ValueError("Invalid backend package layout/size")
            for item in entries:
                if (item.orig_filename != item.filename or item.flag_bits & 1
                        or stat.S_IFMT(item.external_attr >> 16) not in (0, stat.S_IFREG)):
                    raise ValueError("Invalid backend package type")
            if bundle.getinfo("manifest.json").file_size > 2048:
                raise ValueError("Oversized backend manifest")
            manifest = json.loads(bundle.read("manifest.json"))
            expected_fields = {"schema_version", "revision", "tag", "image_id", "platform", "image_sha256"}
            if (not isinstance(manifest, dict) or set(manifest) != expected_fields
                    or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
                    or not all(isinstance(manifest[key], str) for key in expected_fields - {"schema_version"})
                    or manifest["revision"] != sha
                    or manifest["tag"] != tag(sha) or manifest["platform"] != "linux/amd64"
                    or not re.fullmatch(r"sha256:[0-9a-f]{64}", manifest["image_id"])
                    or not re.fullmatch(r"[0-9a-f]{64}", manifest["image_sha256"])):
                raise ValueError("Invalid backend manifest identity")
            destination.mkdir(mode=0o700)
            target = destination / "image.tar.gz"
            with bundle.open("image.tar.gz") as image, target.open("xb") as output:
                while block := image.read(1024 * 1024):
                    output.write(block)
            if digest(target) != manifest["image_sha256"]:
                raise ValueError("Backend image bytes differ from manifest")
        source.seek(0)
        if hashlib.file_digest(source, "sha256").hexdigest() != expected_digest:
            raise ValueError("Backend archive changed during verification")
    return manifest, target


def archive_image_ids(image, manifest):
    """Bind classic config and containerd manifest IDs to the verified archive.

    Docker stores expose different IDs for identical saved bytes. Never accept
    an ID from the daemon unless it is linked to this archive's exact config.
    No archive paths are extracted; metadata and expanded size are bounded.
    """
    metadata = {}
    files = set()
    expanded = 0
    metadata_bytes = 0
    with tarfile.open(image, "r|gz") as saved:
        for entry in saved:
            expanded += entry.size
            if expanded > 4 * 1024 * 1024 * 1024 or len(files) >= 10000:
                raise ValueError("Oversized saved image")
            if entry.isdir():
                continue
            name = entry.name
            if not entry.isfile() or name in files:
                raise ValueError("Invalid saved image entry")
            files.add(name)
            if (name in {"manifest.json", "index.json"} or name.endswith(".json")
                    or re.fullmatch(r"blobs/sha256/[0-9a-f]{64}", name)) and entry.size <= 4 * 1024 * 1024:
                raw = saved.extractfile(entry).read()
                metadata_bytes += len(raw)
                if metadata_bytes > 32 * 1024 * 1024:
                    raise ValueError("Oversized saved image metadata")
                metadata[name] = raw
    try:
        docker = json.loads(metadata["manifest.json"])
        if (not isinstance(docker, list) or len(docker) != 1
                or docker[0].get("RepoTags") != [manifest["tag"]]):
            raise ValueError("Ambiguous saved image")
        config_name = docker[0]["Config"]
        config_raw = metadata[config_name]
        config_id = "sha256:" + hashlib.sha256(config_raw).hexdigest()
        config = json.loads(config_raw)
        if (config.get("os") != "linux" or config.get("architecture") != "amd64"
                or config.get("config", {}).get("Labels", {}).get("org.opencontainers.image.revision") != manifest["revision"]):
            raise ValueError("Saved image platform/revision differs")
        layers = docker[0]["Layers"]
        if not isinstance(layers, list) or not layers or any(name not in files for name in layers):
            raise ValueError("Incomplete saved image")
        identities = {config_id}
        if "index.json" in metadata:
            index = json.loads(metadata["index.json"])
            descriptors = index["manifests"]
            if index.get("schemaVersion") != 2 or len(descriptors) != 1:
                raise ValueError("Ambiguous OCI image")
            descriptor = descriptors[0]
            manifest_id = descriptor["digest"]
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", manifest_id):
                raise ValueError("Invalid OCI digest")
            raw = metadata["blobs/sha256/" + manifest_id.removeprefix("sha256:")]
            if ("sha256:" + hashlib.sha256(raw).hexdigest() != manifest_id
                    or descriptor["size"] != len(raw)):
                raise ValueError("OCI manifest digest differs")
            oci = json.loads(raw)
            if (oci.get("schemaVersion") != 2 or oci["config"]["digest"] != config_id
                    or oci["config"]["size"] != len(config_raw)
                    or ["blobs/sha256/" + layer["digest"].removeprefix("sha256:") for layer in oci["layers"]] != layers):
                raise ValueError("OCI manifest/config/layers differ")
            identities.add(manifest_id)
        if manifest["image_id"] not in identities:
            raise ValueError("Producer identity differs from saved image")
        return identities
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid saved image metadata") from error


def load(archive, sha, expected_digest):
    with tempfile.TemporaryDirectory(prefix="psychology-backend-") as temporary:
        manifest, image = verify(archive, Path(temporary) / "verified", sha, expected_digest)
        identities = archive_image_ids(image, manifest)
        platform = subprocess.check_output(["docker", "version", "--format", "{{.Server.Os}}/{{.Server.Arch}}"], text=True).strip()
        if platform != "linux/amd64":
            raise ValueError("Unexpected target Docker platform")
        subprocess.run(["docker", "image", "load", "--input", str(image)],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=True)
        # Return the target store ID so deploy.sh retains exact container equality.
        loaded_id = inspect_image(tag(sha), sha, identities)
        manifest = {**manifest, "image_id": loaded_id}
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("package", "download", "check", "load"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--digest")
    parser.add_argument("--id-only", action="store_true")
    args = parser.parse_args()
    if args.action == "package":
        if args.directory is None:
            parser.error("--directory required")
        manifest = package(args.sha, args.directory)
        print(f"BACKEND_IMAGE_PACKAGED revision={args.sha} image={manifest['image_id']}")
        return
    if args.archive is None:
        parser.error("--archive required")
    if args.action == "load":
        if args.digest is None:
            parser.error("--digest required")
        manifest = load(args.archive, args.sha, args.digest)
        print(manifest["image_id"] if args.id_only else f"BACKEND_IMAGE_LOADED revision={args.sha} image={manifest['image_id']}")
        return
    if args.run_id is None:
        parser.error("--run-id required")
    artifact = authorize(args.sha, args.run_id, kind="backend")
    expected_digest = artifact["digest"].removeprefix("sha256:")
    if args.action == "download":
        with args.archive.open("xb") as stream:
            args.archive.chmod(0o600)
            subprocess.run(["gh", "api", f"repos/{REPOSITORY}/actions/artifacts/{artifact['id']}/zip"],
                           stdin=subprocess.DEVNULL, stdout=stream, check=True)
    with tempfile.TemporaryDirectory() as temporary:
        manifest, _ = verify(args.archive, Path(temporary) / "verified", args.sha, expected_digest)
    if args.action == "download":
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"digest={expected_digest}\nartifact_id={artifact['id']}\nimage_id={manifest['image_id']}\n")
    print(f"BACKEND_ARTIFACT_VALIDATED revision={args.sha} ci_run={args.run_id} artifact={artifact['id']} digest=sha256:{expected_digest}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, tarfile.TarError, subprocess.CalledProcessError) as error:
        raise SystemExit("BACKEND_ARTIFACT_STOP: " + type(error).__name__) from None
