import copy
import hashlib

import pytest

from app.source_inventory import InventoryError
from scripts.source_review_resume import RAW_COORDINATES, resume_review


def state():
    capture = "\ufeffНачало\r\nПродолжение".encode("utf-8")
    digest = hashlib.sha256(capture).hexdigest()
    ledger = {"records": [], "full_capture_read": 0}
    queue = {"remaining_sources": [{"source_id": "next"}],
             "full_read_evidence": 0, "remaining_without_full_review_evidence": 1}
    processing = {"next": {"review_state": "pending_review", "snapshot_sha256": digest,
                            "revision": ["current", "Title", "text"]}}
    partial = {"source_id": "next", "snapshot_sha256": digest,
               "revision": processing["next"]["revision"], "full_capture_read": False,
               "coordinate_domain": RAW_COORDINATES,
               "characters": len(capture.decode("utf-8")), "read_ranges": [[0, 4]],
               "next_raw_character": 4}
    checkpoint = {"full_review_evidence": 0, "remaining_without_full_review_evidence": 1,
                  "next_remaining_source": {"source_id": "next"},
                  "active_content_review": {"source_id": "next", "next_raw_character": 4}}
    return ledger, queue, processing, checkpoint, partial, capture


def test_resume_preserves_raw_bom_cr_coordinates_and_does_not_mutate_or_approve():
    ledger, queue, processing, checkpoint, partial, capture = state()
    before = copy.deepcopy((ledger, queue, processing, checkpoint, partial))
    result = resume_review(ledger, queue, processing, checkpoint, partial=partial, capture=capture)
    assert result["remaining_range"] == [4, len(capture.decode("utf-8"))]
    assert result["publication_approval"] is False
    assert (ledger, queue, processing, checkpoint, partial) == before


def test_stale_global_cursor_cannot_restart_a_saved_partial_review():
    ledger, queue, processing, checkpoint, partial, capture = state()
    checkpoint["active_content_review"]["next_raw_character"] = 0
    with pytest.raises(InventoryError, match="review_checkpoint_cursor_mismatch"):
        resume_review(ledger, queue, processing, checkpoint, partial=partial, capture=capture)


@pytest.mark.parametrize("ranges", [[[1, 4]], [[0, 3], [2, 4]], [[0, 2], [3, 4]], [[0, True]]])
def test_gap_overlap_or_invalid_coordinates_reject_resume(ranges):
    ledger, queue, processing, checkpoint, partial, capture = state()
    partial["read_ranges"] = ranges
    with pytest.raises(InventoryError, match="invalid_review_ranges"):
        resume_review(ledger, queue, processing, checkpoint, partial=partial, capture=capture)


def test_changed_capture_requires_new_revision_review():
    ledger, queue, processing, checkpoint, partial, capture = state()
    with pytest.raises(InventoryError, match="active_review_capture_changed"):
        resume_review(ledger, queue, processing, checkpoint, partial=partial, capture=capture+b"!")


def test_completed_source_cannot_return_to_remaining_queue():
    ledger, queue, processing, checkpoint, partial, capture = state()
    ledger["records"] = [{"source_id": "next", "full_capture_read": True}]
    with pytest.raises(InventoryError, match="completed_source_requeued"):
        resume_review(ledger, queue, processing, checkpoint, partial=partial, capture=capture)


def test_counts_cannot_mark_missing_sources_as_complete():
    ledger, queue, processing, checkpoint, partial, capture = state()
    checkpoint["full_review_evidence"] = 1
    with pytest.raises(InventoryError, match="review_checkpoint_count_mismatch"):
        resume_review(ledger, queue, processing, checkpoint, partial=partial, capture=capture)


def test_no_active_review_returns_unread_start_without_claiming_capture_verification():
    ledger, queue, processing, checkpoint, partial, capture = state()
    checkpoint["active_content_review"] = None
    result = resume_review(ledger, queue, processing, checkpoint)
    assert result["next_raw_character"] == 0 and result["partial_capture_verified"] is False


def test_normalized_coordinates_cannot_resume_as_raw_publication_coordinates():
    ledger, queue, processing, checkpoint, partial, capture = state()
    partial["coordinate_domain"] = "Normalized LF text without BOM"
    with pytest.raises(InventoryError, match="invalid_active_review_binding"):
        resume_review(ledger, queue, processing, checkpoint, partial=partial, capture=capture)


def test_unbound_completed_evidence_cannot_pass_with_two_missing_hashes():
    ledger, queue, processing, checkpoint, partial, capture = state()
    ledger["records"] = [{"source_id": "done", "full_capture_read": True}]
    ledger["full_capture_read"] = queue["full_read_evidence"] = checkpoint["full_review_evidence"] = 1
    processing["done"] = {"review_state": "conflict"}
    with pytest.raises(InventoryError, match="completed_review_binding_mismatch"):
        resume_review(ledger, queue, processing, checkpoint, partial=partial, capture=capture)
