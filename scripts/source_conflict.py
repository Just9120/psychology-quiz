"""Record a source conflict in a new private processing snapshot.

This is an editorial hold, not a publication or a claim that the source was
fully processed. Existing snapshots stay immutable for later comparison.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.source_inventory import InventoryError, processing_status
from scripts.source_inventory_report import _read, _snapshot, private_json_target


def record_conflict(current: dict, prior: dict, source_id: str, *, reason: str,
                    locator: str, related_source_ids: list[str], reviewed_at: str) -> dict:
    snapshot = _snapshot(current)
    if not isinstance(prior, dict):
        raise InventoryError("invalid_processing_records")
    processing_status(snapshot, prior)
    item = snapshot["files"].get(source_id)
    if item is None:
        raise InventoryError("source_not_in_current_inventory")
    if (not isinstance(reason, str) or not reason.strip()
            or not isinstance(locator, str) or not locator.strip()
            or not isinstance(related_source_ids, list)
            or any(not isinstance(related, str) or related == source_id
                   or related not in snapshot["files"] for related in related_source_ids)
            or len(set(related_source_ids)) != len(related_source_ids)):
        raise InventoryError("invalid_conflict_evidence")
    revision = [item["modified_time"], item["title"], item["mime_type"]]
    record = {"revision": revision, "review_state": "conflict",
              "reason": reason.strip(), "locator": locator.strip(),
              "related_source_ids": sorted(related_source_ids),
              "reviewed_at": reviewed_at}
    if prior.get(source_id) == record:
        raise InventoryError("conflict_review_already_recorded")
    updated = dict(prior)
    updated[source_id] = record
    return updated


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Hold one private source revision for editorial conflict review")
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--prior", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--related-source-id", action="append", default=[])
    parser.add_argument("--reason", required=True)
    parser.add_argument("--locator", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        target = private_json_target(args.output, REPO_ROOT,
                                     error_code="private_conflict_requires_ignored_data_json")
        updated = record_conflict(
            _read(args.current), _read(args.prior), args.source_id,
            reason=args.reason, locator=args.locator,
            related_source_ids=args.related_source_id,
            reviewed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(updated, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (InventoryError, OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError) as error:
        print("SOURCE_CONFLICT_STOP: " + (str(error) if isinstance(error, InventoryError)
                                          else type(error).__name__), file=sys.stderr)
        return 1
    print("SOURCE_CONFLICT_RECORDED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
