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
import re
import stat
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.source_inventory import (
    InventoryError, combine_registries, complete_listing, link_lessons, private_review_queue,
    processing_status, reconcile, reviewed_graph, scan,
)
from app.content_publication import DRIVE_REF, LEGACY_SHA256, fingerprint


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _snapshot(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("folders"), dict):
        raise InventoryError("invalid_inventory_export")
    return scan(value.get("root_id"), {folder: complete_listing(pages)
                                       for folder, pages in value["folders"].items()})


def legacy_derivative_links(repo_root: Path, baseline: dict, quality_reviews: dict, *,
                            expected_sha256: str | None = None) -> tuple[dict[str, list[str]], list[str]]:
    """Map unchanged legacy items using direct refs or explicit quality evidence."""
    if (not isinstance(baseline, dict) or not isinstance(baseline.get("items"), dict)
            or fingerprint(baseline) != (expected_sha256 or LEGACY_SHA256)):
        raise InventoryError("invalid_legacy_baseline")
    if not isinstance(quality_reviews, dict):
        raise InventoryError("invalid_quality_reviews")
    linked, unmapped, seen = {}, [], set()
    for kind, pattern in (("questions", "**/*.json"), ("glossary", "*.json"),
                          ("literature", "*.json")):
        for path in sorted((repo_root / "content" / kind).glob(pattern)):
            entries = _read(path)
            if not isinstance(entries, list):
                raise InventoryError("invalid_derivative_file")
            for item in entries:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    raise InventoryError("invalid_derivative_file")
                derivative_id = f"{kind}:{item['id']}"
                if (item.get("status") != "approved"
                        or baseline["items"].get(derivative_id) != fingerprint(item)):
                    continue
                refs = [item.get("source_ref")] if kind == "questions" else item.get("source_refs")
                if refs is None or refs == [None]:
                    refs = []
                if not isinstance(refs, list):
                    raise InventoryError("invalid_legacy_source_refs")
                source_ids = set()
                for ref in refs:
                    match = DRIVE_REF.fullmatch(ref) if isinstance(ref, str) else None
                    if not isinstance(ref, str):
                        raise InventoryError("invalid_legacy_source_refs")
                    if match is not None:
                        source_ids.add(match.group(1))
                quality = quality_reviews.get(derivative_id)
                quality_ids = set()
                if (isinstance(quality, dict)
                        and quality.get("item_sha256") == fingerprint(item)):
                    evidence = quality.get("sources")
                    if (not isinstance(evidence, list) or not evidence
                            or any(not isinstance(ref, dict)
                                   or not isinstance(ref.get("source_id"), str)
                                   or not ref["source_id"] for ref in evidence)):
                        raise InventoryError("invalid_legacy_quality_sources")
                    quality_ids = {ref["source_id"] for ref in evidence}
                if derivative_id in seen:
                    raise InventoryError("duplicate_legacy_derivative")
                seen.add(derivative_id)
                all_ids = source_ids | quality_ids
                if all_ids:
                    linked[derivative_id] = sorted(all_ids)
                if not all_ids or (source_ids and quality_ids and source_ids != quality_ids):
                    unmapped.append(derivative_id)
    return linked, sorted(unmapped)


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


def private_registry_input(raw_path: Path, repo_root: Path) -> dict:
    """Read additional reviewed source metadata only from ignored operator storage."""
    if raw_path.is_symlink():
        raise InventoryError("private_registry_requires_owned_regular_file")
    path = private_json_target(raw_path, repo_root,
                               error_code="private_registry_requires_ignored_data_json")
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 20_000_000
            or (os.name == "posix" and
                (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077))):
        raise InventoryError("private_registry_requires_owned_regular_file")
    value = _read(path)
    if (not isinstance(value, dict) or set(value) != {"schema_version", "corpus_root_id", "sources"}
            or value["schema_version"] != 1 or not isinstance(value["sources"], list)):
        raise InventoryError("invalid_private_source_registry")
    return value


