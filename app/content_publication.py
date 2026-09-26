"""Repository approval boundary. Source metadata never grants publication by itself."""
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from app.case_content import case_error
from app.source_evidence import locator_precision_review_required

ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT_ID = "119DpAwq3T_9JzlTRMPeB7LX7-vpeO95U"
# Frozen existing publication, not a claim of source certification. Do not extend.
LEGACY_SHA256 = "e03468c43558450105c8b3fddd30ed5db432b379e3b49f63b85b4370235dcc11"
KINDS = {"questions", "glossary", "literature"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
DRIVE_REF = re.compile(r"^drive:([A-Za-z0-9_-]+)(?:#.+)?$")
PUBLIC_DRIVE_LINK = re.compile(r"(?i)(?:drive:|https?://(?:www\.)?(?:drive|docs)\.google\.com/)")


def fingerprint(item):
    return hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _date(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _public_text_contains_private_source(kind, item, sources):
    # Provenance is reviewed in source_ref(s), but those fields are never
    # projected to clients. Scan the content that may actually be displayed.
    visible = {key: value for key, value in item.items()
               if key not in {"source_ref", "source_refs", "source"}}
    if kind == "literature" and isinstance(item.get("source"), dict):
        visible["source"] = {key: item["source"].get(key)
                             for key in ("title", "locator", "citation")}
    known_ids = {source_id for source_id in sources if len(source_id) >= 20}
    known_ids.add(CORPUS_ROOT_ID)
    pending = [visible]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, str) and (PUBLIC_DRIVE_LINK.search(value)
                                         or any(source_id in value for source_id in known_ids)):
            return True
    return False


@dataclass(frozen=True)
class PublicationPolicy:
    legacy: dict
    sources: dict
    reviews: dict
    quality_reviews: dict | None = None

    def is_legacy(self, kind, item):
        return self.legacy.get(f"{kind}:{item.get('id')}") == fingerprint(item)

    def error(self, kind, item):
        if kind not in KINDS:
            return "unknown_derivative_kind"
        if item.get("status") == "approved" and _public_text_contains_private_source(kind, item, self.sources):
            return "private_source_in_public_content"
        if kind == "questions":
            invalid_case = case_error(item)
            if invalid_case:
                return invalid_case
            if item.get("status") == "approved" and not _text(item.get("explanation")):
                return "explanation_required"
        if self.is_legacy(kind, item):
            if kind in {"questions", "glossary"}:
                # The frozen fingerprint preserves the old publication, but
                # cannot certify it against a later corpus revision.
                quality = (self.quality_reviews or {}).get(f"{kind}:{item.get('id')}")
                if (not isinstance(quality, dict)
                        or quality.get("item_sha256") != fingerprint(item)
                        or not isinstance(quality.get("sources"), list)
                        or not quality["sources"]):
                    return "legacy_source_review_required"
                for ref in quality["sources"]:
                    if not isinstance(ref, dict) or not _text(ref.get("source_id")):
                        return "legacy_source_review_required"
                    source = self.sources.get(ref.get("source_id"))
                    if (not isinstance(source, dict) or source.get("readable") is not True
                            or source.get("kind") != "learning_material"):
                        return "legacy_source_review_required"
                    if (ref.get("modified_time") != source.get("modified_time")
                            or ref.get("snapshot_sha256") != source.get("snapshot_sha256")):
                        return "legacy_source_revision_changed_since_review"
            return None
        if item.get("status") != "approved":
            return None  # Preparation is permitted; the loader does not publish it.
        review = self.reviews.get(f"{kind}:{item.get('id')}")
        if not isinstance(review, dict) or review.get("decision") != "approved":
            return "repository_review_required"
        if review.get("item_sha256") != fingerprint(item):
            return "derivative_changed_since_review"
        purpose = "bibliographic_metadata" if kind == "literature" else "learning_content"
        if review.get("purpose") != purpose or not _text(review.get("reviewer")) or not _date(review.get("reviewed_at")):
            return "invalid_repository_review"
        evidence = review.get("sources")
        if not isinstance(evidence, list) or not evidence:
            return "readable_corpus_evidence_required"
        reviewed_ids = set()
        for ref in evidence:
            if not isinstance(ref, dict) or not _text(ref.get("source_id")):
                return "invalid_source_evidence"
            source_id = ref["source_id"]
            if source_id in reviewed_ids:
                return "duplicate_source_evidence"
            reviewed_ids.add(source_id)
            source = self.sources.get(source_id)
            if not isinstance(source, dict) or source.get("readable") is not True:
                return "source_not_readable"
            if purpose == "learning_content" and source.get("kind") != "learning_material":
                return "bibliography_is_not_knowledge"
            if (ref.get("snapshot_sha256") != source.get("snapshot_sha256")
                    or ref.get("modified_time") != source.get("modified_time")):
                return "source_revision_changed_since_review"
            if not _text(ref.get("locator")):
                return "source_locator_required"
            if purpose == "learning_content" and locator_precision_review_required(ref["locator"]):
                return "source_locator_needs_precision"
        refs = [item.get("source_ref")] if kind == "questions" else item.get("source_refs")
        if not isinstance(refs, list) or not refs:
            return "direct_corpus_sources_required"
        claimed_ids = set()
        for ref in refs:
            match = DRIVE_REF.fullmatch(ref) if isinstance(ref, str) else None
            if match is None:
                return "direct_corpus_sources_required"
            claimed_ids.add(match.group(1))
        if claimed_ids != reviewed_ids:
            return "unreviewed_source_reference"
        if purpose == "learning_content":
            quality = (self.quality_reviews or {}).get(f"{kind}:{item.get('id')}")
            if not isinstance(quality, dict):
                return "learning_quality_review_required"
            if quality.get("item_sha256") != fingerprint(item):
                return "learning_quality_changed_since_review"
            required_checks = ({"meaning", "definition", "examples", "ambiguity", "duplicates", "sources"}
                               if kind == "glossary" else
                               {"meaning", "answer", "explanation", "ambiguity", "duplicates", "sources"})
            checks = quality.get("checks")
            if (quality.get("source_support") != "supported"
                    or quality.get("meaning") != "consistent"
                    or quality.get("issues") != []
                    or not _text(quality.get("note"))
                    or not _text(quality.get("reviewer"))
                    or not _date(quality.get("reviewed_at"))
                    or not isinstance(checks, list)
                    or len(checks) != len(required_checks)
                    or any(not isinstance(check, str) for check in checks)
                    or set(checks) != required_checks):
                return "learning_quality_not_approved"
            quality_sources = quality.get("sources")
            if (not isinstance(quality_sources, list)
                    or len(quality_sources) != len(reviewed_ids)
                    or any(not isinstance(ref, dict) or not _text(ref.get("source_id"))
                           for ref in quality_sources)
                    or {ref["source_id"] for ref in quality_sources} != reviewed_ids):
                return "learning_quality_sources_mismatch"
            for ref in quality_sources:
                source = self.sources[ref["source_id"]]
                if (ref.get("snapshot_sha256") != source.get("snapshot_sha256")
                        or ref.get("modified_time") != source.get("modified_time")
                        or not _text(ref.get("locator"))):
                    return "learning_quality_source_stale"
                if locator_precision_review_required(ref["locator"]):
                    return "learning_quality_locator_needs_precision"
        return None

    def can_publish(self, kind, item):
        return item.get("status") == "approved" and self.error(kind, item) is None


@lru_cache(maxsize=1)
def load_policy():
    # Immutable deployment inputs; restart after a repository/artifact update.
    baseline = json.loads((ROOT / "content/legacy-publication-baseline.json").read_bytes())
    if fingerprint(baseline) != LEGACY_SHA256:
        raise ValueError("Frozen legacy publication baseline changed")
    legacy = baseline["items"]
    registry = json.loads((ROOT / "content/source-corpus.json").read_text(encoding="utf-8"))
    reviews = json.loads((ROOT / "content/publication-reviews.json").read_text(encoding="utf-8"))
    quality = json.loads((ROOT / "content/learning-quality-reviews.json").read_text(encoding="utf-8"))
    if (not isinstance(registry, dict) or not isinstance(reviews, dict)
            or not isinstance(quality, dict)
            or registry.get("schema_version") != 1 or registry.get("corpus_root_id") != CORPUS_ROOT_ID
            or reviews.get("schema_version") != 1 or not isinstance(reviews.get("items"), dict)
            or quality.get("schema_version") != 1 or not isinstance(quality.get("items"), dict)):
        raise ValueError("Invalid publication registry")
    sources = {}
    for source in registry.get("sources", []):
        if not isinstance(source, dict) or not _text(source.get("id")) or source["id"] in sources:
            raise ValueError("Invalid or duplicate corpus source")
        if (source.get("kind") not in {"bibliography", "learning_material"}
                or type(source.get("readable")) is not bool
                or not _text(source.get("title")) or not _text(source.get("modified_time"))
                or not _date(source.get("reviewed_at")) or not _text(source.get("reviewer"))
                or source.get("snapshot_kind") not in {"file_bytes", "extracted_text"}
                or not isinstance(source.get("snapshot_sha256"), str)
                or SHA256.fullmatch(source["snapshot_sha256"]) is None):
            raise ValueError("Incomplete corpus source review")
        sources[source["id"]] = source
    return PublicationPolicy(legacy, sources, reviews["items"], quality["items"])


def validate_publications(kind):
    try:
        policy = load_policy()
        errors = []
        pattern = "**/*.json" if kind == "questions" else "*.json"
        for path in sorted((ROOT / "content" / kind).glob(pattern)):
            entries = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                errors.append(f"{path.name}: expected derivative list")
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    errors.append(f"{path.name}: expected derivative object")
                    continue
                error = policy.error(kind, entry)
                if error:
                    errors.append(f"{kind}:{entry.get('id')}: {error}")
        return errors
    except (OSError, ValueError, KeyError, TypeError):
        return ["Publication registry unavailable or invalid"]
