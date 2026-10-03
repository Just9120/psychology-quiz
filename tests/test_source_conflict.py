import pytest

from app.source_inventory import InventoryError, processing_status
from scripts.source_conflict import record_conflict
from scripts.source_inventory_report import _snapshot
from tests.test_source_inventory import REVIEW_EVIDENCE
from tests.test_source_inventory_report import export


def test_conflict_holds_exact_source_revision_without_overwriting_prior_review():
    inventory = export(["transcript", "slides", "already-reviewed"])
    prior = {"already-reviewed": {
        "revision": ["2026-09-25T00:00:00Z", "Lesson", "application/pdf"],
        "review_state": "processed", "snapshot_kind": "file_bytes",
        "snapshot_sha256": "a" * 64, **REVIEW_EVIDENCE}}
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


def test_second_conflict_on_same_revision_keeps_both_evidence_records():
    inventory = export(["transcript", "slides"])
    first = record_conflict(inventory, {}, "transcript", reason="First claim is disputed",
                            locator="paragraph 1", related_source_ids=["slides"],
                            reviewed_at="2026-09-26T08:00:00Z")
    first["transcript"]["snapshot_sha256"] = "a" * 64
    second = record_conflict(inventory, first, "transcript", reason="Second claim is disputed",
                             locator="paragraph 8", related_source_ids=[],
                             reviewed_at="2026-09-27T08:00:00Z")

    assert first["transcript"]["reason"] == "First claim is disputed"
    assert second["transcript"]["snapshot_sha256"] == "a" * 64
    assert [issue["locator"] for issue in second["transcript"]["issues"]] == [
        "paragraph 1", "paragraph 8"]
    assert second["transcript"]["related_source_ids"] == ["slides"]
    assert processing_status(_snapshot(inventory), second)["transcript"] == "conflict_review"
    with pytest.raises(InventoryError, match="already_recorded"):
        record_conflict(inventory, second, "transcript", reason="Second claim is disputed",
                        locator="paragraph 8", related_source_ids=[],
                        reviewed_at="2026-09-28T08:00:00Z")


def test_later_conflict_retains_prior_processed_review_evidence():
    inventory = export(["transcript", "slides"])
    previous = {"transcript": {
        "revision": ["2026-09-25T00:00:00Z", "Lesson", "application/pdf"],
        "review_state": "processed", "snapshot_kind": "file_bytes",
        "snapshot_sha256": "a" * 64, **REVIEW_EVIDENCE}}
    held = record_conflict(inventory, previous, "transcript",
                           reason="Contradictory paragraph", locator="paragraph 4",
                           related_source_ids=["slides"],
                           reviewed_at="2026-09-27T08:00:00Z")
    assert held["transcript"]["review_state"] == "conflict"
    assert held["transcript"]["previous_processed_review"] == previous["transcript"]
    assert held["transcript"]["snapshot_kind"] == "file_bytes"
    assert held["transcript"]["snapshot_sha256"] == "a" * 64
    assert processing_status(_snapshot(inventory), held)["transcript"] == "conflict_review"


def test_conflict_retains_exact_pending_capture_without_approving_it():
    inventory = export(["transcript", "slides"])
    prior = {"transcript": {
        "revision": ["2026-09-25T00:00:00Z", "Lesson", "application/pdf"],
        "review_state": "pending_review", "snapshot_kind": "file_bytes",
        "snapshot_sha256": "b" * 64}}
    held = record_conflict(inventory, prior, "transcript", reason="Unverified claim",
                           locator="slide 21", related_source_ids=["slides"],
                           reviewed_at="2026-09-27T14:26:00Z")
    assert held["transcript"]["snapshot_kind"] == "file_bytes"
    assert held["transcript"]["snapshot_sha256"] == "b" * 64
    assert held["transcript"]["review_state"] == "conflict"
    assert prior["transcript"]["review_state"] == "pending_review"


def test_conflict_retains_text_extraction_profile_for_reproducible_review():
    inventory = export(["transcript"])
    prior = {"transcript": {
        "revision": ["2026-09-25T00:00:00Z", "Lesson", "application/pdf"],
        "review_state": "pending_review", "snapshot_kind": "extracted_text",
        "snapshot_sha256": "b" * 64,
        "extraction_profile": "drive-fetch-text-plain-v1"}}
    held = record_conflict(inventory, prior, "transcript", reason="Contaminated transcript",
                           locator="characters:12:34", related_source_ids=[],
                           reviewed_at="2026-09-27T14:26:00Z")
    assert held["transcript"]["extraction_profile"] == "drive-fetch-text-plain-v1"
    assert processing_status(_snapshot(inventory), held)["transcript"] == "conflict_review"
    assert prior["transcript"]["review_state"] == "pending_review"


def test_conflict_does_not_erase_existing_pending_hold():
    inventory = export(["transcript", "slides"])
    prior = {"transcript": {
        "revision": ["2026-09-25T00:00:00Z", "Lesson", "application/pdf"],
        "review_state": "pending_review", "snapshot_kind": "file_bytes",
        "snapshot_sha256": "b" * 64,
        "conflict_hold": {"reason": "Earlier issue", "locator": "slide 2",
                          "related_source_ids": ["slides"]}}}
    with pytest.raises(InventoryError, match="unresolved_prior_conflict_hold"):
        record_conflict(inventory, prior, "transcript", reason="New issue",
                        locator="slide 21", related_source_ids=["slides"],
                        reviewed_at="2026-09-27T14:26:00Z")


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
