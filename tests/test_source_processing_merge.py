import pytest

from app.source_inventory import InventoryError
from scripts.source_processing_merge import merge_records


def test_merge_keeps_independent_search_review_and_newer_conflict():
    captured = {"revision": ["time", "title", "mime"],
                "snapshot_kind": "extracted_text", "snapshot_sha256": "a" * 64,
                "extraction_profile": "drive-fetch-text-plain-v1"}
    processed = {**captured, "review_state": "processed", "reviewer": "operator"}
    pending = {**captured, "review_state": "pending_review"}
    held = {**captured, "review_state": "conflict", "reason": "disputed claim",
            "locator": "characters:10:20", "related_source_ids": [], "reviewed_at": "time"}
    search = {"search_ranges": [[0, 10]], "search_reviewer": "operator",
              "search_review_note": "reviewed", "search_reviewed_at": "time"}

    combined = merge_records({"one": processed, "two": held}, {
        "one": {**processed, **search}, "two": pending,
        "three": held,
    })
    assert combined["one"] == {**processed, **search}
    assert combined["two"] == held
    assert combined["three"] == held
    with pytest.raises(InventoryError, match="conflicting_processing_review"):
        merge_records({"one": processed}, {"one": {**processed, "snapshot_sha256": "b" * 64}})
    with pytest.raises(InventoryError, match="unsupported_processing_merge"):
        merge_records({"one": processed}, {"one": {**processed, "unreviewed_approval": True}})
    with pytest.raises(InventoryError, match="unsupported_processing_merge"):
        merge_records({"one": {**processed, "search_ranges": [[0, 10]]}},
                      {"one": {**processed, "search_reviewer": "operator"}})
