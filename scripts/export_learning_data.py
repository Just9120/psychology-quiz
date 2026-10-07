"""Operator-only learning-data copy after identity verification of a request.

No delivery is performed. Outputs must remain private; never attach to Git/PR.
"""
import argparse
from contextlib import closing
import os
import stat
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import connect_database, is_postgres_target, resolve_database_target
from app.privacy_export import write_learning_copy
from scripts.source_inventory_report import private_json_target


RUNTIME_DATA = Path('/data')


def export_target(raw):
    """Runtime copies must land in the persistent private mount, never /app."""
    if ROOT != Path('/app'):
        return private_json_target(raw, ROOT)
    if RUNTIME_DATA.resolve(strict=True) != RUNTIME_DATA:
        raise ValueError('physical_runtime_data_required')
    directory = RUNTIME_DATA / 'learning-copies'
    if not directory.exists() and not directory.is_symlink():
        directory.mkdir(mode=0o700)
    info = directory.lstat()
    if (not stat.S_ISDIR(info.st_mode)
            or (os.name == 'posix' and (info.st_uid != os.geteuid() or info.st_mode & 0o077))):
        raise ValueError('private_copy_directory_required')
    raw = Path(raw)
    if raw.is_symlink():
        raise ValueError('ordinary_copy_path_required')
    target = raw.resolve()
    if target.parent != directory or target.suffix.lower() != '.json':
        raise ValueError('persistent_private_copy_target_required')
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telegram-user-id", type=int, required=True)
    parser.add_argument("--verified-request", action="store_true", required=True,
                        help="Operator has already verified the requesting identity")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-identity", action="store_true",
                        help="Also copy this actor's saved profile and linked account identifiers; never credentials")
    args = parser.parse_args(argv)
    output = None
    try:
        if args.telegram_user_id <= 0:
            raise ValueError("invalid_telegram_user_id")
        path = export_target(args.output)
        target = resolve_database_target(require_sqlite_path=True)
        connection = (connect_database(target) if is_postgres_target(target) else
                      sqlite3.connect(Path(target).resolve(strict=True).as_uri() + "?mode=ro", uri=True))
        with closing(connection) as conn:
            actor = conn.execute("SELECT id FROM users WHERE telegram_user_id=?", (args.telegram_user_id,)).fetchone()
            if actor is None:
                raise ValueError("unknown_actor")
            # PostgreSQL starts a transaction for this read. The exporter owns
            # a separate read-only snapshot and rechecks the Telegram identity
            # inside it before writing any personal data to the private file.
            conn.rollback()
            output = os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8")
            with output:
                write_learning_copy(conn, int(actor[0]), output,
                                    expected_telegram_user_id=args.telegram_user_id,
                                    include_identity=args.include_identity)
                output.flush()
                os.fsync(output.fileno())
    except Exception as error:
        # A partially written file is preserved as failed evidence, never sent.
        print("LEARNING_COPY_STOP type=" + type(error).__name__ +
              ("; incomplete output must not be delivered" if output is not None else ""), file=sys.stderr)
        return 1
    exclusions = "credentials/authentication state and backups" if args.include_identity else "identity/authentication storage and backups"
    print("LEARNING_COPY_CREATED; " + exclusions + " excluded; delivery not performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
