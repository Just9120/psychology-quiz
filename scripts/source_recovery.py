"""Recover pending captures with known holds; never restore lost approvals.

This cannot establish that all past editorial records were recovered. It only
preserves objections present in the supplied candidate snapshots.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.source_inventory import InventoryError, processing_status
from scripts.source_inventory_report import _read, _snapshot, private_json_target


def recover(current: dict, captures: dict, candidates: list[dict]) -> dict:
    snapshot = _snapshot(current)
    if (not isinstance(captures, dict) or not isinstance(candidates, list)
            or any(not isinstance(candidate, dict) for candidate in candidates)):
        raise InventoryError("invalid_recovery_records")
    states = processing_status(snapshot, captures)
    if not captures or any(states.get(key) != "pending_review" for key in captures):
        raise InventoryError("pending_captures_required")
    for candidate in candidates:
        processing_status(snapshot, candidate)
    result = {key: dict(value) for key, value in captures.items()}
    for key, capture in result.items():
        if (capture.get("snapshot_kind") not in {"file_bytes", "extracted_text"}
                or not isinstance(capture.get("snapshot_sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", capture["snapshot_sha256"]) is None):
            raise InventoryError("captured_snapshot_required")
        if any(field.startswith("search_") for field in capture):
            raise InventoryError("capture_search_approval_not_allowed")
        holds = []
        if capture.get("conflict_hold") is not None:
            holds.append(capture["conflict_hold"])
        for candidate in candidates:
            previous = candidate.get(key)
            if previous is None:
                continue
            if previous.get("review_state") == "conflict":
                holds.append({"reason": previous["reason"], "locator": previous["locator"],
                              "related_source_ids": previous.get("related_source_ids", [])})
            elif previous.get("conflict_hold") is not None:
                holds.append(previous["conflict_hold"])
        if holds:
            # Disagreement needs editorial reconstruction, never last-writer-wins.
            if any(hold != holds[0] for hold in holds[1:]):
                raise InventoryError("conflicting_recovery_holds")
            capture["conflict_hold"] = dict(holds[0])
    processing_status(snapshot, result)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--prior", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        target = private_json_target(args.output, REPO_ROOT,
                                     error_code="private_recovery_output_required")
        current = _read(args.current)
        result = recover(current, _read(args.captures), [_read(path) for path in args.prior])
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                       "w", encoding="utf-8") as output:
            json.dump(result, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (InventoryError, OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError) as error:
        print("SOURCE_RECOVERY_STOP: " + (str(error) if isinstance(error, InventoryError) else type(error).__name__))
        return 1
    print("SOURCE_CAPTURES_RECOVERED records=" + str(len(result))
          + " holds=" + str(sum("conflict_hold" in record for record in result.values()))
          + " approvals=0; supplied snapshots only, full history unconfirmed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
