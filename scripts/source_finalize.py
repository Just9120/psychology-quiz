"""Close a captured private source review without publishing any derivative.

The reviewer must supply the same local content used at capture time. This
checks the digest and Drive metadata revision before recording the decision;
it cannot prove that the local file came from Drive or that its claims are true.
Conflicted sources require a separate editorial resolution and stay held.
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

from app.source_inventory import InventoryError, processing_status, valid_review_timestamp
from scripts.source_capture import capture
from scripts.source_inventory_report import _read, _snapshot, private_json_target


def finalize(current: dict, prior: dict, source_id: str, content_path: Path,
             *, reviewer: str, review_note: str, reviewed_at: str,
             conflict_resolution_note: str | None = None,
             source_kind: str | None = None) -> dict:
    snapshot = _snapshot(current)
    if not isinstance(prior, dict):
        raise InventoryError("invalid_processing_records")
    states = processing_status(snapshot, prior)
    if source_id not in states:
        raise InventoryError("source_not_in_current_inventory")
    if states[source_id] != "pending_review":
        raise InventoryError("source_not_pending_review")
    if (not isinstance(reviewer, str) or not reviewer.strip()
            or not isinstance(review_note, str) or not review_note.strip()
            or not valid_review_timestamp(reviewed_at)):
        raise InventoryError("review_evidence_required")
    if source_kind is not None and (
            not isinstance(source_kind, str)
            or source_kind not in {"learning_material", "bibliography"}):
        raise InventoryError("invalid_reviewed_source_kind")
    pending = prior[source_id]
    conflict_hold = pending.get("conflict_hold")
    if conflict_hold is not None and (
            not isinstance(conflict_hold, dict)
            or not isinstance(conflict_resolution_note, str)
            or not conflict_resolution_note.strip()):
        raise InventoryError("conflict_resolution_required")
    if conflict_hold is None and conflict_resolution_note is not None:
        raise InventoryError("conflict_resolution_without_hold")
    if pending.get("snapshot_kind") not in {"file_bytes", "extracted_text"}:
        raise InventoryError("captured_snapshot_required")
    captured = capture(current, prior, source_id, content_path, pending["snapshot_kind"])[source_id]
    if captured["snapshot_sha256"] != pending.get("snapshot_sha256"):
        raise InventoryError("captured_content_changed")
    updated = dict(prior)
    completed = {**pending, "review_state": "processed",
                 "reviewer": reviewer.strip(), "review_note": review_note.strip(),
                 "reviewed_at": reviewed_at}
    if source_kind is not None:
        completed["source_kind"] = source_kind
        completed["source_kind_review"] = {
            "reviewer": reviewer.strip(), "reviewed_at": reviewed_at,
            "note": review_note.strip(),
        }
    completed.pop("conflict_hold", None)
    if conflict_resolution_note is not None:
        # The current snapshot must retain the original objection after the
        # hold is lifted; otherwise later derivative reviews lose its scope.
        completed["resolved_conflict_hold"] = dict(conflict_hold)
        completed["conflict_resolution_note"] = conflict_resolution_note.strip()
    updated[source_id] = completed
    processing_status(snapshot, updated)
    return updated


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Record a completed private source review")
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--prior", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--content", required=True, type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--review-note", required=True)
    parser.add_argument("--source-kind", choices=("learning_material", "bibliography"),
                        help="reviewed purpose; required for signing an unregistered source")
    parser.add_argument("--conflict-resolution-note")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        target = private_json_target(args.output, REPO_ROOT,
                                     error_code="private_finalize_requires_ignored_data_json")
        updated = finalize(_read(args.current), _read(args.prior), args.source_id,
                           args.content, reviewer=args.reviewer, review_note=args.review_note,
                           reviewed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           conflict_resolution_note=args.conflict_resolution_note,
                           source_kind=args.source_kind)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(updated, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (InventoryError, OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError) as error:
        print("SOURCE_FINALIZE_STOP: " + (str(error) if isinstance(error, InventoryError)
                                          else type(error).__name__), file=sys.stderr)
        return 1
    print("SOURCE_REVIEW_RECORDED; publication unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