def private_topics_input(raw_path: Path, repo_root: Path) -> dict:
    """Read unreleased lesson metadata from ignored operator storage."""
    if raw_path.is_symlink():
        raise InventoryError("private_topics_requires_owned_regular_file")
    path = private_json_target(raw_path, repo_root,
                               error_code="private_topics_requires_ignored_data_json")
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 20_000_000
            or (os.name == "posix" and
                (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077))):
        raise InventoryError("private_topics_requires_owned_regular_file")
    value = _read(path)
    if (not isinstance(value, dict)
            or not {"schema_version", "corpus_root_id", "topics"} <= set(value)
            or set(value) - {"schema_version", "corpus_root_id", "topics", "disciplines"}
            or value["schema_version"] != 1 or not isinstance(value["topics"], dict)
            or not isinstance(value.get("disciplines", {}), dict)):
        raise InventoryError("invalid_private_topics")
    return value


def combine_private_topics(curriculum: dict, private: dict,
                           private_registry: dict) -> dict:
    """Overlay only privately reviewed sources, without changing public curriculum."""
    if (private["corpus_root_id"] != private_registry["corpus_root_id"]
            or not isinstance(curriculum, dict)
            or not isinstance(curriculum.get("topics"), dict)
            or not isinstance(curriculum.get("disciplines"), dict)):
        raise InventoryError("invalid_private_topics")
    allowed_sources = {source["id"] for source in private_registry["sources"]}
    disciplines = dict(curriculum["disciplines"])
    for discipline_id, discipline in private.get("disciplines", {}).items():
        if (not isinstance(discipline_id, str)
                or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", discipline_id) is None
                or not isinstance(discipline, dict)
                or set(discipline) != {"title"}
                or not isinstance(discipline["title"], str)
                or not discipline["title"].strip()):
            raise InventoryError("invalid_private_discipline")
        if discipline_id in disciplines:
            # A previously private discipline may have been published since
            # this immutable source-review snapshot was written. Reuse only
            # its exact public definition; never override or rename it.
            if disciplines[discipline_id] != discipline:
                raise InventoryError("invalid_private_discipline")
            continue
        if any(item["title"] == discipline["title"] for item in disciplines.values()):
            raise InventoryError("invalid_private_discipline")
        disciplines[discipline_id] = discipline
    topics = dict(curriculum["topics"])
    for topic_id, topic in private["topics"].items():
        if (not isinstance(topic_id, str) or re.fullmatch(r"t_[0-9a-f]{12}", topic_id) is None
                or topic_id in topics or not isinstance(topic, dict)
                or set(topic) != {"title", "discipline_id", "source"}
                or not isinstance(topic["title"], str) or not topic["title"].strip()
                or topic["discipline_id"] not in disciplines
                or not isinstance(topic["source"], dict)
                or set(topic["source"]) != {"source_id", "modified_time", "snapshot_sha256"}
                or topic["source"]["source_id"] not in allowed_sources):
            raise InventoryError("invalid_private_topic")
        topics[topic_id] = topic
    return {**curriculum, "disciplines": disciplines, "topics": topics}


