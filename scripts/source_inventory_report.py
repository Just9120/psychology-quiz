"""Read a private Drive metadata export and print aggregate review work only.

Input files belong in ignored private operator storage such as data/. This
command never writes source IDs, titles, paths or extracted text to the repo.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.source_inventory import InventoryError, complete_listing, link_lessons, processing_status, reconcile, scan


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("folders"), dict):
        raise InventoryError("invalid_inventory_export")
    return scan(value.get("root_id"), {folder: complete_listing(pages)
                                       for folder, pages in value["folders"].items()})


def report(current: dict, *, previous: dict | None = None,
           processed: dict | None = None, links: list | None = None) -> dict:
    snapshot = _snapshot(current)
    if processed is not None and not isinstance(processed, dict):
        raise InventoryError("invalid_processing_records")
    if links is not None and not isinstance(links, list):
        raise InventoryError("invalid_lesson_links")
    states = processing_status(snapshot, processed or {})
    lessons = link_lessons(snapshot, links or [])
    changes = reconcile(_snapshot(previous), snapshot) if previous is not None else None
    by_format: dict[str, Counter] = {}
    for file_id, item in snapshot["files"].items():
        by_format.setdefault(item["mime_type"], Counter())[states[file_id]] += 1
    return {"folders": snapshot["folders"], "files": len(snapshot["files"]),
            "processing": dict(sorted(Counter(states.values()).items())),
            "processing_by_format": {mime: dict(sorted(counts.items()))
                                     for mime, counts in sorted(by_format.items())},
            "linked_lessons": len(lessons),
            "changes": ({kind: len(ids) for kind, ids in changes.items()} if changes else None)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate private recursive source metadata without exposing file IDs")
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--processed", type=Path)
    parser.add_argument("--links", type=Path)
    args = parser.parse_args(argv)
    try:
        value = report(_read(args.current),
                       previous=_read(args.previous) if args.previous else None,
                       processed=_read(args.processed) if args.processed else None,
                       links=_read(args.links) if args.links else None)
    except (InventoryError, OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError) as error:
        print("SOURCE_INVENTORY_STOP: " + (str(error) if isinstance(error, InventoryError)
                                             else type(error).__name__), file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
