"""Approve exact private source passages for operator-only search indexing.

This records an editorial decision in a new ignored processing snapshot. It
does not index, publish, or change any existing source review file.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.source_inventory import InventoryError, processing_status, unresolved_related_conflicts
from scripts.source_batch_capture import _private_content_path
from scripts.source_inventory_report import _read, _snapshot, private_json_target


def approve_ranges(current: dict, prior: dict, source_id: str, content: Path,
                   ranges: list[list[int]], *, reviewer: str, note: str,
                   reviewed_at: str) -> dict:
    snapshot = _snapshot(current)
    if (not isinstance(prior, dict)
            or processing_status(snapshot, prior).get(source_id) != "processed"
            or source_id in unresolved_related_conflicts(prior)):
        raise InventoryError("current_processed_source_required")
    record = prior[source_id]
    if (record.get("snapshot_kind") != "extracted_text"
            or not isinstance(reviewer, str) or not reviewer.strip()
            or not isinstance(note, str) or not note.strip()):
        raise InventoryError("search_review_evidence_required")
    raw = content.read_bytes()
    if hashlib.sha256(raw).hexdigest() != record.get("snapshot_sha256"):
        raise InventoryError("captured_content_changed")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as error:
        raise InventoryError("invalid_source_text") from error
    if not isinstance(ranges, list) or not ranges or len(ranges) > 100:
        raise InventoryError("invalid_private_search_ranges")
    previous_end = 0
    for bounds in ranges:
        if (not isinstance(bounds, list) or len(bounds) != 2
                or any(type(value) is not int for value in bounds)
                or not 0 <= bounds[0] < bounds[1] <= len(text)
                or bounds[0] < previous_end or not text[bounds[0]:bounds[1]].strip()):
            raise InventoryError("invalid_private_search_ranges")
        previous_end = bounds[1]
    updated = dict(prior)
    updated[source_id] = {**record, "search_ranges": ranges,
                          "search_reviewer": reviewer.strip(),
                          "search_review_note": note.strip(),
                          "search_reviewed_at": reviewed_at}
    return updated


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Approve exact private search passages")
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--prior", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--content", required=True)
    parser.add_argument("--range", dest="ranges", action="append", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--note", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        target = private_json_target(args.output, REPO_ROOT,
                                     error_code="private_search_review_output_required")
        bounds = []
        for value in args.ranges:
            start, separator, end = value.partition(":")
            if not separator or not start.isdecimal() or not end.isdecimal():
                raise InventoryError("invalid_private_search_ranges")
            bounds.append([int(start), int(end)])
        updated = approve_ranges(_read(args.current), _read(args.prior), args.source_id,
                                 _private_content_path(args.content), bounds,
                                 reviewer=args.reviewer, note=args.note,
                                 reviewed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(updated, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (InventoryError, OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError) as error:
        print("SOURCE_SEARCH_REVIEW_STOP: " +
              (str(error) if isinstance(error, InventoryError) else type(error).__name__),
              file=sys.stderr)
        return 1
    print("PRIVATE_SEARCH_PASSAGES_RECORDED; index unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
