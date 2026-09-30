"""Native dump/isolated-restore workflow, with injectable system boundaries."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import stat
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
              "source": runtime.identity(), "before": before,
              "created_at": datetime.now(timezone.utc).isoformat()}
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
        record["verified_at"] = datetime.now(timezone.utc).isoformat()
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
    if not isinstance(record, dict) or record.get("format") != "psychology-postgres-recovery-v1" or record.get("phase") != "verified":
        raise ValueError("A verified PostgreSQL recovery record is required")
    if (type(record.get("dump_bytes")) is not int or record["dump_bytes"] <= 0
            or not isinstance(record.get("dump_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", record["dump_sha256"]) is None):
        raise ValueError("Invalid PostgreSQL recovery dump identity")
    dump = path.with_name("database.dump")
    if dump.stat().st_size != record["dump_bytes"] or file_digest(dump) != record["dump_sha256"]:
        raise ValueError("PostgreSQL recovery dump has changed")
    return record


def rehearse_user_recovery(runtime, verified_path: Path, output_root: Path) -> Path:
    """Restore a verified snapshot and rebuild serving content in an owned copy.

    This never replaces production, deletes a backup, or restores the derivative
    search index. The caller verifies the target, private paths and delivery lock.
    """
    from app.postgres_recovery import verify_user_state

    runtime.require_stopped_writers()
    backup = read_verified_record(verified_path)
    identity = runtime.identity()
    source = backup.get("source")
    if (not isinstance(source, dict)
            or {k: v for k, v in source.items() if k != "revision"}
            != {k: v for k, v in identity.items() if k != "revision"}):
        raise ValueError("Recovery snapshot belongs to another runtime")
    live_before = runtime.manifest()
    if output_root.exists() or output_root.is_symlink():
        info = output_root.lstat()
        if (not stat.S_ISDIR(info.st_mode)
                or (os.name == "posix" and
                    (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077))):
            raise ValueError("Private owned recovery directory required")
    else:
        output_root.mkdir(mode=0o700, parents=True)
    directory = Path(tempfile.mkdtemp(prefix="rehearsal-", dir=output_root))
    record_path = directory / "record.json"
    name = "psychology_restore_" + uuid.uuid4().hex
    record = {"format": "psychology-user-recovery-v1", "phase": "prepared",
              "source": source, "candidate": identity,
              "backup_sha256": backup["dump_sha256"], "restore_database": name,
              "created_at": datetime.now(timezone.utc).isoformat()}
    write_record(record_path, record)
    created = False
    try:
        record["phase"] = "creating_restore"
        write_record(record_path, record)
        runtime.create_restore_database(name)
        created = True
        record["phase"] = "restoring"
        write_record(record_path, record)
        runtime.restore(verified_path.with_name("database.dump"), name)
        if runtime.manifest(database=name) != backup["before"]:
            raise ValueError("Restored snapshot does not match recovery record")
        record["phase"] = "rebuilding_content"
        write_record(record_path, record)
        runtime.rebuild_restore_content(name)
        after = runtime.manifest(database=name)
        verify_user_state(backup["before"], after)
        runtime.require_stopped_writers()
        if runtime.identity() != identity or runtime.manifest() != live_before:
            raise ValueError("Runtime changed during user recovery rehearsal")
        record["after"] = after
        runtime.drop_restore_database(name)
        created = False
        record.update(phase="verified", restore_cleanup="removed",
                      verified_at=datetime.now(timezone.utc).isoformat())
        write_record(record_path, record)
        return record_path
    except BaseException as error:
        if record["phase"] == "creating_restore" and not created:
            record["restore_cleanup"] = "creation_unconfirmed_inspect_owned_name"
        record.update(phase="failed", error_type=type(error).__name__)
        if created:
            try:
                runtime.drop_restore_database(name)
                record["restore_cleanup"] = "removed"
            except Exception:
                record["restore_cleanup"] = "pending"
        write_record(record_path, record)
        raise
