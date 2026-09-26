"""Capture a private source digest at a Drive inventory revision for manual review.

This command never approves or publishes a derivative. It reads operator-owned
content and writes only a new, ignored processing record in data/.
"""
from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.source_inventory import InventoryError, processing_status
from scripts.source_inventory_report import _read, _snapshot, private_json_target


def capture(current: dict, prior: dict, source_id: str, content_path: Path,
            snapshot_kind: str) -> dict:
    """Return a fresh pending-review map; preserve prior records verbatim."""
    snapshot = _snapshot(current)
    if not isinstance(prior, dict):
        raise InventoryError("invalid_processing_records")
    processing_status(snapshot, prior)
    item = snapshot["files"].get(source_id)
    if item is None:
        raise InventoryError("source_not_in_current_inventory")
    revision = [item["modified_time"], item["title"], item["mime_type"]]
    previous = prior.get(source_id)
    if (isinstance(previous, dict) and previous.get("review_state") == "processed"
            and tuple(previous.get("revision", ())) == tuple(revision)):
        raise InventoryError("source_revision_already_processed")
    if snapshot_kind not in {"file_bytes", "extracted_text"}:
        raise InventoryError("invalid_snapshot_kind")
    digest = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")() if snapshot_kind == "extracted_text" else None
    bytes_read = 0
    with content_path.open("rb") as content:
        before = os.fstat(content.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size == 0:
            raise InventoryError("source_content_not_regular_file")
        while chunk := content.read(1024 * 1024):
            bytes_read += len(chunk)
            if decoder is not None:
                decoder.decode(chunk)
            digest.update(chunk)
        if decoder is not None:
            decoder.decode(b"", final=True)
        after = os.fstat(content.fileno())
    if (bytes_read != before.st_size or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns):
        raise InventoryError("source_content_changed_during_capture")
    updated = dict(prior)
    updated[source_id] = {
        "revision": revision,
        "review_state": "pending_review",
        "snapshot_kind": snapshot_kind,
        "snapshot_sha256": digest.hexdigest(),
    }
    return updated


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Capture one private source for manual review")
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--content", required=True, type=Path)
    parser.add_argument("--snapshot-kind", required=True, choices=("file_bytes", "extracted_text"))
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        target = private_json_target(args.output, REPO_ROOT,
                                     error_code="private_capture_requires_ignored_data_json")
        prior = _read(args.prior) if args.prior else {}
        updated = capture(_read(args.current), prior, args.source_id,
                          args.content, args.snapshot_kind)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(updated, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (InventoryError, OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError) as error:
        print("SOURCE_CAPTURE_STOP: " + (str(error) if isinstance(error, InventoryError)
                                         else type(error).__name__), file=sys.stderr)
        return 1
    print("SOURCE_CAPTURE_PENDING_REVIEW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
