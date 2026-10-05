"""Verify one private fragment without approving or changing its source record."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from app.content_publication import fingerprint


class FragmentReviewError(ValueError):
    pass


def _ranges(value):
    if not isinstance(value, str) or len(value) > 4000:
        raise FragmentReviewError("fragment_locator_required")
    result = []
    for part in value.split(";"):
        match = re.fullmatch(r"characters:(\d{1,9}):(\d{1,9})", part.strip())
        if match is None or int(match[1]) >= int(match[2]):
            raise FragmentReviewError("fragment_locator_required")
        result.append((int(match[1]), int(match[2])))
    if not result or any(a[1] > b[0] for a,b in zip(result,result[1:])):
        raise FragmentReviewError("fragment_locator_required")
    return result


def _timestamp(value):
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise FragmentReviewError("fragment_review_date_required") from error
    if result.tzinfo is None:
        raise FragmentReviewError("fragment_review_date_required")
    return result


def _derived_pdf_text(claim, source, record, *, private_path):
    """Bind a reviewed bibliographic OCR fragment to unchanged PDF bytes."""
    try:
        original = private_path(Path(claim["original_path"]), suffix=".pdf")
        binding_path = private_path(Path(claim["derivation_receipt"]), suffix=".json")
        text_path = private_path(Path(claim["snapshot_path"]), suffix=".txt")
        if (not original.is_file() or not text_path.is_file()
                or not 0 < text_path.stat().st_size <= 32 * 1024 * 1024
                or not binding_path.is_file() or binding_path.stat().st_size > 65536):
            raise FragmentReviewError("fragment_derivation_invalid")
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        raw = text_path.read_bytes()
        if not isinstance(binding, dict):
            raise FragmentReviewError("fragment_derivation_invalid")
        with original.open("rb") as original_file:
            if original_file.read(5) != b"%PDF-":
                raise FragmentReviewError("fragment_derivation_invalid")
            original_file.seek(0)
            original_digest = hashlib.file_digest(original_file, "sha256").hexdigest()
        if (binding.get("schema_version") != 1
                or binding.get("source_id") != source.get("id")
                or binding.get("revision") != record.get("revision")
                or binding.get("original_sha256") != source.get("snapshot_sha256")
                or original_digest != source.get("snapshot_sha256")
                or binding.get("derived_text_sha256") != hashlib.sha256(raw).hexdigest()
                or claim.get("derived_text_sha256") != binding.get("derived_text_sha256")
                or not isinstance(binding.get("extraction_profile"), str)
                or not binding["extraction_profile"].strip()):
            raise FragmentReviewError("fragment_derivation_changed")
        text = raw.decode("utf-8")
        # Page coordinates are explicit form-feed boundaries, never guessed offsets.
        pages, start = [], 0
        for end, char in enumerate(text):
            if char == "\f":
                pages.append((start, end))
                start = end + 1
        if text[start:].strip():
            pages.append((start, len(text)))
        if not pages:
            raise FragmentReviewError("fragment_pdf_pages_required")
        reviewed = claim.get("visual_pages_read")
        if (not isinstance(reviewed, list) or not reviewed
                or any(type(page) is not int or not 1 <= page <= len(pages) for page in reviewed)):
            raise FragmentReviewError("fragment_pdf_visual_review_required")
        for a, b in _ranges(claim.get("locator")):
            if not any(i in reviewed and start <= a < b <= end
                       for i, (start, end) in enumerate(pages, 1)):
                raise FragmentReviewError("fragment_pdf_visual_review_required")
        return text, pages
    except FragmentReviewError:
        raise
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as error:
        raise FragmentReviewError("fragment_derivation_invalid") from error


def _held_ranges(locator, pdf_pages):
    if pdf_pages is None or not isinstance(locator, str) or not locator.startswith("page:"):
        return _ranges(locator)
    result = []
    for part in locator.split(";"):
        match = re.fullmatch(r"page:(\d{1,6})", part.strip())
        if match is None or not 1 <= int(match[1]) <= len(pdf_pages):
            raise FragmentReviewError("fragment_conflict_scope_unknown")
        result.append(pdf_pages[int(match[1]) - 1])
    return result


def verify_fragment_review(dossier, source, record, public_item, *, private_path):
    """Keep record/hold fingerprints and exact excerpts bound to a single item.

    Version 2 is a used-fragment review, never a source-wide finalization. An
    older unresolved hold cannot be mapped to new text by assuming old offsets.
    """
    claim = dossier.get("scoped_claim_review")
    kind, item_id = dossier.get("kind"), dossier.get("item_id")
    purpose = "bibliographic_metadata" if kind == "literature" else "learning_content"
    review = dossier.get("publication_review")
    if (kind not in {"questions", "glossary", "literature"}
            or not isinstance(public_item, dict) or public_item.get("id") != item_id
            or not isinstance(claim, dict) or claim.get("schema_version") != 2
            or claim.get("kind") != kind or claim.get("item_id") != item_id
            or claim.get("purpose") != purpose
            or claim.get("source_id") != source.get("id")
            or len(dossier.get("sources", [])) != 1
            or not isinstance(review, dict) or review.get("purpose") != purpose
            or review.get("decision") != "approved"
            or claim.get("snapshot_sha256") != source.get("snapshot_sha256")
            or claim.get("processing_sha256") != fingerprint(record)
            or source.get("snapshot_kind") not in {"extracted_text", "file_bytes"}
            or not isinstance(claim.get("reviewer"), str) or not claim["reviewer"].strip()
            or not isinstance(claim.get("note"), str) or not claim["note"].strip()):
        raise FragmentReviewError("fragment_review_required")
    # Explicitly narrowed historical exceptions stay on their original path.
    if (kind, item_id) in {("questions", "m1_psyf_070"), ("questions", "m1_psyf_071"), ("glossary", "dopamine")}:
        raise FragmentReviewError("named_scoped_exception_required")
    reference_field = "source_ref" if kind == "questions" else "source_refs"
    full_item = {**public_item, reference_field: dossier.get(reference_field)}
    if (claim.get("item_sha256") != fingerprint(full_item)
            or review.get("item_sha256") != claim["item_sha256"]):
        raise FragmentReviewError("fragment_item_changed")
    reviewed_at = _timestamp(claim.get("reviewed_at"))
    if (reviewed_at < _timestamp(source.get("modified_time"))
            or review.get("reviewer") != claim["reviewer"]
            or review.get("reviewed_at") != reviewed_at.date().isoformat()
            or source.get("reviewer") != claim["reviewer"]
            or source.get("reviewed_at") != reviewed_at.date().isoformat()):
        raise FragmentReviewError("fragment_review_date_required")
    selected = _ranges(claim.get("locator"))
    pdf_text, pdf_pages = None, None
    if source.get("snapshot_kind") == "file_bytes":
        if kind != "literature" or record.get("revision", [None, None, None])[2] != "application/pdf":
            raise FragmentReviewError("fragment_pdf_bibliography_only")
        pdf_text, pdf_pages = _derived_pdf_text(claim, source, record, private_path=private_path)
    held = []
    if "conflict_hold" in record:
        # No cross-edition offset inference. Resolve or explicitly recapture the hold first.
        raise FragmentReviewError("fragment_previous_hold_unresolved")
    if record.get("review_state") == "conflict":
        if reviewed_at <= _timestamp(record.get("reviewed_at")):
            raise FragmentReviewError("fragment_review_date_required")
        held.extend(_held_ranges(record.get("locator"), pdf_pages))
    issues = record.get("issues", [])
    if not isinstance(issues, list):
        raise FragmentReviewError("fragment_conflict_scope_unknown")
    for issue in issues:
        if not isinstance(issue, dict):
            raise FragmentReviewError("fragment_conflict_scope_unknown")
        held.extend(_held_ranges(issue.get("locator"), pdf_pages))
    if any(a < d and c < b for a,b in selected for c,d in held):
        raise FragmentReviewError("fragment_overlaps_conflict")
    evidence = [{"source_id": source["id"], "snapshot_sha256": source["snapshot_sha256"],
                 "modified_time": source["modified_time"], "locator": claim["locator"]}]
    expected = "drive:" + source["id"] + "#" + claim["locator"]
    if dossier.get(reference_field) != (expected if kind == "questions" else [expected]):
        raise FragmentReviewError("fragment_evidence_mismatch")
    reviews = [review]
    if kind != "literature":
        quality = dossier.get("quality_review")
        if (not isinstance(quality, dict) or quality.get("item_sha256") != claim["item_sha256"]
                or quality.get("purpose") != "learning_content"
                or quality.get("decision") != "approved"
                or quality.get("reviewer") != claim["reviewer"]
                or quality.get("reviewed_at") != reviewed_at.date().isoformat()):
            raise FragmentReviewError("fragment_quality_review_required")
        reviews.append(quality)
    if any(item.get("sources") != evidence for item in reviews):
        raise FragmentReviewError("fragment_evidence_mismatch")
    try:
        path = private_path(Path(claim["snapshot_path"]), suffix=".txt")
        if not path.is_file() or not 0 < path.stat().st_size <= 32 * 1024 * 1024:
            raise FragmentReviewError("fragment_snapshot_invalid")
        raw = path.read_bytes()
        if pdf_text is None and hashlib.sha256(raw).hexdigest() != source["snapshot_sha256"]:
            raise FragmentReviewError("fragment_snapshot_changed")
        text = pdf_text if pdf_text is not None else raw.decode("utf-8")
        if any(end > len(text) for _,end in [*selected,*held]):
            raise FragmentReviewError("fragment_locator_out_of_bounds")
        excerpts = [text[start:end] for start,end in selected]
        if any(not excerpt.strip() for excerpt in excerpts):
            raise FragmentReviewError("fragment_empty_excerpt")
        digest = hashlib.sha256(json.dumps(excerpts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    except FragmentReviewError:
        raise
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as error:
        raise FragmentReviewError("fragment_snapshot_invalid") from error
    if claim.get("excerpt_sha256") != digest:
        raise FragmentReviewError("fragment_excerpt_changed")
