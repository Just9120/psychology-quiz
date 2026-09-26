"""Read a private Drive metadata export and print aggregate review work only.

Input files belong in ignored private operator storage such as data/. The
default output is aggregate-only; an optional file-level queue is written only
to a new JSON file directly in ignored data/.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.source_inventory import (
    InventoryError, complete_listing, link_lessons, private_review_queue,
    processing_status, reconcile, reviewed_graph, scan,
)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("folders"), dict):
        raise InventoryError("invalid_inventory_export")
    return scan(value.get("root_id"), {folder: complete_listing(pages)
                                       for folder, pages in value["folders"].items()})


def private_json_target(raw_target: Path, repo_root: Path, *,
                        error_code: str = "private_queue_requires_ignored_data_json") -> Path:
    data_root = (repo_root / "data").resolve()
    target = raw_target.resolve()
    if target.parent != data_root or target.suffix.lower() != ".json" or not data_root.is_dir():
        raise InventoryError(error_code)
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--",
         target.relative_to(repo_root.resolve()).as_posix()],
        cwd=repo_root, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if ignored.returncode != 0:
        raise InventoryError(error_code)
    return target


def report(current: dict, *, previous: dict | None = None,
           processed: dict | None = None, links: list | None = None,
           registry: dict | None = None, curriculum: dict | None = None) -> dict:
    snapshot = _snapshot(current)
    if processed is not None and not isinstance(processed, dict):
        raise InventoryError("invalid_processing_records")
    if links is not None and not isinstance(links, list):
        raise InventoryError("invalid_lesson_links")
    states = processing_status(snapshot, processed or {})
    lessons = link_lessons(snapshot, links or [])
    changes = reconcile(_snapshot(previous), snapshot) if previous is not None else None
    if (registry is None) != (curriculum is None):
        raise InventoryError("reviewed_graph_inputs_required")
    by_format: dict[str, Counter] = {}
    for file_id, item in snapshot["files"].items():
        by_format.setdefault(item["mime_type"], Counter())[states[file_id]] += 1
    result = {"folders": snapshot["folders"], "files": len(snapshot["files"]),
            "processing": dict(sorted(Counter(states.values()).items())),
            "processing_by_format": {mime: dict(sorted(counts.items()))
                                     for mime, counts in sorted(by_format.items())},
            "linked_lessons": len(lessons),
            "changes": ({kind: len(ids) for kind, ids in changes.items()} if changes else None)}
    if registry is not None:
        result["reviewed_graph"] = reviewed_graph(snapshot, registry, curriculum)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate private recursive source metadata without exposing file IDs")
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--processed", type=Path)
    parser.add_argument("--links", type=Path)
    parser.add_argument("--reviewed", action="store_true",
                        help="compare live metadata to repository source and curriculum reviews")
    parser.add_argument("--private-queue", type=Path,
                        help="write a new per-file review queue only in ignored data/; requires --reviewed")
    args = parser.parse_args(argv)
    try:
        if args.private_queue and not args.reviewed:
            raise InventoryError("private_queue_requires_reviewed")
        current = _read(args.current)
        previous = _read(args.previous) if args.previous else None
        processed = _read(args.processed) if args.processed else None
        links = _read(args.links) if args.links else None
        registry = _read(REPO_ROOT / "content/source-corpus.json") if args.reviewed else None
        curriculum = _read(REPO_ROOT / "content/curriculum.json") if args.reviewed else None
        reviews = _read(REPO_ROOT / "content/publication-reviews.json") if args.private_queue else None
        quality_reviews = _read(REPO_ROOT / "content/learning-quality-reviews.json") if args.private_queue else None
        value = report(current, previous=previous, processed=processed, links=links,
                       registry=registry, curriculum=curriculum)
        if args.private_queue:
            target = private_json_target(args.private_queue, REPO_ROOT)
            queue = private_review_queue(_snapshot(current), registry, curriculum,
                                         processed=processed,
                                         previous=_snapshot(previous) if previous is not None else None,
                                         reviews=reviews, quality_reviews=quality_reviews)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(queue, output, ensure_ascii=False, indent=2)
                output.write("\n")
    except (InventoryError, OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError) as error:
        print("SOURCE_INVENTORY_STOP: " + (str(error) if isinstance(error, InventoryError)
                                             else type(error).__name__), file=sys.stderr)
        return 1
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
