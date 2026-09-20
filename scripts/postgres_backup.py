"""Native dump/isolated-restore workflow, with injectable system boundaries."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_record(path: Path, value: dict) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".record-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, sort_keys=True, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def sync_directory(path: Path) -> None:
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def backup_and_rehearse(runtime, backup_root: Path) -> Path:
    """Writers stopped and target/lock verified by the concrete runtime boundary.

    runtime supplies manifest(), dump(), create_restore_database(), restore(),
    drop_restore_database(). It never restores or truncates the runtime database.
    """
    runtime.require_stopped_writers()
    before = runtime.manifest()
    backup_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="release-", dir=backup_root))
    record_path, dump = directory / "record.json", directory / "database.dump"
    record = {"format": "psychology-postgres-recovery-v1", "phase": "started",
              "source": runtime.identity(), "before": before}
    write_record(record_path, record)
    restore_name = "psychology_restore_" + uuid.uuid4().hex
    created = False
    try:
        runtime.dump(dump)
        if not dump.is_file() or not dump.stat().st_size:
            raise ValueError("PostgreSQL dump is empty")
        record.update(phase="dumped", dump_sha256=file_digest(dump), dump_bytes=dump.stat().st_size,
                      restore_database=restore_name)
        write_record(record_path, record)
        record["phase"] = "creating_restore"
        write_record(record_path, record)
        runtime.create_restore_database(restore_name)
        created = True
        record["phase"] = "restore_created"
        write_record(record_path, record)
        runtime.restore(dump, restore_name)
        if runtime.manifest(database=restore_name) != before:
            raise ValueError("PostgreSQL restore reconciliation failed")
        if runtime.manifest() != before:
            raise ValueError("PostgreSQL runtime changed during backup rehearsal")
        runtime.require_stopped_writers()
        runtime.drop_restore_database(restore_name)
        created = False
        record["phase"] = "verified"
        write_record(record_path, record)
        return record_path
    except BaseException as error:
        if record["phase"] == "creating_restore" and not created:
            record["restore_cleanup"] = "creation_unconfirmed_inspect_owned_name"
        record.update(phase="failed", error_type=type(error).__name__)
        if created:
            try:
                runtime.drop_restore_database(restore_name)
                record["restore_cleanup"] = "removed"
            except Exception:
                record["restore_cleanup"] = "pending"
        write_record(record_path, record)
        raise


def read_verified_record(path: Path) -> dict:
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("format") != "psychology-postgres-recovery-v1" or record.get("phase") != "verified":
        raise ValueError("A verified PostgreSQL recovery record is required")
    dump = path.with_name("database.dump")
    if dump.stat().st_size != record["dump_bytes"] or file_digest(dump) != record["dump_sha256"]:
        raise ValueError("PostgreSQL recovery dump has changed")
    return record
