"""Durable Telegram learning deletion receipts outside the PostgreSQL dump."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile

from app.database import DatabaseError, is_postgres


class JournalError(ValueError):
    pass


def configured_directory() -> Path | None:
    value = os.getenv("LEARNING_DELETION_JOURNAL", "").strip()
    if not value:
        return None
    directory = Path(value)
    if not directory.is_absolute():
        raise JournalError("absolute_deletion_journal_path_required")
    return directory


def _check_private(path: Path, expected_type: int) -> None:
    info = path.lstat()
    if (stat.S_IFMT(info.st_mode) != expected_type or info.st_uid != os.geteuid()
            or info.st_mode & 0o077):
        raise JournalError("private_deletion_journal_required")


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _locked(directory: Path):
    import fcntl

    _check_private(directory, stat.S_IFDIR)
    descriptor = os.open(directory / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "r+b") as lock:
        _check_private(directory / "lock", stat.S_IFREG)
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _write(directory: Path, state: dict) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".journal-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"state": state, "digest": _digest(state, state)}, output,
                      separators=(",", ":"), sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, directory / "journal.json")
        _sync_directory(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _read(directory: Path) -> dict:
    path = directory / "journal.json"
    _check_private(path, stat.S_IFREG)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        state = document["state"]
        if (set(state) != {"format", "key", "cluster", "database", "events"}
                or state["format"] != 1
                or not re.fullmatch(r"[0-9a-f]{64}", state["key"])
                or not re.fullmatch(r"[0-9]+", state["cluster"])
                or not state["database"] or not isinstance(state["events"], list)):
            raise ValueError
        if not hmac.compare_digest(document["digest"], _digest(state, state)):
            raise ValueError
        for index, event in enumerate(state["events"], 1):
            if (set(event) != {"sequence", "xid", "actor", "status"}
                    or type(event["sequence"]) is not int or event["sequence"] != index
                    or not re.fullmatch(r"[0-9]+", event["xid"])
                    or event["status"] not in {"pending", "committed", "aborted"}
                    or (event["actor"] is not None if event["status"] == "aborted"
                        else not re.fullmatch(r"[0-9a-f]{64}", event["actor"]))):
                raise ValueError
        if any(event["status"] == "pending" for event in state["events"][:-1]):
            raise ValueError
        return state
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise JournalError("invalid_deletion_journal") from error


def initialize(directory: Path, *, cluster: str, database: str) -> None:
    directory.mkdir(mode=0o700)
    _sync_directory(directory.parent)
    with _locked(directory):
        _write(directory, {"format": 1, "key": secrets.token_hex(32),
                           "cluster": cluster, "database": database, "events": []})


def _reconcile(directory: Path, state: dict, conn) -> None:
    if conn.execute("SELECT current_database()").fetchone()[0] != state["database"]:
        raise JournalError("deletion_journal_database_mismatch")
    events = state["events"]
    if not events or events[-1]["status"] != "pending":
        return
    event = events[-1]
    status = conn.execute("SELECT pg_xact_status(CAST(? AS xid8))", (event["xid"],)).fetchone()[0]
    if status not in {"committed", "aborted"}:
        raise JournalError("unresolved_deletion_transaction")
    event["status"] = status
    if status == "aborted":
        event["actor"] = None
    _write(directory, state)


def actor_digest(state: dict, telegram_user_id: int) -> str:
    return hmac.digest(bytes.fromhex(state["key"]), str(telegram_user_id).encode("ascii"), "sha256").hex()


def _digest(state: dict, value: dict | list) -> str:
    material = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hmac.digest(bytes.fromhex(state["key"]), material, "sha256").hex()


@contextmanager
def recorded_deletion(conn, telegram_user_id: int | None):
    """Commit inside the receipt lock, so acknowledgement follows both stores."""
    if not is_postgres(conn):
        yield
        return
    directory = configured_directory()
    if directory is None:
        if os.getenv("APP_ENV", "").strip().lower() in {"prod", "production"}:
            raise JournalError("deletion_journal_required")
        yield
        return
    if telegram_user_id is None:
        raise JournalError("postgres_telegram_actor_required")
    with _locked(directory):
        state = _read(directory)
        _reconcile(directory, state, conn)
        conn.execute("SET LOCAL synchronous_commit = on")
        xid = conn.execute("SELECT pg_current_xact_id()::text").fetchone()[0]
        event = {"sequence": len(state["events"]) + 1, "xid": xid,
                 "actor": actor_digest(state, telegram_user_id), "status": "pending"}
        state["events"].append(event)
        _write(directory, state)
        yield
        try:
            conn.commit()
        except DatabaseError as error:
            raise JournalError("unresolved_deletion_transaction") from error
        event["status"] = "committed"
        _write(directory, state)


def _point(state: dict, count: int) -> dict:
    return {"sequence": count, "digest": _digest(state, state["events"][:count])}


def recovery_records(directory: Path, conn, *, cluster: str, point: dict | None = None):
    """Read the current point or validate a point and return the later actor hashes."""
    with _locked(directory):
        state = _read(directory)
        if state["cluster"] != cluster:
            raise JournalError("deletion_journal_cluster_mismatch")
        _reconcile(directory, state, conn)
        if point is None:
            return _point(state, len(state["events"]))
        count = point.get("sequence") if isinstance(point, dict) else None
        if type(count) is not int or not 0 <= count <= len(state["events"]) or point != _point(state, count):
            raise JournalError("unverified_deletion_journal_point")
        return state, {event["actor"] for event in state["events"][count:] if event["status"] == "committed"}
