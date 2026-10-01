"""Private, revision-bound bibliography candidates from any extracted source.

Discovery locates mentions, never approves a work identity or publication. Source
texts, offsets and Drive identifiers stay in the private operator queue. Existing
catalogue and personal reading rows are not modified by ingestion.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from app.source_inventory import InventoryError, _revision

READING_QUOTE = re.compile(
    r'(?:книг[а-я]*|учебник[а-я]*|пособи[а-я]*|монографи[а-я]*|прочита[а-я]*|литератур[а-я]*)'
    r'[^\n]{0,120}?[«“"](?P<title>[^»”"\n]{3,200})[»”"]', re.IGNORECASE)


def _title_pattern(title: str):
    # Keep offsets in the exact captured text; do not normalize the source.
    parts = re.split(r"\s+", title.strip())
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(part) for part in parts)
                      + r"(?!\w)", re.IGNORECASE)


def discover_bibliography(snapshot: dict, captures: list[dict], catalogue: list[dict]) -> dict:
    """Return review candidates and explicit unread coverage, never a clean bill."""
    by_title = defaultdict(set)
    for entry in catalogue:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) and entry[k].strip()
                                                 for k in ("title", "id", "work_id")):
            raise InventoryError("invalid_bibliography_catalogue")
        by_title[entry["title"]].add(entry["work_id"])
    known = [(_title_pattern(title), sorted(ids)) for title, ids in by_title.items()]
    seen, mentions = set(), []
    for capture in captures:
        if not isinstance(capture, dict):
            raise InventoryError("invalid_bibliography_capture")
        source_id = capture.get("source_id")
        source = snapshot["files"].get(source_id)
        raw = capture.get("content")
        if (source is None or source_id in seen or not isinstance(raw, bytes)
                or tuple(capture.get("revision", ())) != _revision(source)
                or hashlib.sha256(raw).hexdigest() != capture.get("snapshot_sha256")):
            raise InventoryError("stale_or_invalid_bibliography_capture")
        try:
            text = raw.decode("utf-8")
        except UnicodeError as error:
            raise InventoryError("bibliography_extracted_utf8_required") from error
        if not text.lstrip("\ufeff").strip():
            raise InventoryError("bibliography_empty_capture_not_read")
        seen.add(source_id)
        found = {}
        for pattern, work_ids in known:
            for match in pattern.finditer(text):
                found[match.span()] = (match.group(), work_ids)
        for match in READING_QUOTE.finditer(text):
            bounds = match.span("title")
            if not any(start <= bounds[0] and bounds[1] <= end for start, end in found):
                found[bounds] = (match.group("title"), [])
        for (start, end), (title, work_ids) in sorted(found.items()):
            mentions.append({
                "source_id": source_id, "revision": list(_revision(source)),
                "snapshot_sha256": capture["snapshot_sha256"],
                "paths": snapshot["paths"][source_id],
                "locator": f"characters:{start}:{end}", "title_candidate": title,
                "excerpt": text[max(0, start - 150):min(len(text), end + 150)],
                "candidate_work_ids": work_ids, "decision": "pending_review",
            })
    return {"schema_version": 1, "captured_sources": len(seen),
            "unread_source_ids": sorted(set(snapshot["files"]) - seen),
            "mentions": mentions, "publication_approval": False}
