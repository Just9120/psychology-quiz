"""Read-only PostgreSQL backup inventory; never deletes or restores anything."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.postgres_config import PG_DATABASE, PG_SERVICE
from scripts.postgres_backup import read_verified_record

RELEASE = re.compile(r"release-[A-Za-z0-9_-]+")


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("missing_time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("utc_time_required")
    return parsed


def _regular(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("regular_file_required")


def build_plan(root, *, retention_days=None, min_verified=2, pinned=(), now=None):
    """Only exact owned-format, digest-verified records can become candidates.

    Failed, unknown, legacy timestamp-less and externally pinned records stay.
    Keep at least two recent verified points per cluster, regardless of age.
    Output is a proposal only; no cleanup operation is implemented.
    """
    if retention_days is not None and (type(retention_days) is not int or not 1 <= retention_days <= 3650):
        raise ValueError("invalid_retention_days")
    if type(min_verified) is not int or min_verified < 2:
        raise ValueError("at_least_two_verified_points_required")
    root = Path(root)
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError("ordinary_backup_directory_required")
    root = root.resolve(strict=True)
    pin_names = set()
    for value in pinned:
        value = Path(value)
        if value.name != "record.json" or value.parent.parent.resolve() != root:
            raise ValueError("pin_outside_backup_root")
        pin_names.add(value.parent.name)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("timezone_required")
    rows, valid = [], []
    for directory in sorted(root.iterdir()):
        row = {"entry": directory.name, "action": "KEEP", "reason": "unrecognized_entry"}
        rows.append(row)
        if not RELEASE.fullmatch(directory.name) or not stat.S_ISDIR(directory.lstat().st_mode):
            continue
        try:
            _regular(directory / "record.json")
            _regular(directory / "database.dump")
            record = read_verified_record(directory / "record.json")
            source = record["source"]
            if not isinstance(source, dict):
                raise ValueError("backup_identity_required")
            if (source.get("project") != "psychology-quiz" or source.get("database") != PG_DATABASE
                    or source.get("service") != PG_SERVICE or not re.fullmatch(r"[0-9]+", str(source.get("cluster", "")))):
                raise ValueError("backup_identity_required")
            created, verified = _timestamp(record.get("created_at")), _timestamp(record.get("verified_at"))
            if not created <= verified <= now:
                raise ValueError("invalid_backup_times")
            row.update(reason="verified", verified_at=verified.isoformat(), dump_bytes=record["dump_bytes"])
            valid.append((str(source["cluster"]), verified, directory.name, row))
        except (ValueError, KeyError, TypeError, OSError):
            # Never expose record text, DB contents, credentials or exception messages.
            row["reason"] = "unverified_or_legacy_record"
    groups = {}
    for cluster, verified, name, row in valid:
        groups.setdefault(cluster, []).append((verified, name, row))
    for records in groups.values():
        records.sort(key=lambda item: (item[0], item[1]), reverse=True)
        newest = {name for _, name, _ in records[:min_verified]}
        for verified, name, row in records:
            if name in pin_names:
                row["reason"] = "pinned_recovery_point"
            elif name in newest:
                row["reason"] = "minimum_verified_points"
            elif retention_days is None:
                row["reason"] = "retention_unset"
            elif verified >= now - timedelta(days=retention_days):
                row["reason"] = "within_retention"
            else:
                row.update(action="REVIEW_CANDIDATE", reason="older_than_retention")
    return {"format": "psychology-backup-retention-plan-v1", "observed_at": now.isoformat(),
            "retention_days": retention_days, "min_verified_per_cluster": min_verified,
            "plan_only": True, "deletion_supported": False, "entries": rows,
            "candidate_count": sum(row["action"] == "REVIEW_CANDIDATE" for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--retention-days", type=int)
    parser.add_argument("--min-verified", type=int, default=2)
    parser.add_argument("--pin-record", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        print(json.dumps(build_plan(args.backup_root, retention_days=args.retention_days,
              min_verified=args.min_verified, pinned=args.pin_record), sort_keys=True))
    except (OSError, ValueError):
        print("BACKUP_RETENTION_PLAN_STOP: inspect private backup metadata; no changes made", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
