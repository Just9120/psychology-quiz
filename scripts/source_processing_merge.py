"""Combine independent private review snapshots without losing later holds.

Only identical records, disjoint fields of the same review state, and a newer
conflict replacing the exact same pending capture can be reconciled. All other
differences require an operator to inspect the source and choose a new review.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.source_inventory import InventoryError, processing_status
from scripts.source_inventory_report import _read, _snapshot, private_json_target

SEARCH_REVIEW_FIELDS = {
    "search_ranges", "search_reviewer", "search_review_note", "search_reviewed_at",
}


def merge_records(base: dict, supplement: dict) -> dict:
    if not isinstance(base, dict) or not isinstance(supplement, dict):
        raise InventoryError("invalid_processing_records")
    merged = dict(base)
    for source_id, incoming in supplement.items():
        if source_id not in merged:
            merged[source_id] = incoming
            continue
        current = merged[source_id]
        if current == incoming:
            continue
        if (not isinstance(current, dict) or not isinstance(incoming, dict)
                or current.get("revision") != incoming.get("revision")):
            raise InventoryError("conflicting_processing_revisions")
        if (current.get("review_state") == "conflict"
                and incoming.get("review_state") == "pending_review"
                and all(current.get(key) == value for key, value in incoming.items()
                        if key != "review_state")
                and all(key in current for key in incoming if key != "review_state")):
            # An editorial hold is stricter than the identical earlier capture.
            continue
        if (current.get("review_state") != incoming.get("review_state")
                or any(current[key] != incoming[key]
                       for key in current.keys() & incoming.keys())):
            raise InventoryError("conflicting_processing_review")
        different_keys = current.keys() ^ incoming.keys()
        current_search = current.keys() & SEARCH_REVIEW_FIELDS
        incoming_search = incoming.keys() & SEARCH_REVIEW_FIELDS
        if (current.get("review_state") != "processed"
                or different_keys - SEARCH_REVIEW_FIELDS
                or (current_search not in (set(), SEARCH_REVIEW_FIELDS))
                or (incoming_search not in (set(), SEARCH_REVIEW_FIELDS))
                or current_search == incoming_search):
            raise InventoryError("unsupported_processing_merge")
        merged[source_id] = {**incoming, **current}
    return merged


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--supplement", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        target = private_json_target(args.output, REPO_ROOT,
                                     error_code="private_processing_merge_output_required")
        snapshot = _snapshot(_read(args.current))
        base, supplement = _read(args.base), _read(args.supplement)
        if (not isinstance(base, dict) or not isinstance(supplement, dict)
                or set(base) - set(snapshot["files"])
                or set(supplement) - set(snapshot["files"])):
            raise InventoryError("processing_source_missing_from_inventory")
        for records in (base, supplement):
            if "changed_unprocessed" in processing_status(snapshot, records).values():
                raise InventoryError("stale_processing_review")
        merged = merge_records(base, supplement)
        states = processing_status(snapshot, merged)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(merged, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (InventoryError, OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError) as error:
        print("SOURCE_PROCESSING_MERGE_STOP: " +
              (str(error) if isinstance(error, InventoryError) else type(error).__name__),
              file=sys.stderr)
        return 1
    print("SOURCE_PROCESSING_MERGED records=" + str(len(merged)) +
          " conflict=" + str(sum(state == "conflict_review" for state in states.values())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
