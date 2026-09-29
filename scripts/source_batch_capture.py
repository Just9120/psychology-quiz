"""Capture multiple private source revisions into one pending-review record.

The manifest, extracted texts and output stay in ignored data/. Capture is
atomic at the record level; it never approves a source or publishes content.
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

from app.source_inventory import InventoryError
from scripts.source_capture import capture
from scripts.source_inventory_report import _read, private_json_target


def _private_content_path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise InventoryError("invalid_batch_content_path")
    path = (REPO_ROOT / value).resolve()
    if path.parent != (REPO_ROOT / "data").resolve():
        raise InventoryError("batch_content_requires_private_data")
    return path


def capture_batch(current: dict, prior: dict, manifest: dict) -> dict:
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or not isinstance(manifest.get("sources"), list)
            or not manifest["sources"]):
        raise InventoryError("invalid_batch_manifest")
    updated, seen = prior, set()
    for item in manifest["sources"]:
        if (not isinstance(item, dict)
                or not {"source_id", "content", "snapshot_kind"} <= set(item)
                or set(item) - {"source_id", "content", "snapshot_kind", "extraction_profile"}
                or ("extraction_profile" in item and item["extraction_profile"] is None)
                or not isinstance(item["source_id"], str)
                or not item["source_id"]
                or item["source_id"] in seen):
            raise InventoryError("invalid_batch_entry")
        seen.add(item["source_id"])
        updated = capture(current, updated, item["source_id"],
                          _private_content_path(item["content"]),
                          item["snapshot_kind"],
                          extraction_profile=item.get("extraction_profile"))
    return updated


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Capture private sources for later manual review")
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        manifest_path = private_json_target(args.manifest, REPO_ROOT,
                                            error_code="private_batch_manifest_required")
        target = private_json_target(args.output, REPO_ROOT,
                                     error_code="private_batch_output_required")
        updated = capture_batch(_read(args.current), _read(args.prior) if args.prior else {},
                                _read(manifest_path))
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(updated, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (InventoryError, OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError) as error:
        print("SOURCE_BATCH_CAPTURE_STOP: " +
              (str(error) if isinstance(error, InventoryError) else type(error).__name__),
              file=sys.stderr)
        return 1
    print("SOURCE_BATCH_CAPTURE_PENDING_REVIEW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
