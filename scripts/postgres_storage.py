"""Explicit PostgreSQL schema/import commands; credentials only via DATABASE_URL."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from app.database import connect_database, is_postgres_target, resolve_database_target
from app.postgres_import import import_snapshot
from app.postgres_schema import initialize_schema, verify_schema


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "check", "import"))
    parser.add_argument("--source", type=Path, help="Offline, validated SQLite snapshot for import")
    parser.add_argument("--report", type=Path, help="New JSON result file; never overwritten")
    args = parser.parse_args()
    load_dotenv()
    try:
        target = resolve_database_target()
        if not is_postgres_target(target):
            raise ValueError("DATABASE_URL is required")
        if args.report is not None and args.report.exists():
            raise ValueError("Report already exists")
        if args.action == "import":
            if args.source is None:
                raise ValueError("Import requires --source")
            report = import_snapshot(args.source, target)
        else:
            if args.source is not None:
                raise ValueError("--source is only valid for import")
            with closing(connect_database(target)) as conn, conn:
                (initialize_schema if args.action == "init" else verify_schema)(conn)
            report = {"result": args.action + "_ok"}
        if args.report is not None:
            with args.report.open("x", encoding="utf-8") as output:
                json.dump(report, output, ensure_ascii=False, indent=2)
                output.write("\n")
        print("POSTGRES_STORAGE_OK action=" + args.action + " result=" + report["result"])
        return 0
    except Exception as error:
        # Includes OS/driver messages that might otherwise expose connection input.
        print("POSTGRES_STORAGE_FAILED type=" + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
