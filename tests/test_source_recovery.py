from copy import deepcopy
from pathlib import Path

import pytest

from app.source_inventory import InventoryError, processing_status
from scripts.source_inventory_report import _snapshot
from scripts.source_recovery import recover
from scripts.source_finalize import finalize


def fixture():
    current = {"schema_version": 1, "root_id": "root", "folders": {"root": [{
        "page_token": None, "next_page_token": None,
        "children": [{"id": "one", "title": "Source", "mime_type": "text/plain",
                      "modified_time": "2026-09-30T00:00:00Z", "file_or_folder": "file",
                      "parent_ids": ["root"]}],
    }]}}
    captured = {"revision": ["2026-09-30T00:00:00Z", "Source", "text/plain"],
                "review_state": "pending_review", "snapshot_kind": "extracted_text",
                "snapshot_sha256": "a" * 64}
    return current, {"one": captured}


def test_recovery_preserves_known_objection_even_from_previous_edition():
    current, captures = fixture()
    held = {**captures["one"], "review_state": "conflict", "reason": "unresolved claim",
            "locator": "characters:10:20", "related_source_ids": []}
    held["revision"] = ["2026-09-29T00:00:00Z", "Source", "text/plain"]
    original = deepcopy(captures)
    result = recover(current, captures, [{"one": held}])
    assert result["one"]["review_state"] == "pending_review"
    assert result["one"]["conflict_hold"]["reason"] == "unresolved claim"
    assert processing_status(_snapshot(current), result)["one"] == "pending_review"
    with pytest.raises(InventoryError, match="conflict_resolution_required"):
        finalize(current, result, "one", Path("not-read-before-hold-check.txt"),
                 reviewer="editor", review_note="review", reviewed_at="2026-09-30T00:00:00Z")
    assert captures == original


def test_recovery_never_imports_previous_processed_or_search_approval():
    current, captures = fixture()
    approved = {**captures["one"], "review_state": "processed", "reviewer": "editor",
                "review_note": "previous review", "reviewed_at": "2026-09-30T00:00:00Z",
                "search_ranges": [[0, 20]]}
    assert recover(current, captures, [{"one": approved}]) == captures


def test_disagreeing_recovery_holds_require_editorial_reconstruction():
    current, captures = fixture()
    held = {**captures["one"], "review_state": "conflict", "reason": "first objection",
            "locator": "characters:10:20", "related_source_ids": []}
    with pytest.raises(InventoryError, match="conflicting_recovery_holds"):
        recover(current, captures, [{"one": held}, {"one": {**held, "reason": "other objection"}}])


def test_recovery_rejects_missing_capture_and_existing_approvals():
    current, captures = fixture()
    with pytest.raises(InventoryError, match="captured_snapshot_required"):
        recover(current, {"one": {"revision": captures["one"]["revision"], "review_state": "pending_review"}}, [])
    with pytest.raises(InventoryError, match="capture_search_approval_not_allowed"):
        recover(current, {"one": {**captures["one"], "search_ranges": [[0, 20]]}}, [])
