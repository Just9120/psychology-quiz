import pytest

from app.source_inventory import InventoryError, processing_status
from scripts.source_conflict import record_conflict
from scripts.source_inventory_report import _snapshot
from tests.test_source_inventory_report import export


def test_conflict_holds_exact_source_revision_without_overwriting_prior_review():
    inventory = export(["transcript", "slides", "already-reviewed"])
    prior = {"already-reviewed": {
        "revision": ["2026-09-25T00:00:00Z", "Lesson", "application/pdf"],
        "review_state": "processed", "snapshot_kind": "file_bytes",
        "snapshot_sha256": "a" * 64}}
    updated = record_conflict(
        inventory, prior, "transcript", reason="  Transcript differs from slides  ",
        locator="  Membrane potential section  ", related_source_ids=["slides"],
        reviewed_at="2026-09-26T08:00:00Z")
    assert prior == {"already-reviewed": updated["already-reviewed"]}
    assert updated["transcript"]["review_state"] == "conflict"
    assert updated["transcript"]["revision"] == [
        "2026-09-25T00:00:00Z", "Lesson", "application/pdf"]
    assert updated["transcript"]["related_source_ids"] == ["slides"]
    assert updated["transcript"]["reason"] == "Transcript differs from slides"
    assert processing_status(_snapshot(inventory), updated)["transcript"] == "conflict_review"

    inventory["folders"]["root"][0]["children"][0]["modified_time"] = "2026-09-27T00:00:00Z"
    assert processing_status(_snapshot(inventory), updated)["transcript"] == "changed_unprocessed"


@pytest.mark.parametrize("source_id,reason,related", [
    ("unknown", "disagreement", ["slides"]),
    ("transcript", " ", ["slides"]),
    ("transcript", "disagreement", ["transcript"]),
    ("transcript", "disagreement", ["unknown"]),
    ("transcript", "disagreement", ["slides", "slides"]),
])
def test_conflict_rejects_unverifiable_or_ambiguous_link(source_id, reason, related):
    with pytest.raises(InventoryError):
        record_conflict(export(["transcript", "slides"]), {}, source_id,
                        reason=reason, locator="slide 4", related_source_ids=related,
                        reviewed_at="2026-09-26T08:00:00Z")
