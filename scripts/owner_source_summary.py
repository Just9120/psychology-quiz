"""Create source-free owner aggregates from a complete private inventory."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.source_inventory import InventoryError, reviewed_graph, processing_status
from app.content_publication import fingerprint, load_policy
from app.curriculum import load_catalog
from scripts.source_inventory_report import _read, _snapshot, report, private_json_target


def lesson_coverage(current, processed, registry, curriculum, published_items):
    """Only an exact current question edition acquires its reviewed lesson."""
    snapshot = _snapshot(current)
    graph = reviewed_graph(snapshot, registry, curriculum)
    states = processing_status(snapshot, processed)
    registered = {item["id"]: item for item in registry["sources"]}
    editions = {}
    for edition in curriculum["editions"].values():
        key = (edition["external_id"], edition["item_sha256"])
        previous = editions.get(key)
        if previous is not None and previous != edition["topic_id"]:
            raise InventoryError("ambiguous_derivative_lesson")
        editions[key] = edition["topic_id"]
    counts = {key: {kind: 0 for kind in ("theory", "glossary", "case")} for key in curriculum["topics"]}
    seen = set()
    unmapped = 0
    for item in published_items:
        if item["id"] in seen:
            raise InventoryError("duplicate_derivative")
        seen.add(item["id"])
        topic_id = editions.get((item["id"], fingerprint(item)))
        if topic_id is None:
            unmapped += 1
            continue
        kind = item.get("kind", "theory")
        if kind not in counts[topic_id]:
            raise InventoryError("unknown_derivative_kind")
        counts[topic_id][kind] += 1
    lessons = []
    for key, topic in curriculum["topics"].items():
        source_id = topic["source"]["source_id"]
        source, live = registered[source_id], snapshot["files"].get(source_id)
        current_metadata = live is not None and source["title"] == live["title"] and source["modified_time"] == live["modified_time"]
        processing = states.get(source_id, "missing")
        hold = source_id in processed and (processed[source_id].get("review_state") == "conflict" or bool(processed[source_id].get("conflict_hold")))
        lessons.append({"id": key, "title": topic["title"], "discipline_id": topic["discipline_id"],
                        "source_metadata_current": current_metadata, "processing_state": processing,
                        "known_hold": bool(hold), "kinds": counts[key],
                        "glossary_terms": None, "notes": None, "notes_state": "UNSET"})
    # Aggregate graph only: exclude file names, locators, paths and Drive IDs.
    return {"tracked_sources": graph["tracked_sources"],
            "untracked_files": graph["untracked_inventory_files"],
            "source_metadata": graph["source_metadata"], "lessons": lessons,
            "unmapped_published_questions": unmapped}



def prepared_note_coverage(coverage, note_manifest, current, processed, curriculum):
    # Reuse source/revision/hold/link gates; rendered texts stay operator-only.
    from scripts.obsidian_vault import render
    render(note_manifest, current, processed)
    counts = {key: 0 for key in curriculum["topics"]}
    unmapped = 0
    for note in note_manifest["notes"]:
        matched = []
        for key, topic in curriculum["topics"].items():
            source = topic["source"]
            if (note["source_id"] == source["source_id"]
                    and note["source_revision"][0] == source["modified_time"]
                    and note["source_sha256"] == source["snapshot_sha256"]):
                matched.append(key)
        if not matched:
            unmapped += 1
        for key in matched:
            counts[key] += 1
    for lesson in coverage["lessons"]:
        lesson.update(notes=counts[lesson["id"]], notes_state="PREPARED")
    coverage["prepared_notes_unmapped"] = unmapped


def published_questions():
    policy = load_policy()
    result = []
    for path in sorted((ROOT / "content/questions").glob("**/*.json")):
        items = _read(path)
        if not isinstance(items, list):
            raise InventoryError("invalid_derivative_file")
        result.extend(item for item in items if isinstance(item, dict) and item.get("status") == "approved" and policy.can_publish("questions", item))
    return result


def build(current, processed, observed_at, *, registry=None, curriculum=None, published_items=None, note_manifest=None):
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if observed.tzinfo is None or observed > datetime.now(timezone.utc):
        raise ValueError("invalid_observation_time")
    value = report(current, processed=processed)
    files = _snapshot(current)["files"]
    records = {key: record for key, record in processed.items() if key in files}
    result = {"schema_version": 1, "state": "PARTIAL",
            "captured_at": observed_at, "generated_at": datetime.now(timezone.utc).isoformat(),
            "files": value["files"], "folders": value["folders"],
            "processing": value["processing"], "processing_records": len(records),
            "known_holds": sum(record.get("review_state") == "conflict" or bool(record.get("conflict_hold"))
                               for record in records.values())}
    if any(value is not None for value in (registry, curriculum, published_items)):
        if any(value is None for value in (registry, curriculum, published_items)):
            raise InventoryError("reviewed_graph_inputs_required")
        result["coverage"] = lesson_coverage(current, processed, registry, curriculum, published_items)
        if note_manifest is not None:
            prepared_note_coverage(result["coverage"], note_manifest, current, processed, curriculum)
    elif note_manifest is not None:
        raise InventoryError("reviewed_graph_inputs_required")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--reviewed", action="store_true")
    parser.add_argument("--notes-manifest", type=Path, help="Optional ignored private preparation manifest; never Vault publication evidence")
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        target = private_json_target(args.output, ROOT)
        inputs = {"registry": _read(ROOT / "content/source-corpus.json"), "curriculum": load_catalog(),
                  "published_items": published_questions()} if args.reviewed else {}
        if args.notes_manifest is not None:
            from scripts.obsidian_vault import _private_input
            inputs["note_manifest"] = _private_input(args.notes_manifest)
        value = build(_read(args.current), _read(args.processed), args.observed_at, **inputs)
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as output:
            json.dump(value, output, indent=2)
            output.write("\n")
    except (InventoryError, OSError, ValueError, TypeError, KeyError) as error:
        print("OWNER_SUMMARY_STOP: " + (str(error) if isinstance(error, InventoryError) else type(error).__name__))
        return 1
    print("OWNER_SOURCE_SUMMARY_CREATED; counts only, supplied review snapshot remains partial")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
