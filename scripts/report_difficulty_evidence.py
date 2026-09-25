"""Private read-only report for manual review of difficulty metadata.

Set DATABASE_URL or DB_PATH in the process environment. No actor data or DSN
is printed; never run against an unknown target.
"""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3

from app.database import is_postgres_target, resolve_database_target
from app.db import get_connection
from app.difficulty_calibration import report


def main() -> None:
    target = resolve_database_target(require_sqlite_path=True)
    if is_postgres_target(target):
        with closing(get_connection(target)) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            result = report(conn)
    else:
        path = Path(target).resolve(strict=True)
        if not path.is_file():
            raise ValueError("DB_PATH must be an existing database file")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
            result = report(conn)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
