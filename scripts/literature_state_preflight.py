"""Read-only, aggregate-only inspection; never merges or changes reading state."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import connect_database, is_postgres_target, resolve_database_target
from app.literature import load_literature_items
from app.literature_state_preflight import inspect


def main():
    target = resolve_database_target(require_sqlite_path=True)
    if is_postgres_target(target):
        conn = connect_database(target)
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    else:
        conn = sqlite3.connect(Path(target).resolve().as_uri() + '?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
    with closing(conn):
        print(json.dumps(inspect(conn, load_literature_items()), sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('LITERATURE_PREFLIGHT_STOP type=' + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
