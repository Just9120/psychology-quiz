import pytest

from app.source_inventory import InventoryError, processing_status
from scripts import source_capture, source_finalize
from tests.test_source_inventory_report import export


def test_finalize_requires_matching_capture_and_does_not_release_conflict(tmp_path):
    inventory = export(["private"])
    content = tmp_path / "private.txt"
    content.write_text("Первичный текст", encoding="utf-8")
    pending = source_capture.capture(inventory, {}, "private", content, "extracted_text")

    completed = source_finalize.finalize(
        inventory, pending, "private", content,
        reviewer="editor", review_note="Сверены разделы и спорные утверждения",
        reviewed_at="2026-09-26T12:00:00Z",
    )
    assert completed["private"]["snapshot_sha256"] == pending["private"]["snapshot_sha256"]
    assert completed["private"]["review_state"] == "processed"
    assert pending["private"]["review_state"] == "pending_review"
    assert processing_status(source_capture._snapshot(inventory), completed)["private"] == "processed"

    content.write_text("Изменённый текст", encoding="utf-8")
    with pytest.raises(InventoryError, match="captured_content_changed"):
        source_finalize.finalize(inventory, pending, "private", content,
                                 reviewer="editor", review_note="review", reviewed_at="now")
    with pytest.raises(InventoryError, match="review_evidence_required"):
        source_finalize.finalize(inventory, pending, "private", content,
                                 reviewer="", review_note="review", reviewed_at="now")
    with pytest.raises(InventoryError, match="source_not_pending_review"):
        source_finalize.finalize(inventory, completed, "private", content,
                                 reviewer="editor", review_note="review", reviewed_at="now")
    conflicted = {"private": {"revision": pending["private"]["revision"],
                              "review_state": "conflict", "reason": "Disagreement"}}
    with pytest.raises(InventoryError, match="source_not_pending_review"):
        source_finalize.finalize(inventory, conflicted, "private", content,
                                 reviewer="editor", review_note="review", reviewed_at="now")

    newer = export(["private"])
    newer["folders"]["root"][0]["children"][0]["modified_time"] = "2026-09-27T00:00:00Z"
    with pytest.raises(InventoryError, match="source_not_pending_review"):
        source_finalize.finalize(newer, pending, "private", content,
                                 reviewer="editor", review_note="review", reviewed_at="now")
