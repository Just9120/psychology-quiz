"""Print only recovery hashes; connection credentials remain in runtime env."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import connect_database, is_postgres_target, resolve_database_target
from app.postgres_recovery import manifest, recovery_target, verify_user_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="Owned isolated restore DB; never an arbitrary runtime target")
    parser.add_argument("--verify-user-state", action="store_true", help="Compare stdin manifest with runtime")
    args = parser.parse_args()
    try:
        target = resolve_database_target(require_sqlite_path=True)
        if not is_postgres_target(target):
            raise ValueError("PostgreSQL target required")
        if args.database:
            target = recovery_target(target, args.database)
        with closing(connect_database(target)) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            result = manifest(conn)
        if args.verify_user_state:
            verify_user_state(json.load(sys.stdin), result)
            print("POSTGRES_USER_STATE_PRESERVED")
        else:
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as error:
        print("POSTGRES_MANIFEST_FAILED type=" + type(error).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
