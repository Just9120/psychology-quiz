"""Read-only aggregate inventory before deprecating persisted student PWA state."""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import connect_database, is_postgres, is_postgres_target, resolve_database_target
from app.web_config import normalize_email


def inspect(conn, *, owner_email=None, now=None):
    owner = normalize_email(owner_email) if owner_email else None
    now = int(time.time()) if now is None else int(now)
    if is_postgres(conn):
        tables = {row[0] for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        ).fetchall()}
    else:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    result = {"ok": True, "schema_version": 1, "owner_configured": owner is not None,
              "web_accounts": None, "non_owner_accounts": None, "non_owner_linked_accounts": None,
              "invitation_rows": None, "pending_tokens": None, "expired_tokens": None,
              "consumed_invitations": None, "invitation_linked_accounts": None,
              "review_required": True}
    if "web_accounts" in tables:
        result["web_accounts"] = int(conn.execute("SELECT COUNT(*) FROM web_accounts").fetchone()[0])
        if owner is not None:
            result["non_owner_accounts"] = int(conn.execute(
                "SELECT COUNT(*) FROM web_accounts WHERE lower(email)<>?", (owner,)).fetchone()[0])
            result["non_owner_linked_accounts"] = int(conn.execute(
                "SELECT COUNT(*) FROM web_accounts WHERE lower(email)<>? AND user_id IS NOT NULL", (owner,)).fetchone()[0])
    if "pwa_invitations" in tables:
        counts = conn.execute("""SELECT COUNT(*),
            COALESCE(SUM(CASE WHEN token_digest IS NOT NULL AND consumed_at IS NULL AND expires_at>? THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN token_digest IS NOT NULL AND consumed_at IS NULL AND expires_at<=? THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN consumed_at IS NOT NULL THEN 1 ELSE 0 END),0),
            COALESCE(SUM(CASE WHEN account_id IS NOT NULL THEN 1 ELSE 0 END),0)
            FROM pwa_invitations""", (now, now)).fetchone()
        for key, count in zip(("invitation_rows", "pending_tokens", "expired_tokens", "consumed_invitations", "invitation_linked_accounts"), counts):
            result[key] = int(count)
    return result


def main():
    target = resolve_database_target(require_sqlite_path=True)
    if is_postgres_target(target):
        conn = connect_database(target)
    else:
        conn = sqlite3.connect(Path(target).resolve().as_uri() + "?mode=ro", uri=True)
    with closing(conn):
        if is_postgres(conn):
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        else:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
        result = inspect(conn, owner_email=os.environ.get("PWA_OWNER_EMAIL"))
        result["observed_at"] = datetime.now(timezone.utc).isoformat()
        result["backend"] = "postgresql" if is_postgres(conn) else "sqlite"
        revision = os.environ.get("APP_REVISION", "")
        result["revision"] = revision if re.fullmatch(r"[0-9a-f]{40}", revision) else "UNSET"
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("STUDENT_PREFLIGHT_STOP type=" + type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
