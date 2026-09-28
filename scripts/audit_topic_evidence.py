"""Report source support for current curriculum question editions.

This is a coverage triage, not a publication approval or a claim that an
entire source was reviewed. It prints no Drive IDs or source text.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.content_publication import DRIVE_REF, fingerprint, load_policy
from app.source_inventory import processing_status, unresolved_related_conflicts
from scripts.sign_private_publication import private_path
from scripts.source_inventory_report import _snapshot


def coverage(curriculum: dict, quality: dict, approved_questions: dict[str, str],
             source_states: dict[str, str] | None = None,
             source_registry: dict | None = None,
             certified_questions: dict[str, dict] | None = None) -> dict:
    topics = curriculum["topics"]
    items = quality["items"]
    result = {topic_id: {"title": topic["title"], "supported": 0, "signed_private": 0,
                         "partial": 0, "disputed": 0, "stale": 0,
                         "unverified_source": 0}
              for topic_id, topic in topics.items()}
    if source_states is not None:
        for topic_id, topic in topics.items():
            source_id = topic.get("source", {}).get("source_id")
            result[topic_id]["source_review_state"] = source_states.get(source_id, "missing_from_inventory")
    unmapped = 0
    mapped_ids = set()
    for edition in curriculum["editions"].values():
        if edition["external_id"] not in approved_questions:
            continue
        mapped_ids.add(edition["external_id"])
        topic_id = edition["topic_id"]
        if topic_id not in result:
            unmapped += 1
            continue
        if (question_id := edition["external_id"]) in (certified_questions or {}):
            source = topics[topic_id].get("source", {})
            certified_source = certified_questions[question_id]
            registered = next((item for item in (source_registry or {}).get("sources", [])
                               if item["id"] == source.get("source_id")), None)
            if (edition.get("item_sha256") == approved_questions[question_id]
                    and edition.get("locator") == f"private certificate:questions:{question_id}"
                    and registered is not None
                    and all(source.get(key) == certified_source.get(key)
                            for key in ("source_id", "modified_time", "snapshot_sha256"))
                    and (source_states is None or source_states.get(source.get("source_id"))
                         in {"processed", "conflict_review"})
                    and all(source.get(key) == registered.get(key)
                            for key in ("modified_time", "snapshot_sha256"))):
                result[topic_id]["signed_private"] += 1
                continue
            result[topic_id]["stale"] += 1
            continue
        review = items.get(f"questions:{edition['external_id']}")
        if (not isinstance(review, dict)
                or review.get("item_sha256") != edition.get("item_sha256")
                or edition.get("item_sha256") != approved_questions[edition["external_id"]]):
            result[topic_id]["stale"] += 1
            continue
        support = review.get("source_support")
        if support == "supported":
            source = topics[topic_id].get("source")
            references = review.get("sources")
            if (not isinstance(source, dict) or not source.get("source_id")
                    or not source.get("snapshot_sha256") or not isinstance(references, list)
                    or not any(
                    isinstance(item, dict)
                    and item.get("source_id") == source.get("source_id")
                    and item.get("modified_time") == source.get("modified_time")
                    and item.get("snapshot_sha256") == source.get("snapshot_sha256")
                    for item in references)):
                result[topic_id]["unverified_source"] += 1
                continue
        if support in {"supported", "partial", "disputed"}:
            result[topic_id][support] += 1
        else:
            result[topic_id]["stale"] += 1
    without_mapping = approved_questions.keys() - mapped_ids
    support_breakdown = Counter()
    scope_breakdown = Counter()
    sources = ({item["id"]: item for item in source_registry["sources"]}
               if source_registry is not None else {})
    for question_id in without_mapping:
        review = items.get(f"questions:{question_id}")
        if isinstance(review, dict) and review.get("item_sha256") != approved_questions[question_id]:
            support_breakdown["stale"] += 1
        else:
            support = review.get("source_support") if isinstance(review, dict) else None
            support_breakdown[support if support in {"supported", "partial", "disputed"}
                              else "unreviewed"] += 1
            if source_registry is not None and support == "supported":
                references = review.get("sources")
                discipline_only = (isinstance(references, list) and bool(references)
                    and all(isinstance(ref, dict)
                        and (source := sources.get(ref.get("source_id"))) is not None
                        and source.get("discipline_id") in curriculum.get("disciplines", {})
                        and all(ref.get(key) == source.get(key)
                                for key in ("modified_time", "snapshot_sha256"))
                        for ref in references))
                scope_breakdown["current_discipline_source_only" if discipline_only
                                else "other_supported_source"] += 1
    report = {"topics": result, "unknown_topic_editions": unmapped,
            "approved_questions_without_curriculum_edition": len(without_mapping),
            "unmapped_questions_by_source_support": dict(sorted(support_breakdown.items())),
            "topics_without_supported_question": sorted(
                topic_id for topic_id, counts in result.items()
                if counts["supported"] + counts["signed_private"] == 0)}
    if source_registry is not None:
        report["unmapped_supported_source_scope"] = dict(sorted(scope_breakdown.items()))
    return report


def approved_questions(root: Path) -> dict[str, str]:
    topics = json.loads((root / "content/topics.json").read_text(encoding="utf-8"))
    approved = {}
    for topic in topics:
        if topic.get("status") != "active" or "questions" not in topic.get("available_contours", []):
            continue
        for question in json.loads((root / topic["question_file"]).read_text(encoding="utf-8")):
            if question.get("status") == "approved":
                approved[question["id"]] = fingerprint(question)
    return approved


def certified_questions(root: Path, dossier_paths: list[Path]) -> dict[str, dict]:
    """Use exact ignored review dossiers; a public signature alone has no source ID."""
    policy = load_policy()
    certified = {}
    items = {}
    for path in (root / "content/questions").glob("**/*.json"):
        for question in json.loads(path.read_text(encoding="utf-8")):
            items[question["id"]] = question
    for raw_path in dossier_paths:
        dossier = json.loads(private_path(raw_path, suffix=".json").read_text(encoding="utf-8"))
        if (dossier.get("kind") != "questions" or not isinstance(dossier.get("item_id"), str)
                or dossier["item_id"] in certified):
            raise ValueError("invalid_signed_curriculum_dossier")
        item_id = dossier["item_id"]
        certificate = (policy.certificates or {}).get(f"questions:{item_id}")
        sources = dossier.get("sources")
        if (not isinstance(certificate, dict) or certificate.get("review_sha256") != fingerprint(dossier)
                or not isinstance(sources, list) or len(sources) != 1
                or not isinstance(sources[0], dict)
                or not isinstance(dossier.get("source_ref"), str)
                or (ref := DRIVE_REF.fullmatch(dossier["source_ref"])) is None
                or ref[1] != sources[0].get("id")
                or item_id not in items or not policy.can_publish("questions", items[item_id])):
            raise ValueError("invalid_signed_curriculum_dossier")
        certified[item_id] = {"source_id": sources[0]["id"],
                              "modified_time": sources[0].get("modified_time"),
                              "snapshot_sha256": sources[0].get("snapshot_sha256")}
    return certified


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curriculum", type=Path, default=ROOT / "content/curriculum.json")
    parser.add_argument("--quality", type=Path, default=ROOT / "content/learning-quality-reviews.json")
    parser.add_argument("--inventory", type=Path,
                        help="private current Drive inventory; use together with --processed")
    parser.add_argument("--processed", type=Path,
                        help="private source review snapshot; use together with --inventory")
    parser.add_argument("--signed-dossier", type=Path, action="append", default=[],
                        help="ignored signed private review dossier for an exact question edition")
    args = parser.parse_args()
    if (args.inventory is None) != (args.processed is None):
        parser.error("--inventory and --processed must be supplied together")
    curriculum = json.loads(args.curriculum.read_text(encoding="utf-8"))
    quality = json.loads(args.quality.read_text(encoding="utf-8"))
    source_states = None
    if args.inventory is not None:
        inventory = _snapshot(json.loads(args.inventory.read_text(encoding="utf-8")))
        processed = json.loads(args.processed.read_text(encoding="utf-8"))
        source_states = processing_status(inventory, processed)
        for source_id in unresolved_related_conflicts(processed):
            if source_states.get(source_id) == "processed":
                source_states[source_id] = "related_conflict_review"
    registry = json.loads((ROOT / "content/source-corpus.json").read_text(encoding="utf-8"))
    print(json.dumps(coverage(curriculum, quality, approved_questions(ROOT), source_states,
                              registry, certified_questions(ROOT, args.signed_dossier)),
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
