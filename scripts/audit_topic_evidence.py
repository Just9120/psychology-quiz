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

from app.content_publication import fingerprint
from app.source_inventory import processing_status, unresolved_related_conflicts
from scripts.source_inventory_report import _snapshot


def coverage(curriculum: dict, quality: dict, approved_questions: dict[str, str],
             source_states: dict[str, str] | None = None) -> dict:
    topics = curriculum["topics"]
    items = quality["items"]
    result = {topic_id: {"title": topic["title"], "supported": 0,
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
    for question_id in without_mapping:
        review = items.get(f"questions:{question_id}")
        if isinstance(review, dict) and review.get("item_sha256") != approved_questions[question_id]:
            support_breakdown["stale"] += 1
        else:
            support = review.get("source_support") if isinstance(review, dict) else None
            support_breakdown[support if support in {"supported", "partial", "disputed"}
                              else "unreviewed"] += 1
    return {"topics": result, "unknown_topic_editions": unmapped,
            "approved_questions_without_curriculum_edition": len(without_mapping),
            "unmapped_questions_by_source_support": dict(sorted(support_breakdown.items())),
            "topics_without_supported_question": sorted(
                topic_id for topic_id, counts in result.items() if counts["supported"] == 0)}


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curriculum", type=Path, default=ROOT / "content/curriculum.json")
    parser.add_argument("--quality", type=Path, default=ROOT / "content/learning-quality-reviews.json")
    parser.add_argument("--inventory", type=Path,
                        help="private current Drive inventory; use together with --processed")
    parser.add_argument("--processed", type=Path,
                        help="private source review snapshot; use together with --inventory")
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
    print(json.dumps(coverage(curriculum, quality, approved_questions(ROOT), source_states),
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
