"""Build a private shortlist of source passages for manual derivative review.

Lexical overlap only locates candidates. It never certifies a claim or changes
publication state. Input text and output remain in ignored operator data/.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.content_publication import fingerprint
from app.source_inventory import InventoryError, processing_status
from scripts.source_batch_capture import _private_content_path
from scripts.source_inventory_report import _read, _snapshot, private_json_target

WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
STOP = {"какой", "какая", "какие", "почему", "после", "нужно", "может",
        "чтобы", "который", "которое", "этого", "только", "более", "менее",
        "обычно", "лучше", "прежде", "всего", "человек", "человека"}


def _tokens(value: str) -> set[str]:
    return {word for word in WORD.findall(value.casefold()) if word not in STOP}


def _passages(text: str) -> list[tuple[int, int, set[str]]]:
    passages, offset = [], 0
    for line in text.splitlines(keepends=True):
        length = len(line.rstrip("\r\n"))
        for start in range(0, length, 700):
            end = min(start + 800, length)
            words = _tokens(line[start:end])
            if words:
                passages.append((offset + start, offset + end, words))
            if end == length:
                break
        offset += len(line)
    return passages


def candidate_ranges(text: str, claim: str, limit: int = 3) -> list[list[int]]:
    """Return likely passage positions, never a support verdict."""
    passages = _passages(text)
    query = _tokens(claim)
    if not passages or not query:
        return []
    frequency = Counter(word for _, _, words in passages for word in words)
    ranked = []
    for start, end, words in passages:
        overlap = query & words
        if overlap:
            score = sum(math.log1p((len(passages) + 1) / (frequency[word] + 1))
                        for word in overlap)
            ranked.append((-score, start, end))
    return [[start, end] for _, start, end in sorted(ranked)[:limit]]


def _derivatives(root: Path) -> dict[str, dict]:
    items = {}
    for kind, pattern in (("questions", "**/*.json"), ("glossary", "*.json")):
        for path in sorted((root / "content" / kind).glob(pattern)):
            for item in _read(path):
                key = f"{kind}:{item['id']}"
                if key in items:
                    raise InventoryError("duplicate_derivative")
                items[key] = item
    return items


def _claim(key: str, item: dict) -> str:
    if key.startswith("questions:"):
        answer = item["options"][item["correct_option_index"]]
        return " ".join((item["question"], answer, item["explanation"]))
    return " ".join((item["term"], item["short_definition"],
                     item["definition"], *item.get("examples", [])))


def build_queue(current: dict, processed: dict, manifest: dict, reviews: dict,
                derivatives: dict) -> dict:
    snapshot = _snapshot(current)
    states = processing_status(snapshot, processed)
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or not isinstance(manifest.get("sources"), list)):
        raise InventoryError("invalid_batch_manifest")
    if not isinstance(reviews, dict):
        raise InventoryError("invalid_quality_reviews")
    result, seen = [], set()
    for entry in manifest["sources"]:
        if (not isinstance(entry, dict) or set(entry) != {"source_id", "content", "snapshot_kind"}
                or not isinstance(entry["source_id"], str)
                or entry["source_id"] in seen or entry["snapshot_kind"] != "extracted_text"):
            raise InventoryError("invalid_candidate_source")
        source_id = entry["source_id"]
        seen.add(source_id)
        source = snapshot["files"].get(source_id)
        record = processed.get(source_id)
        if (source is None or states[source_id] not in {"pending_review", "processed"}
                or not isinstance(record, dict)):
            raise InventoryError("candidate_source_not_current")
        path = _private_content_path(entry["content"])
        raw = path.read_bytes()
        if (not raw or record.get("snapshot_kind") != "extracted_text"
                or hashlib.sha256(raw).hexdigest() != record.get("snapshot_sha256")):
            raise InventoryError("candidate_content_digest_mismatch")
        text = raw.decode("utf-8")
        claims = {}
        for key, review in reviews.items():
            if not isinstance(review, dict):
                continue
            if not any(isinstance(ref, dict) and ref.get("source_id") == source_id
                       for ref in review.get("sources", [])):
                continue
            item = derivatives.get(key)
            if item is None or review.get("item_sha256") != fingerprint(item):
                claims[key] = {"state": "stale_or_missing_derivative", "candidate_ranges": []}
                continue
            claims[key] = {"state": "needs_claim_review",
                           "candidate_ranges": candidate_ranges(text, _claim(key, item))}
        result.append({"source_id": source_id, "revision": record["revision"],
                       "snapshot_sha256": record["snapshot_sha256"],
                       "content": entry["content"], "claims": claims})
    return {"schema_version": 1, "purpose": "private_candidates_not_approval",
            "sources": result}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Private lexical candidates for claim review")
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--processed", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        manifest_path = private_json_target(args.manifest, REPO_ROOT)
        target = private_json_target(args.output, REPO_ROOT)
        reviews = _read(REPO_ROOT / "content/learning-quality-reviews.json")["items"]
        queue = build_queue(_read(args.current), _read(args.processed),
                            _read(manifest_path), reviews, _derivatives(REPO_ROOT))
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(queue, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (InventoryError, OSError, UnicodeError, json.JSONDecodeError,
            TypeError, KeyError, IndexError) as error:
        print("SOURCE_CANDIDATES_STOP: " +
              (str(error) if isinstance(error, InventoryError) else type(error).__name__),
              file=sys.stderr)
        return 1
    print("SOURCE_CANDIDATES_PRIVATE_READY sources=" + str(len(queue["sources"])) +
          " claims=" + str(sum(len(source["claims"]) for source in queue["sources"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
