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
from app.source_inventory import InventoryError, reviewed_graph, processing_status, combine_registries
from app.content_publication import fingerprint, load_policy
from app.curriculum import load_reviewed_catalog
from scripts.source_inventory_report import _read, _snapshot, report, private_json_target, private_registry_input, private_topics_input, combine_private_topics


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
        # Additional navigation labels have no reviewed source lesson in this
        # graph. An exact edition alone must not invent that source binding.
        if topic_id not in counts:
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



def glossary_coverage(coverage, published_glossary, policy, curriculum):
    """Count only current reviewed term editions against exact lesson sources."""
    lessons = {item["id"]: item for item in coverage["lessons"]}
    counts = {key: 0 for key in lessons}
    unmapped, seen = 0, set()
    for item in published_glossary:
        if item["id"] in seen:
            raise InventoryError("duplicate_glossary_derivative")
        seen.add(item["id"])
        if item.get("status") != "approved" or not policy.can_publish("glossary", item):
            raise InventoryError("published_glossary_required")
        review = (policy.quality_reviews or {}).get("glossary:" + item["id"], {})
        refs = review.get("sources", []) if (isinstance(review, dict)
                and review.get("item_sha256") == fingerprint(item)
                and review.get("source_support") == "supported"
                and isinstance(review.get("sources"), list)) else []
        matched = set()
        for key, topic in curriculum["topics"].items():
            source, lesson = topic["source"], lessons[key]
            if (not lesson["source_metadata_current"] or lesson["known_hold"]
                    or lesson["processing_state"] != "processed"):
                continue
            if any(isinstance(ref, dict)
                   and ref.get("source_id") == source["source_id"]
                   and ref.get("modified_time") == source["modified_time"]
                   and ref.get("snapshot_sha256") == source["snapshot_sha256"] for ref in refs):
                matched.add(key)
        if not matched:
            unmapped += 1
        for key in matched:
            counts[key] += 1
    for key, lesson in lessons.items():
        lesson["glossary_terms"] = counts[key]
    coverage["unmapped_published_glossary"] = unmapped


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


def published_glossary(policy):
    result = []
    for path in sorted((ROOT / "content/glossary").glob("*.json")):
        items = _read(path)
        if not isinstance(items, list):
            raise InventoryError("invalid_derivative_file")
        result.extend(item for item in items if isinstance(item, dict) and item.get("status") == "approved" and policy.can_publish("glossary", item))
    return result


def published_questions():
    policy = load_policy()
    result = []
    for path in sorted((ROOT / "content/questions").glob("**/*.json")):
        items = _read(path)
        if not isinstance(items, list):
            raise InventoryError("invalid_derivative_file")
        result.extend(item for item in items if isinstance(item, dict) and item.get("status") == "approved" and policy.can_publish("questions", item))
    return result


def build(current, processed, observed_at, *, registry=None, curriculum=None, published_items=None, note_manifest=None, glossary_items=None, glossary_policy=None, public_topic_ids=None, saved_inputs=False):
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
    if saved_inputs:
        result["observation_basis"] = "saved_inputs"
    if any(value is not None for value in (registry, curriculum, published_items)):
        if any(value is None for value in (registry, curriculum, published_items)):
            raise InventoryError("reviewed_graph_inputs_required")
        result["coverage"] = lesson_coverage(current, processed, registry, curriculum, published_items)
        if glossary_items is not None:
            if glossary_policy is None:
                raise InventoryError("glossary_policy_required")
            glossary_coverage(result["coverage"], glossary_items, glossary_policy, curriculum)
        if note_manifest is not None:
            prepared_note_coverage(result["coverage"], note_manifest, current, processed, curriculum)
        if public_topic_ids is not None:
            if not isinstance(public_topic_ids, set) or not public_topic_ids <= set(curriculum["topics"]):
                raise InventoryError("invalid_public_topics")
            public_lessons, private_lessons = [], []
            for lesson in result["coverage"]["lessons"]:
                (public_lessons if lesson["id"] in public_topic_ids else private_lessons).append(lesson)
            states = {}
            for lesson in private_lessons:
                state = lesson["processing_state"]
                states[state] = states.get(state, 0) + 1
            result["coverage"]["lessons"] = public_lessons
            # Unreleased names and source bindings never leave operator storage.
            result["coverage"]["unreleased_lessons"] = {
                "total": len(private_lessons), "processing": states,
                "metadata_current": sum(item["source_metadata_current"] for item in private_lessons),
                "known_holds": sum(item["known_hold"] for item in private_lessons),
            }
    elif note_manifest is not None or glossary_items is not None or public_topic_ids is not None:
        raise InventoryError("reviewed_graph_inputs_required")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--reviewed", action="store_true")
    parser.add_argument("--private-registry", type=Path, help="Additional reviewed source metadata in ignored data/; requires --reviewed")
    parser.add_argument("--private-topics", type=Path, help="Unreleased lesson metadata in ignored data/; requires reviewed private registry")
    parser.add_argument("--notes-manifest", type=Path, help="Optional ignored private preparation manifest; never Vault publication evidence")
    observation = parser.add_mutually_exclusive_group(required=True)
    observation.add_argument("--observed-at", help="Known inventory observation time")
    observation.add_argument("--saved-inputs", action="store_true",
                             help="Date compilation of saved inputs, without claiming fresh Drive observation")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.private_registry is not None and not args.reviewed:
            raise InventoryError("private_registry_requires_reviewed")
        if args.private_topics is not None and (not args.reviewed or args.private_registry is None):
            raise InventoryError("private_topics_requires_reviewed_registry")
        target = private_json_target(args.output, ROOT)
        inputs = {"registry": _read(ROOT / "content/source-corpus.json"), "curriculum": load_reviewed_catalog(),
                  "published_items": published_questions()} if args.reviewed else {}
        if args.private_registry is not None:
            private_registry = private_registry_input(args.private_registry, ROOT)
            inputs["registry"] = combine_registries(inputs["registry"], private_registry)
            if args.private_topics is not None:
                inputs["public_topic_ids"] = set(inputs["curriculum"]["topics"])
                inputs["curriculum"] = combine_private_topics(
                    inputs["curriculum"], private_topics_input(args.private_topics, ROOT), private_registry)
        if args.reviewed:
            policy = load_policy()
            inputs.update(glossary_items=published_glossary(policy), glossary_policy=policy)
        if args.notes_manifest is not None:
            from scripts.obsidian_vault import _private_input
            inputs["note_manifest"] = _private_input(args.notes_manifest)
        observed_at = datetime.now(timezone.utc).isoformat() if args.saved_inputs else args.observed_at
        value = build(_read(args.current), _read(args.processed), observed_at, saved_inputs=args.saved_inputs, **inputs)
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
