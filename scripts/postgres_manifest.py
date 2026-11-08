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
from app.deletion_journal import configured_directory, initialize, recovery_records
from app.postgres_recovery import manifest, recovery_target, verify_user_state
from app.privacy_data import replay_learning_deletions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="Owned isolated restore DB; never an arbitrary runtime target")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-user-state", action="store_true", help="Compare stdin manifest with runtime")
    mode.add_argument("--initialize-deletion-journal", action="store_true")
    mode.add_argument("--deletion-point", action="store_true")
    mode.add_argument("--replay-deletions", action="store_true")
    parser.add_argument("--cluster")
    args = parser.parse_args()
    try:
        target = resolve_database_target(require_sqlite_path=True)
        if not is_postgres_target(target):
            raise ValueError("PostgreSQL target required")
        if args.initialize_deletion_journal or args.deletion_point or args.replay_deletions:
            directory = configured_directory()
            if directory is None or not args.cluster or not args.cluster.isascii() or not args.cluster.isdecimal():
                raise ValueError("Deletion journal and cluster required")
            if bool(args.database) != args.replay_deletions:
                raise ValueError("Replay requires an isolated restore")
            if args.initialize_deletion_journal:
                with closing(connect_database(target)) as conn:
                    database = conn.execute("SELECT current_database()").fetchone()[0]
                initialize(directory, cluster=args.cluster, database=database)
            elif args.deletion_point:
                with closing(connect_database(target)) as conn:
                    print(json.dumps(recovery_records(directory, conn, cluster=args.cluster)))
            else:
                request = json.load(sys.stdin)
                with closing(connect_database(target)) as conn:
                    journal, actors = recovery_records(directory, conn, cluster=args.cluster, point=request["point"])
                with closing(connect_database(recovery_target(target, args.database))) as conn, conn:
                    if manifest(conn) != request["before"]:
                        raise ValueError("Restore changed before deletion replay")
                    applied = replay_learning_deletions(conn, journal, actors)
                print(json.dumps({"actors_reconciled": applied, "status": "verified"}))
            return 0
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
