#!/usr/bin/env python3
"""Shortlist private source passages for human claim review; never approve content.

Input and output must be ignored files directly under data/. The pinned local
embedding model is used offline. Scores locate passages, not establish truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
MAX_SOURCE_BYTES = 2_000_000
MAX_CLAIMS = 200

from app.content_publication import fingerprint
from app.source_inventory import InventoryError
from scripts.source_batch_capture import _private_content_path
from scripts.source_claim_candidates import _claim, _derivatives
from scripts.source_inventory_report import private_json_target


def shortlist(text: str, claims: dict, items: dict, model, *,
              window: int = 240, stride: int = 160, limit: int = 5) -> dict:
    if window < 80 or stride < 1 or stride > window or limit < 1:
        raise ValueError("invalid_candidate_window")
    windows = [(start, min(start + window, len(text)))
               for start in range(0, len(text), stride)
               if min(start + window, len(text)) - start >= 60]
    if not windows:
        raise ValueError("empty_source_text")
    keys = [key for key in sorted(claims)
            if key in items and items[key].get("status") == "approved"]
    if not keys:
        raise ValueError("no_current_approved_claims")
    if len(keys) > MAX_CLAIMS or len(windows) > 20_000:
        raise ValueError("candidate_batch_too_large")

    vectors = np.asarray(list(model.embed([text[a:b] for a, b in windows],
                                          batch_size=64)), dtype=np.float32)
    queries = np.asarray(list(model.embed([_claim(key, items[key])[:500]
                                           for key in keys], batch_size=32)), dtype=np.float32)
    if (vectors.shape[0] != len(windows) or queries.shape[0] != len(keys)
            or vectors.ndim != 2 or queries.ndim != 2
            or vectors.shape[1] != queries.shape[1]
            or not np.isfinite(vectors).all() or not np.isfinite(queries).all()):
        raise ValueError("invalid_candidate_embeddings")
    for values in (vectors, queries):
        norms = np.linalg.norm(values, axis=1, keepdims=True)
        if np.any(norms <= 0):
            raise ValueError("zero_candidate_embedding")
        values /= norms

    result = {}
    for key, query in zip(keys, queries):
        scores = vectors @ query
        selected = []
        for index in np.argsort(scores)[::-1]:
            start, end = windows[int(index)]
            if any(start < previous_end and previous_start < end
                   for previous_start, previous_end, _ in selected):
                continue
            selected.append([start, end, round(float(scores[index]), 4)])
            if len(selected) == limit:
                break
        result[key] = {"item_sha256": fingerprint(items[key]),
                       "candidate_ranges": selected}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True,
                        help="private lexical claim-candidate JSON")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        candidate_path = private_json_target(args.candidates, ROOT)
        target = private_json_target(args.output, ROOT)
        if target.exists() or target.is_symlink():
            raise InventoryError("candidate_output_exists")
        manifest = json.loads(candidate_path.read_text(encoding="utf-8"))
        sources = [source for source in manifest.get("sources", [])
                   if source.get("source_id") == args.source_id]
        if len(sources) != 1 or not isinstance(sources[0].get("claims"), dict):
            raise InventoryError("candidate_source_not_unique")
        source = sources[0]
        content_path = _private_content_path(source.get("content"))
        if content_path.is_symlink() or not content_path.is_file():
            raise InventoryError("candidate_source_not_regular")
        source_bytes = content_path.read_bytes()
        if len(source_bytes) > MAX_SOURCE_BYTES:
            raise InventoryError("candidate_source_too_large")
        digest = hashlib.sha256(source_bytes).hexdigest()
        if digest != source.get("snapshot_sha256"):
            raise InventoryError("candidate_source_revision_changed")
        content = source_bytes.decode("utf-8")
        cache_setting = os.environ.get("SEARCH_MODEL_CACHE")
        if not cache_setting or not Path(cache_setting).is_dir():
            raise InventoryError("local_embedding_cache_required")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        from app.private_search import MODEL_IDENTITY, embedder
        items = _derivatives(ROOT)
        result = shortlist(content, source["claims"], items, embedder())
        payload = {"schema_version": 1,
                   "purpose": "private_semantic_candidates_not_approval",
                   "source_sha256": digest,
                   "model": MODEL_IDENTITY,
                   "items": result}
        with target.open("x", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False, indent=2)
            output.write("\n")
        print(f"PRIVATE_SEMANTIC_CANDIDATES_READY claims={len(result)}")
        return 0
    except (InventoryError, ValueError, OSError, UnicodeError, KeyError, TypeError) as error:
        print(f"PRIVATE_SEMANTIC_CANDIDATES_STOP: {type(error).__name__}",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
