"""Owner-only aggregate view; no source locators or learner rows are returned."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from app.glossary import load_glossary_entries
from app.curriculum import load_catalog
from app.literature import load_literature_items, load_topic_registry

ROOT = Path(__file__).resolve().parents[1]


def _coverage(raw):
    if not isinstance(raw, dict):
        raise ValueError("invalid_coverage")
    for key in ("tracked_sources", "untracked_files", "unmapped_published_questions"):
        if type(raw.get(key)) is not int or raw[key] < 0:
            raise ValueError("invalid_coverage")
    metadata = raw.get("source_metadata")
    if (not isinstance(metadata, dict) or set(metadata) - {"current", "changed", "relocated", "missing"}
            or any(type(value) is not int or value < 0 for value in metadata.values())
            or sum(metadata.values()) != raw["tracked_sources"]):
        raise ValueError("invalid_coverage")
    catalog = load_catalog()
    supplied = raw.get("lessons")
    if not isinstance(supplied, list) or len(supplied) > len(catalog["topics"]):
        raise ValueError("invalid_coverage")
    lessons, seen = [], set()
    for item in supplied:
        if not isinstance(item, dict):
            raise ValueError("invalid_coverage")
        key = item.get("id")
        if key not in catalog["topics"] or key in seen:
            raise ValueError("invalid_coverage")
        seen.add(key)
        kinds = item.get("kinds")
        if (not isinstance(kinds, dict) or set(kinds) != {"theory", "glossary", "case"}
                or any(type(value) is not int or value < 0 for value in kinds.values())
                or type(item.get("source_metadata_current")) is not bool
                or type(item.get("known_hold")) is not bool
                or item.get("processing_state") not in {"processed", "pending_review", "conflict_review", "new_unprocessed", "changed_unprocessed", "excluded", "missing"}):
            raise ValueError("invalid_coverage")
        topic = catalog["topics"][key]
        lessons.append({"id": key, "title": topic["title"],
                        "discipline": catalog["disciplines"][topic["discipline_id"]]["title"],
                        "kinds": kinds, "source_metadata_current": item["source_metadata_current"],
                        "processing_state": item["processing_state"], "known_hold": item["known_hold"],
                        "glossary_terms": None, "notes": None, "notes_state": "UNSET"})
    return {key: raw[key] for key in ("tracked_sources", "untracked_files", "source_metadata", "unmapped_published_questions")} | {"lessons": lessons}


def source_summary():
    path = Path(os.environ.get("OWNER_SOURCE_SUMMARY_PATH", "/data/owner-source-summary.json"))
    try:
        if not path.exists():
            return {"state": "UNSET", "reason": "source_snapshot_not_installed"}
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 100_000:
            raise ValueError("invalid_snapshot")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if (raw.get("schema_version") != 1 or raw.get("state") != "PARTIAL"
                or not isinstance(raw.get("captured_at"), str)):
            raise ValueError("invalid_snapshot")
        stamp = datetime.fromisoformat(raw["captured_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp > datetime.now(timezone.utc):
            raise ValueError("invalid_snapshot")
        for key in ("files", "folders", "processing_records", "known_holds"):
            if type(raw.get(key)) is not int or raw[key] < 0:
                raise ValueError("invalid_snapshot")
        allowed = {"processed", "pending_review", "conflict_review", "excluded", "new_unprocessed", "changed_unprocessed", "unreadable"}
        processing = raw.get("processing")
        if (not isinstance(processing, dict) or set(processing) - allowed
                or any(type(value) is not int or value < 0 for value in processing.values())
                or sum(processing.values()) != raw["files"]
                or raw["processing_records"] > raw["files"] or raw["known_holds"] > raw["processing_records"]):
            raise ValueError("invalid_snapshot")
        # Return an explicit allowlist, never arbitrary JSON supplied by an operator.
        result = {key: raw[key] for key in ("state", "captured_at", "files", "folders", "processing", "processing_records", "known_holds")}
        if "coverage" in raw:
            result["coverage"] = _coverage(raw["coverage"])
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        return {"state": "UNSET", "reason": "source_snapshot_invalid"}


def dashboard(conn):
    registry = load_topic_registry()
    counts = {}
    for row in conn.execute("""SELECT c.slug,q.kind,COUNT(*) FROM questions q
                              JOIN categories c ON c.id=q.category_id
                              WHERE q.status='approved' GROUP BY c.slug,q.kind"""):
        counts.setdefault(row[0], {})[row[1]] = row[2]
    literature = {}
    for item in load_literature_items():
        literature.setdefault(item["topic_id"], set()).add(item["work_id"])
    topics = []
    for key, topic in sorted(registry.items(), key=lambda pair: pair[1]["order"]):
        questions = counts.pop(key, {})
        glossary = load_glossary_entries(key)
        kinds = {kind: questions.get(kind, 0) for kind in ("theory", "glossary", "case")}
        topics.append({"id": key, "title": topic["title"], "module": topic["module"],
                       "questions": sum(kinds.values()), "kinds": kinds,
                       "glossary_terms": len(glossary) if glossary is not None else None,
                       "literature_works": len(literature.get(key, set())),
                       "notes_state": "UNSET", "notes": None,
                       "gaps": [kind for kind, count in kinds.items() if count == 0]})
    return {"ok": True, "topics": topics, "sources": source_summary(),
            "unmapped_questions": sum(sum(kinds.values()) for kinds in counts.values())}
