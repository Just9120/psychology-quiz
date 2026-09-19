"""Read-only deployment checks and backup rehearsal; never restore production."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from app.attempt_content import get_attempt_content
from app.auth_schema import AUTH_TABLES
from scripts.audit_question_bank import build_report, has_blockers

USER_TABLES = (
    "users", "quiz_sessions", "quiz_session_selected_categories",
    "quiz_session_questions", "quiz_answers", "user_literature_progress",
)


def read_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)


def check_integrity(conn: sqlite3.Connection) -> None:
    if [row[0] for row in conn.execute("PRAGMA integrity_check")] != ["ok"]:
        raise RuntimeError("Database integrity check failed")
    if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise RuntimeError("Database foreign key check failed")


def user_state(conn: sqlite3.Connection, columns: dict | None = None) -> dict:
    """Compare all pre-existing user fields; additive columns are permitted."""
    result = {}
    existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    # Old backups lack auth tables. Preserve every table present in that backup,
    # while newly introduced empty auth tables are allowed by an additive migration.
    tables = tuple(columns) if columns is not None else USER_TABLES + tuple(name for name in AUTH_TABLES if name in existing)
    for table in tables:
        if table not in USER_TABLES + AUTH_TABLES:
            raise RuntimeError("Unexpected user-state table")
        names = (columns[table]["columns"] if columns else
                 [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')])
        if not names or any(not name.replace("_", "").isalnum() for name in names):
            raise RuntimeError("Missing or invalid user-state schema")
        fields = ", ".join(f'"{name}"' for name in names)
        digest = hashlib.sha256()
        count = 0
        for row in conn.execute(f'SELECT {fields} FROM "{table}" ORDER BY {fields}'):
            digest.update(json.dumps(tuple(row), ensure_ascii=False, separators=(",", ":")).encode())
            digest.update(b"\n")
            count += 1
        result[table] = {"columns": names, "rows": count, "sha256": digest.hexdigest()}
    return result


def backup_and_rehearse(db_path: Path, backup_root: Path) -> Path:
    # mkdtemp is exclusive, private, and leaves earlier recovery points intact.
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = Path(tempfile.mkdtemp(prefix="release-", dir=backup_root))
    backup_path = directory / "quiz.sqlite3"
    with closing(read_connection(db_path)) as source:
        check_integrity(source)
        before = user_state(source)
        with closing(sqlite3.connect(backup_path)) as backup:
            source.backup(backup)
    # Exercise restore to an isolated file, not just readability of the backup.
    with tempfile.TemporaryDirectory(prefix="restore-check-", dir=directory) as temporary:
        with closing(read_connection(backup_path)) as backup, closing(
            sqlite3.connect(Path(temporary) / "restored.sqlite3")
        ) as restored:
            backup.backup(restored)
            check_integrity(restored)
            if user_state(restored) != before:
                raise RuntimeError("Backup restore did not preserve user state")
    (directory / "manifest.json").write_text(json.dumps(before), encoding="utf-8")
    return backup_path


def verify_preserved(db_path: Path, backup_path: Path) -> None:
    before = json.loads(backup_path.with_name("manifest.json").read_text(encoding="utf-8"))
    with closing(read_connection(db_path)) as conn:
        check_integrity(conn)
        if user_state(conn, before) != before:
            raise RuntimeError("Migration changed pre-existing user state")


def check_business(conn: sqlite3.Connection) -> None:
    check_integrity(conn)
    count = conn.execute("SELECT count(*) FROM questions WHERE status='approved'").fetchone()[0]
    if count == 0:
        raise RuntimeError("No approved questions available")
    invalid = conn.execute("""
        SELECT q.id FROM questions q LEFT JOIN question_options o ON o.question_id=q.id
        WHERE q.status='approved' GROUP BY q.id
        HAVING count(o.id) < 2 OR sum(o.is_correct) != 1 LIMIT 1
    """).fetchone()
    if invalid:
        raise RuntimeError("Invalid serving question options")
    for session_id, question_id in conn.execute("SELECT session_id, question_id FROM quiz_session_questions"):
        get_attempt_content(conn, session_id, question_id)


def check_content_parity(db_path: Path) -> None:
    if has_blockers(build_report(str(db_path))):
        raise RuntimeError("Serving content differs from canonical approved bank")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preflight", "backup", "verify", "smoke"))
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    # The runtime's database must live in the existing persistent bind mount.
    raw_path = os.environ.get("DB_PATH", "")
    db_path = Path(raw_path).resolve()
    if not raw_path or not db_path.is_relative_to(Path("/data")) or not db_path.is_file():
        raise RuntimeError("DB_PATH must identify an existing database under /data")
    if args.action == "preflight":
        token = os.environ.get("BOT_TOKEN", "")
        if not token or "__REQUIRED_SECRET__" in token:
            raise RuntimeError("Required runtime configuration is missing")
        if os.environ.get("TELEGRAM_UPDATE_MODE", "polling").strip().lower() == "webhook":
            for name in ("TELEGRAM_WEBHOOK_URL", "TELEGRAM_WEBHOOK_LISTEN",
                         "TELEGRAM_WEBHOOK_PORT", "TELEGRAM_WEBHOOK_SECRET_TOKEN"):
                if not os.environ.get(name, "").strip():
                    raise RuntimeError(f"Required configuration is missing: {name}")
            if not 1 <= int(os.environ["TELEGRAM_WEBHOOK_PORT"]) <= 65535:
                raise RuntimeError("Invalid webhook port")
        with closing(read_connection(db_path)) as conn:
            check_integrity(conn)
            user_state(conn)
        print("PREFLIGHT_OK")
    elif args.action == "backup":
        print(backup_and_rehearse(db_path, Path("/data/backups")))
    elif args.action == "verify":
        if args.backup is None or not args.backup.resolve().is_relative_to(Path("/data/backups")):
            raise RuntimeError("A verified backup under /data/backups is required")
        verify_preserved(db_path, args.backup)
        print("USER_STATE_PRESERVED")
    else:
        with closing(read_connection(db_path)) as conn:
            check_business(conn)
        check_content_parity(db_path)
        print("CONTENT_PARITY_OK")
        print("DATABASE_SMOKE_OK")


if __name__ == "__main__":
    main()
