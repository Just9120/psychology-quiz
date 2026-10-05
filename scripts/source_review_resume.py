"""Read-only consistency guard for resuming private saved-source review.

This checks recorded evidence, not whether a person actually read a source.
It never approves content, advances ranges, or changes a checkpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.source_inventory import InventoryError
from scripts.source_batch_capture import _private_content_path

RAW_COORDINATES = "Original UTF-8 decoded bytes including BOM and CR; raw publication locator coordinates"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _records_by_source(records: object, error: str) -> dict:
    if not isinstance(records, list):
        raise InventoryError(error)
    indexed = {}
    for record in records:
        if (not isinstance(record, dict)
                or not isinstance(record.get("source_id"), str)
                or not record["source_id"] or record["source_id"] in indexed):
            raise InventoryError(error)
        indexed[record["source_id"]] = record
    return indexed


def resume_review(ledger: dict, queue: dict, processing: dict, checkpoint: dict,
                  *, partial: dict | None = None, capture: bytes | None = None) -> dict:
    """Reject stale/overlapping evidence before selecting the next unread range."""
    if not all(isinstance(value, dict) for value in (ledger, queue, processing, checkpoint)):
        raise InventoryError("invalid_review_checkpoint")
    done = _records_by_source(ledger.get("records"), "invalid_review_ledger")
    pending = _records_by_source(queue.get("remaining_sources"), "invalid_review_queue")
    if done.keys() & pending.keys():
        raise InventoryError("completed_source_requeued")
    if (done.keys() | pending.keys()) != processing.keys():
        raise InventoryError("review_queue_coverage_mismatch")
    for source_id, record in done.items():
        current = processing[source_id]
        if (record.get("full_capture_read") is not True
                or not isinstance(current, dict)
                or not isinstance(record.get("snapshot_sha256"), str)
                or not SHA256.fullmatch(record["snapshot_sha256"])
                or current.get("review_state") == "pending_review"
                or record.get("snapshot_sha256") != current.get("snapshot_sha256")):
            raise InventoryError("completed_review_binding_mismatch")
        # Equal text bytes do not establish that a recorded review belongs to
        # the current source edition. Legacy hash-only records remain usable
        # as text evidence; do not fabricate a revision binding for them.
        if "revision" in record and (
                not isinstance(record["revision"], list)
                or len(record["revision"]) != 3
                or any(not isinstance(value, str) or not value for value in record["revision"])
                or record["revision"] != current.get("revision")):
            raise InventoryError("completed_review_revision_mismatch")
    for field, owner, count in (
        ("full_capture_read", ledger, len(done)),
        ("full_read_evidence", queue, len(done)),
        ("full_review_evidence", checkpoint, len(done)),
        ("remaining_without_full_review_evidence", queue, len(pending)),
        ("remaining_without_full_review_evidence", checkpoint, len(pending)),
    ):
        if type(owner.get(field)) is not int or owner[field] != count:
            raise InventoryError("review_checkpoint_count_mismatch")
    active = checkpoint.get("active_content_review")
    if not pending:
        if active is not None or partial is not None:
            raise InventoryError("completed_corpus_has_active_review")
        return {"recorded_complete": len(done), "remaining": 0, "next_range": None,
                "publication_approval": False}
    next_item = next(iter(pending.values()))
    next_checkpoint = checkpoint.get("next_remaining_source")
    if (not isinstance(next_checkpoint, dict)
            or next_checkpoint.get("source_id") != next_item["source_id"]):
        raise InventoryError("review_checkpoint_next_source_mismatch")
    if active is None:
        if partial is not None:
            raise InventoryError("unbound_partial_review")
        return {"recorded_complete": len(done), "remaining": len(pending),
                "next_raw_character": 0, "partial_capture_verified": False,
                "publication_approval": False}
    if (not isinstance(active, dict) or not isinstance(partial, dict)
            or active.get("source_id") != next_item["source_id"]
            or partial.get("source_id") != next_item["source_id"]
            or partial.get("full_capture_read") is not False
            or partial.get("coordinate_domain") != RAW_COORDINATES
            or not isinstance(capture, bytes)):
        raise InventoryError("invalid_active_review_binding")
    digest = hashlib.sha256(capture).hexdigest()
    current = processing[next_item["source_id"]]
    if (not isinstance(current, dict)
            or digest != partial.get("snapshot_sha256")
            or digest != current.get("snapshot_sha256")
            or partial.get("revision") != current.get("revision")):
        raise InventoryError("active_review_capture_changed")
    try:
        text = capture.decode("utf-8")  # Preserve BOM/CR: raw publication coordinates.
    except UnicodeError as error:
        raise InventoryError("invalid_review_capture_text") from error
    ranges = partial.get("read_ranges")
    if not isinstance(ranges, list) or partial.get("characters") != len(text):
        raise InventoryError("invalid_review_ranges")
    cursor = 0
    for bounds in ranges:
        if (not isinstance(bounds, list) or len(bounds) != 2
                or any(type(value) is not int for value in bounds)
                or bounds[0] != cursor or not cursor < bounds[1] <= len(text)):
            raise InventoryError("invalid_review_ranges")
        cursor = bounds[1]
    if (type(partial.get("next_raw_character")) is not int
            or type(active.get("next_raw_character")) is not int
            or cursor != partial["next_raw_character"]
            or cursor != active["next_raw_character"] or cursor == len(text)):
        raise InventoryError("review_checkpoint_cursor_mismatch")
    return {"recorded_complete": len(done), "remaining": len(pending),
            "next_raw_character": cursor, "remaining_range": [cursor, len(text)],
            "partial_capture_verified": True, "publication_approval": False}


def _read_private(value: str) -> dict:
    return json.loads(_private_content_path(value).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate private review resume state without advancing it")
    for name in ("ledger", "queue", "processing", "checkpoint"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        checkpoint = _read_private(args.checkpoint)
        active = checkpoint.get("active_content_review")
        partial = _read_private(active["receipt"]) if active else None
        capture = _private_content_path(partial["capture"]).read_bytes() if partial else None
        result = resume_review(_read_private(args.ledger), _read_private(args.queue),
                               _read_private(args.processing), checkpoint,
                               partial=partial, capture=capture)
    except (InventoryError, OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as error:
        code = str(error) if isinstance(error, InventoryError) else type(error).__name__
        print("SOURCE_REVIEW_RESUME_STOP: " + code, file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