def report(current: dict, *, previous: dict | None = None,
           processed: dict | None = None, links: list | None = None,
           registry: dict | None = None, curriculum: dict | None = None) -> dict:
    snapshot = _snapshot(current)
    if processed is not None and not isinstance(processed, dict):
        raise InventoryError("invalid_processing_records")
    if links is not None and not isinstance(links, list):
        raise InventoryError("invalid_lesson_links")
    if (registry is None) != (curriculum is None):
        raise InventoryError("reviewed_graph_inputs_required")
    reviewed = reviewed_graph(snapshot, registry, curriculum) if registry is not None else None
    states = processing_status(snapshot, processed or {})
    if registry is not None and any(states.get(source["id"]) == "excluded"
                                    for source in registry["sources"]):
        raise InventoryError("excluded_source_registered")
    lessons = link_lessons(snapshot, links or [],
                           curriculum_topics=curriculum["topics"] if curriculum is not None else None)
    changes = reconcile(_snapshot(previous), snapshot) if previous is not None else None
    by_format: dict[str, Counter] = {}
    for file_id, item in snapshot["files"].items():
        by_format.setdefault(item["mime_type"], Counter())[states[file_id]] += 1
    result = {"folders": snapshot["folders"], "files": len(snapshot["files"]),
            "processing": dict(sorted(Counter(states.values()).items())),
            "processing_by_format": {mime: dict(sorted(counts.items()))
                                     for mime, counts in sorted(by_format.items())},
            "linked_lessons": len(lessons),
            "changes": ({kind: len(ids) for kind, ids in changes.items()} if changes else None)}
    if reviewed is not None:
        result["reviewed_graph"] = reviewed
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate private recursive source metadata without exposing file IDs")
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--processed", type=Path)
    parser.add_argument("--links", type=Path)
    parser.add_argument("--reviewed", action="store_true",
                        help="compare live metadata to repository source and curriculum reviews")
    parser.add_argument("--private-registry", type=Path,
                        help="additional reviewed sources in ignored data/; requires --reviewed")
    parser.add_argument("--private-topics", type=Path,
                        help="unreleased lesson topics in ignored data/; requires --private-registry")
    parser.add_argument("--require-current-reviewed", action="store_true",
                        help="stop if a reviewed source is changed, relocated or missing; requires --reviewed")
    parser.add_argument("--private-queue", type=Path,
                        help="write a new per-file review queue only in ignored data/; requires --reviewed")
    args = parser.parse_args(argv)
    try:
        if args.private_queue and not args.reviewed:
            raise InventoryError("private_queue_requires_reviewed")
        if args.private_registry and not args.reviewed:
            raise InventoryError("private_registry_requires_reviewed")
        if args.private_topics and not args.private_registry:
            raise InventoryError("private_topics_requires_private_registry")
        if args.require_current_reviewed and not args.reviewed:
            raise InventoryError("current_review_gate_requires_reviewed")
        current = _read(args.current)
        previous = _read(args.previous) if args.previous else None
        processed = _read(args.processed) if args.processed else None
        links = _read(args.links) if args.links else None
        registry = _read(REPO_ROOT / "content/source-corpus.json") if args.reviewed else None
        public_source_count = len(registry["sources"]) if registry is not None else 0
        private_source_count = 0
        private_registry = None
        if args.private_registry:
            private_registry = private_registry_input(args.private_registry, REPO_ROOT)
            private_source_count = len(private_registry["sources"])
            registry = combine_registries(registry, private_registry)
        curriculum = _read(REPO_ROOT / "content/curriculum.json") if args.reviewed else None
        public_topic_count = len(curriculum["topics"]) if curriculum is not None else 0
        if args.private_topics:
            curriculum = combine_private_topics(
                curriculum, private_topics_input(args.private_topics, REPO_ROOT),
                private_registry)
        reviews = _read(REPO_ROOT / "content/publication-reviews.json") if args.private_queue else None
        quality_reviews = _read(REPO_ROOT / "content/learning-quality-reviews.json") if args.private_queue else None
        legacy, unmapped_legacy = legacy_derivative_links(
            REPO_ROOT, _read(REPO_ROOT / "content/legacy-publication-baseline.json"),
            quality_reviews["items"]) if args.private_queue else ({}, [])
        value = report(current, previous=previous, processed=processed, links=links,
                       registry=registry, curriculum=curriculum)
        if args.private_registry:
            graph = value["reviewed_graph"]
            graph["registered_sources"] = graph["tracked_sources"]
            graph["tracked_sources"] = public_source_count
            graph["private_reviewed_sources"] = private_source_count
        if args.private_topics:
            graph = value["reviewed_graph"]
            graph["registered_lesson_edges"] = graph["reviewed_lesson_edges"]
            graph["reviewed_lesson_edges"] = public_topic_count
            graph["private_reviewed_topics"] = len(curriculum["topics"]) - public_topic_count
        if args.require_current_reviewed and any(
                state != "current" and count
                for state, count in value["reviewed_graph"]["source_metadata"].items()):
            raise InventoryError("reviewed_source_revision_not_current")
        if args.private_queue:
            target = private_json_target(args.private_queue, REPO_ROOT)
            queue = private_review_queue(_snapshot(current), registry, curriculum,
                                         processed=processed,
                                         previous=_snapshot(previous) if previous is not None else None,
                                         reviews=reviews, quality_reviews=quality_reviews,
                                         links=links, legacy_derivatives=legacy,
                                         unmapped_legacy_derivatives=unmapped_legacy)
            value["legacy_derivatives"] = {"linked": len(legacy),
                                           "unmapped": len(unmapped_legacy)}
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
