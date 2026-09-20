#!/usr/bin/env python3
"""Check the review ledger's identity/evidence, not the truth of its judgments.

This is an audit record, deliberately separate from publication approval. A
partial/disputed result never grants permission to publish changed content.
"""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.content_publication import SHA256, fingerprint


def inventory(root=ROOT):
    items = {}
    for kind, pattern in (("questions", "**/*.json"), ("glossary", "*.json")):
        for path in sorted((root / "content" / kind).glob(pattern)):
            for item in json.loads(path.read_text(encoding="utf-8")):
                key = f"{kind}:{item['id']}"
                if key in items:
                    raise ValueError(f"Duplicate learning identity: {key}")
                items[key] = item
    return items


def validate(ledger, items, sources):
    errors = []
    if not isinstance(ledger, dict) or ledger.get("schema_version") != 1 or not isinstance(ledger.get("items"), dict):
        return ["Invalid learning review schema"]
    reviews = ledger["items"]
    for key in sorted(items.keys() - reviews.keys()):
        errors.append(f"{key}: missing review")
    for key in sorted(reviews.keys() - items.keys()):
        errors.append(f"{key}: orphan review")
    for key in sorted(items.keys() & reviews.keys()):
        r = reviews[key]
        if not isinstance(r, dict):
            errors.append(f"{key}: invalid review")
            continue
        if r.get("item_sha256") != fingerprint(items[key]):
            errors.append(f"{key}: stale item review")
        try:
            valid_date = date.fromisoformat(r.get("reviewed_at", "")).isoformat() == r["reviewed_at"]
        except (ValueError, TypeError, KeyError):
            valid_date = False
        if not valid_date or not isinstance(r.get("reviewer"), str) or not r["reviewer"].strip():
            errors.append(f"{key}: reviewer/date required")
        if r.get("source_support") not in {"supported", "partial", "unconfirmed", "disputed"}:
            errors.append(f"{key}: invalid source support")
        if r.get("meaning") not in {"consistent", "ambiguous", "incorrect", "unconfirmed"}:
            errors.append(f"{key}: invalid meaning review")
        if not isinstance(r.get("note"), str) or not r["note"].strip():
            errors.append(f"{key}: substantive review note required")
        required = {"meaning", "answer", "explanation", "ambiguity", "duplicates", "sources"}
        if key.startswith("glossary:"):
            required = {"meaning", "definition", "examples", "ambiguity", "duplicates", "sources"}
        checks = r.get("checks")
        if (not isinstance(checks, list) or any(not isinstance(x, str) for x in checks)
                or len(checks) != len(required) or set(checks) != required):
            errors.append(f"{key}: incomplete review aspects")
        if not isinstance(r.get("issues"), list) or any(not isinstance(x, str) or not x.strip() for x in r["issues"]):
            errors.append(f"{key}: invalid issues")
        evidence = r.get("sources")
        if not isinstance(evidence, list):
            errors.append(f"{key}: source evidence list required")
            continue
        if r.get("source_support") == "supported" and not evidence:
            errors.append(f"{key}: supported requires primary evidence")
        if r.get("source_support") != "supported" and not r.get("issues"):
            errors.append(f"{key}: uncertainty requires explicit issue")
        if r.get("meaning") != "consistent" and not r.get("issues"):
            errors.append(f"{key}: semantic concern requires explicit issue")
        seen = set()
        for e in evidence:
            if not isinstance(e, dict):
                errors.append(f"{key}: invalid source evidence")
                continue
            source_id = e.get("source_id")
            if not isinstance(source_id, str) or source_id in seen:
                errors.append(f"{key}: invalid/duplicate source identity")
                continue
            seen.add(source_id)
            source = sources.get(source_id)
            if not source or source.get("kind") != "learning_material" or source.get("readable") is not True:
                errors.append(f"{key}: readable primary learning source required")
                continue
            if (not isinstance(e.get("snapshot_sha256"), str)
                    or SHA256.fullmatch(e["snapshot_sha256"]) is None
                    or not isinstance(e.get("modified_time"), str) or not e["modified_time"].strip()):
                errors.append(f"{key}: source revision/fingerprint required")
            if any(e.get(field) != source.get(field) for field in ("modified_time", "snapshot_sha256")):
                errors.append(f"{key}: stale source review")
            if not isinstance(e.get("locator"), str) or not e["locator"].strip():
                errors.append(f"{key}: source locator required")
    return errors


def main():
    try:
        ledger = json.loads((ROOT / "content/learning-quality-reviews.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "content/source-corpus.json").read_text(encoding="utf-8"))
        errors = validate(ledger, inventory(), {s["id"]: s for s in registry["sources"]})
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Learning review unavailable: {type(error).__name__}")
        return 1
    for error in errors:
        print(error)
    if errors:
        return 1
    print(f"Learning review ledger valid: {len(ledger['items'])} items; semantic truth requires source review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
