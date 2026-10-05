"""Locate bibliography across private captures without publishing source data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.bibliography_ingestion import discover_bibliography
from app.source_inventory import InventoryError
from scripts.source_batch_capture import _private_content_path
from scripts.source_inventory_report import _read, _snapshot, private_json_target


def _private_original_path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise InventoryError("invalid_bibliography_original_path")
    path = (ROOT / value).resolve()
    data_root = (ROOT / "data").resolve()
    if not path.is_relative_to(data_root) or path.suffix.lower() != ".pdf":
        raise InventoryError("bibliography_original_requires_private_pdf")
    return path


def run(current, processing, capture_manifest, catalogue):
    snapshot = _snapshot(current)
    if (not isinstance(capture_manifest, dict) or capture_manifest.get("schema_version") != 1
            or not isinstance(capture_manifest.get("sources"), list)):
        raise InventoryError("invalid_bibliography_manifest")
    captures = []
    for item in capture_manifest["sources"]:
        if not isinstance(item, dict):
            raise InventoryError("invalid_bibliography_manifest")
        record = processing.get(item.get("source_id"), {})
        raw = _private_content_path(item.get("content")).read_bytes()
        if record.get("snapshot_kind") == "extracted_text":
            text_sha = record.get("snapshot_sha256")
        elif record.get("snapshot_kind") == "file_bytes":
            # Discovery may use a derived OCR capture, but must retain the
            # identity of its original. This receipt is not publication review
            # and does not prove OCR completeness or scientific validity.
            binding = _read(_private_content_path(item.get("derivation_receipt")))
            original = _private_original_path(item.get("original")).read_bytes()
            text_sha = hashlib.sha256(raw).hexdigest()
            original_sha = hashlib.sha256(original).hexdigest()
            if (not isinstance(binding, dict) or binding.get("schema_version") != 1
                    or binding.get("source_id") != item.get("source_id")
                    or binding.get("revision") != record.get("revision")
                    or binding.get("original_sha256") != original_sha
                    or original_sha != record.get("snapshot_sha256")
                    or binding.get("derived_text_sha256") != text_sha
                    or not isinstance(binding.get("extraction_profile"), str)
                    or not binding["extraction_profile"].strip()):
                raise InventoryError("bibliography_invalid_derivation_binding")
        else:
            raise InventoryError("bibliography_extracted_capture_required")
        captures.append({"source_id": item["source_id"], "content": raw,
                         "revision": record.get("revision"),
                         "snapshot_sha256": text_sha})
    result = discover_bibliography(snapshot, captures, catalogue,
                                   capture_manifest.get("catalogue_aliases"))
    # Character locators and excerpts always refer to the derived text, never
    # byte offsets in a PDF. Carry both identities to subsequent private review.
    for mention in result["mentions"]:
        record = processing[mention["source_id"]]
        mention["original_snapshot_kind"] = record.get("snapshot_kind")
        mention["original_snapshot_sha256"] = record.get("snapshot_sha256")
    result["limitations"] = ("Candidate discovery only. Derived OCR does not "
                             "establish full reading, image coverage, identity "
                             "approval or publication permission.")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("current", "processed", "manifest", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        # All evidence and output live in ignored operator storage.
        paths = {name: private_json_target(getattr(args, name), ROOT)
                 for name in ("current", "processed", "manifest", "output")}
        catalogue = [entry for path in sorted((ROOT / "content/literature").glob("*.json"))
                     for entry in _read(path)]
        result = run(_read(paths["current"]), _read(paths["processed"]),
                     _read(paths["manifest"]), catalogue)
        descriptor = os.open(paths["output"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"captured_sources": result["captured_sources"],
                          "unread_sources": len(result["unread_source_ids"]),
                          "mention_candidates": len(result["mentions"]),
                          "evidence_counts": result["evidence_counts"],
                          "unknown_work_candidates": sum(not item["candidate_work_ids"]
                                                         for item in result["mentions"]),
                          "publication_approval": False}))
        return 0
    except (InventoryError, OSError, ValueError, KeyError, TypeError) as error:
        print("SOURCE_BIBLIOGRAPHY_STOP: " + (str(error) if isinstance(error, InventoryError)
                                             else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
