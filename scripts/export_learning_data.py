"""Operator-only learning-data copy after identity verification of a request.

No delivery is performed. Outputs must remain private; never attach to Git/PR.
"""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import connect_database, is_postgres_target, resolve_database_target
from app.privacy_export import write_learning_copy
from scripts.source_inventory_report import private_json_target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telegram-user-id", type=int, required=True)
    parser.add_argument("--verified-request", action="store_true", required=True,
                        help="Operator has already verified the requesting identity")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = None
    try:
        if args.telegram_user_id <= 0:
            raise ValueError("invalid_telegram_user_id")
        path = private_json_target(args.output, ROOT)
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
                write_learning_copy(conn, int(actor[0]), output, expected_telegram_user_id=args.telegram_user_id)
                output.flush()
                os.fsync(output.fileno())
    except Exception as error:
        # A partially written file is preserved as failed evidence, never sent.
        print("LEARNING_COPY_STOP type=" + type(error).__name__ +
              ("; incomplete output must not be delivered" if output is not None else ""), file=sys.stderr)
        return 1
    print("LEARNING_COPY_CREATED; identity/authentication storage and backups excluded; delivery not performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
