import json
import subprocess

import pytest

from app.source_inventory import InventoryError
from scripts import source_inventory_report as inventory_report
from scripts.source_inventory_report import main, report
from tests.test_source_inventory import REVIEW_EVIDENCE, item


def export(file_ids):
    return {"schema_version": 1, "root_id": "root", "folders": {"root": [
        {"page_token": None, "next_page_token": None,
         "children": [item(file_id, "root") for file_id in file_ids]}]}}


def test_private_inventory_report_reconciles_without_exposing_ids(tmp_path, capsys):
    current, previous = export(["first", "second"]), export(["first"])
    current_file = tmp_path / "private-current.json"
    previous_file = tmp_path / "private-previous.json"
    current_file.write_text(json.dumps(current), encoding="utf-8")
    previous_file.write_text(json.dumps(previous), encoding="utf-8")
    assert main(["--current", str(current_file), "--previous", str(previous_file)]) == 0
    output = capsys.readouterr()
    assert "first" not in output.out and "second" not in output.out
    assert "root" not in output.out
    assert json.loads(output.out) == {"folders": 1, "files": 2, "linked_lessons": 0,
        "processing": {"new_unprocessed": 2},
        "processing_by_format": {"application/pdf": {"new_unprocessed": 2}},
        "changes": {"new": 1, "changed": 0, "relocated": 0, "unchanged": 1, "missing": 0}}
    assert report(current, processed={"first": {"revision": ("2026-09-25T00:00:00Z", "Lesson", "application/pdf"),
        "review_state": "processed", "snapshot_kind": "file_bytes",
        "snapshot_sha256": "a" * 64, **REVIEW_EVIDENCE}})["processing"] == {"new_unprocessed": 1, "processed": 1}
    assert report(current, processed={"first": {"revision": ("2026-09-25T00:00:00Z", "Lesson", "application/pdf"),
        "review_state": "processed", "snapshot_kind": "file_bytes",
        "snapshot_sha256": "a" * 64, **REVIEW_EVIDENCE}})["processing_by_format"] == {
            "application/pdf": {"new_unprocessed": 1, "processed": 1}}


def test_private_inventory_report_rejects_truncated_export_without_leak(tmp_path, capsys):
    path = tmp_path / "sensitive-name.json"
    data = export(["private-file-id"])
    data["folders"]["root"][0]["next_page_token"] = "still-more"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert main(["--current", str(path)]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.strip() == "SOURCE_INVENTORY_STOP: incomplete_folder_listing"


def test_conflict_holds_derivatives_of_both_related_sources_until_review():
    current = export(["transcript", "slides"])
    sources = [{"id": source_id, "kind": "learning_material", "title": "Lesson",
                "corpus_path": "Lesson", "modified_time": "2026-09-25T00:00:00Z",
                "snapshot_sha256": "a" * 64, "readable": True,
                "snapshot_kind": "extracted_text", "reviewed_at": "2026-09-25",
                "reviewer": "agent"} for source_id in ("transcript", "slides")]
    registry = {"schema_version": 1, "corpus_root_id": "root", "sources": sources}
    curriculum = {"schema_version": 1, "disciplines": {}, "topics": {}}
    reviews = {"schema_version": 1, "items": {
        f"questions:{source_id}": {"decision": "approved", "sources": [{
            "source_id": source_id, "modified_time": source["modified_time"],
            "snapshot_sha256": source["snapshot_sha256"]}]}
        for source_id, source in zip(("transcript", "slides"), sources)}}
    processed = {"transcript": {
        "revision": ["2026-09-25T00:00:00Z", "Lesson", "application/pdf"],
        "review_state": "conflict", "reason": "Statements disagree",
        "related_source_ids": ["slides"]}}

    def entries(inventory):
        queue = inventory_report.private_review_queue(
            inventory_report._snapshot(inventory), registry, curriculum,
            processed=processed, reviews=reviews)
        return {entry["file_id"]: entry for entry in queue["files"]}

    initial = entries(current)
    # A partial processing snapshot must still yield the complete review queue.
    assert set(initial) == {"transcript", "slides"}
    assert initial["transcript"]["derivative_ids_requiring_review"] == ["questions:transcript"]
    assert initial["slides"]["processing_state"] == "new_unprocessed"
    assert initial["slides"]["related_conflict_review_required"] is True
    assert initial["slides"]["derivative_ids_requiring_review"] == ["questions:slides"]

    current["folders"]["root"][0]["children"][0]["modified_time"] = "2026-09-26T00:00:00Z"
    changed = entries(current)
    assert changed["transcript"]["processing_state"] == "changed_unprocessed"
    assert changed["slides"]["derivative_ids_requiring_review"] == ["questions:slides"]

    processed["transcript"] = {
        "revision": ["2026-09-26T00:00:00Z", "Lesson", "application/pdf"],
        "review_state": "pending_review", "snapshot_kind": "extracted_text",
        "snapshot_sha256": "b" * 64,
        "conflict_hold": {"reason": "Statements disagree", "locator": "slide 4",
                          "related_source_ids": ["slides"]}}
    assert entries(current)["slides"]["derivative_ids_requiring_review"] == ["questions:slides"]

    processed["transcript"] = {"revision": ["2026-09-26T00:00:00Z", "Lesson", "application/pdf"],
                               "review_state": "processed", "snapshot_kind": "extracted_text",
                               "snapshot_sha256": "b" * 64, **REVIEW_EVIDENCE}
    assert entries(current)["slides"]["related_conflict_review_required"] is False


def test_private_queue_distinguishes_reviewed_format_links_from_candidates():
    current = export(["doc", "pdf"])
    doc, pdf = current["folders"]["root"][0]["children"]
    doc.update(title="Lecture", mime_type="application/vnd.google-apps.document")
    pdf["title"] = "Lecture.pdf"
    registry = {"schema_version": 1, "corpus_root_id": "root", "sources": [{
        "id": "doc", "kind": "learning_material", "title": "Lecture",
        "corpus_path": "Lecture", "modified_time": doc["modified_time"],
        "snapshot_sha256": "a" * 64, "readable": True,
        "snapshot_kind": "extracted_text", "reviewed_at": "2026-09-25",
        "reviewer": "editor"}]}
    curriculum = {"schema_version": 1, "disciplines": {"d": {"title": "Discipline"}},
                  "topics": {"topic": {"title": "Lecture", "discipline_id": "d",
                     "source": {"source_id": "doc", "modified_time": doc["modified_time"],
                                "snapshot_sha256": "a" * 64}}}}
    links = [{"source_id": entry["id"], "lesson_id": "lesson", "topic_id": "topic",
              "format": format_name,
              "revision": [entry["modified_time"], entry["title"], entry["mime_type"]],
              "corpus_path": entry["title"], **REVIEW_EVIDENCE}
             for entry, format_name in ((doc, "transcript"), (pdf, "slides"))]

    def queue(selected):
        return inventory_report.private_review_queue(
            inventory_report._snapshot(current), registry, curriculum, links=selected)

    assert queue([])["format_variant_candidates"][0]["link_state"] == "candidate"
    assert queue(links[:1])["format_variant_candidates"][0]["link_state"] == "candidate"
    reviewed = queue(links)
    assert reviewed["format_variant_candidates"][0]["link_state"] == "linked"
    assert all(entry["linked_lesson_ids"] == ["lesson"] for entry in reviewed["files"])
    with pytest.raises(InventoryError, match="unknown_lesson_topic"):
        queue([{**links[0], "topic_id": "invented"}])
    with pytest.raises(InventoryError, match="stale_lesson_link"):
        queue([{**links[0], "revision": ["old", *links[0]["revision"][1:]]}])


def test_frozen_legacy_derivatives_stay_in_private_source_review_queue(tmp_path):
    question = {"id": "old", "status": "approved", "source_ref": "drive:private#slide-2"}
    altered = {"id": "altered", "status": "approved", "source_ref": "drive:private",
               "question": "Changed since frozen baseline"}
    unmapped = {"id": "unmapped", "status": "approved", "source_ref": "old-course-lecture"}
    quality_mapped = {"id": "quality", "status": "approved", "source_ref": "old-lecture"}
    (tmp_path / "content/questions").mkdir(parents=True)
    (tmp_path / "content/questions/bank.json").write_text(
        json.dumps([question, altered, unmapped, quality_mapped]), encoding="utf-8")
    baseline = {"items": {"questions:old": inventory_report.fingerprint(question),
                          "questions:altered": "0" * 64,
                          "questions:unmapped": inventory_report.fingerprint(unmapped),
                          "questions:quality": inventory_report.fingerprint(quality_mapped)}}
    quality = {"questions:quality": {
        "item_sha256": inventory_report.fingerprint(quality_mapped),
        "sources": [{"source_id": "private"}]},
        "questions:unmapped": {"item_sha256": "0" * 64,
                               "sources": [{"source_id": "private"}]}}
    links, unresolved = inventory_report.legacy_derivative_links(
        tmp_path, baseline, quality, expected_sha256=inventory_report.fingerprint(baseline))
    assert links == {"questions:old": ["private"], "questions:quality": ["private"]}
    assert unresolved == ["questions:unmapped"]
    with pytest.raises(InventoryError, match="invalid_legacy_baseline"):
        inventory_report.legacy_derivative_links(tmp_path, baseline, quality,
                                                 expected_sha256="0" * 64)
    source = {"id": "private", "kind": "learning_material", "title": "Lesson",
              "corpus_path": "Lesson", "modified_time": "2026-09-25T00:00:00Z",
              "snapshot_sha256": "a" * 64, "readable": True,
              "snapshot_kind": "extracted_text", "reviewed_at": "2026-09-25", "reviewer": "agent"}
    registry = {"schema_version": 1, "corpus_root_id": "root", "sources": [source]}
    curriculum = {"schema_version": 1, "disciplines": {}, "topics": {}}
    queue = inventory_report.private_review_queue(
        inventory_report._snapshot(export(["private"])), registry, curriculum,
        legacy_derivatives=links, unmapped_legacy_derivatives=unresolved)
    entry = queue["files"][0]
    assert entry["legacy_derivative_ids"] == ["questions:old", "questions:quality"]
    assert entry["linked_derivative_ids"] == ["questions:old", "questions:quality"]
    assert entry["derivative_ids_requiring_review"] == ["questions:old", "questions:quality"]
    assert queue["unmapped_legacy_derivative_ids"] == ["questions:unmapped"]
    missing = inventory_report.private_review_queue(
        inventory_report._snapshot(export([])), registry, curriculum,
        legacy_derivatives=links)["missing_tracked_sources"][0]
    assert missing["legacy_derivative_ids"] == ["questions:old", "questions:quality"]
    with pytest.raises(InventoryError, match="invalid_legacy_derivatives"):
        inventory_report.private_review_queue(
            inventory_report._snapshot(export(["private"])), registry, curriculum,
            legacy_derivatives={"questions:old": ["unknown"]})


def test_reviewed_graph_counts_exact_lesson_edges_and_stale_metadata_without_ids():
    current = export(["private-lesson", "private-bibliography", "unreviewed"])
    registry = {"schema_version": 1, "corpus_root_id": "root", "sources": [
        {"id": "private-lesson", "kind": "learning_material", "title": "Lesson", "corpus_path": "Lesson",
         "modified_time": "2026-09-25T00:00:00Z", "snapshot_sha256": "a" * 64,
         "readable": True, "snapshot_kind": "extracted_text", "reviewed_at": "2026-09-25", "reviewer": "agent"},
        {"id": "private-bibliography", "kind": "bibliography", "title": "Lesson", "corpus_path": "Lesson",
         "modified_time": "2026-09-25T00:00:00Z", "snapshot_sha256": "b" * 64,
         "readable": True, "snapshot_kind": "file_bytes", "reviewed_at": "2026-09-25", "reviewer": "agent"},
    ]}
    curriculum = {"schema_version": 1, "disciplines": {"discipline": {"title": "D"}},
                  "topics": {"one": {"title": "One", "discipline_id": "discipline", "source": {
                      "source_id": "private-lesson", "modified_time": "2026-09-25T00:00:00Z",
                      "snapshot_sha256": "a" * 64}}}}
    result = report(current, registry=registry, curriculum=curriculum)["reviewed_graph"]
    assert result == {"tracked_sources": 2, "source_kinds": {"bibliography": 1, "learning_material": 1},
                      "source_metadata": {"current": 2}, "current_by_format": {"application/pdf": 2},
                      "untracked_inventory_files": 1, "reviewed_lesson_edges": 1,
                      "lesson_metadata": {"current": 1}, "unique_lesson_files": 1,
                      "multi_lesson_files": 0, "reviewed_learning_without_lesson": 0}
    assert "private-lesson" not in json.dumps(result)
    assert "private-bibliography" not in json.dumps(result)

    current["folders"]["root"][0]["children"][0]["modified_time"] = "2026-09-26T00:00:00Z"
    changed = report(current, registry=registry, curriculum=curriculum)["reviewed_graph"]
    assert changed["source_metadata"] == {"changed": 1, "current": 1}
    assert changed["lesson_metadata"] == {"changed": 1}
    assert changed["current_by_format"] == {"application/pdf": 1}

    current["folders"]["root"][0]["children"] = current["folders"]["root"][0]["children"][1:]
    missing = report(current, registry=registry, curriculum=curriculum)["reviewed_graph"]
    assert missing["source_metadata"] == {"current": 1, "missing": 1}
    assert missing["lesson_metadata"] == {"missing": 1}
    relocated = report(export(["private-lesson", "private-bibliography", "unreviewed"]),
                       registry={**registry, "sources": [{**registry["sources"][0],
                           "corpus_path": "Former/Lesson"}, registry["sources"][1]]},
                       curriculum=curriculum)["reviewed_graph"]
    assert relocated["source_metadata"] == {"current": 1, "relocated": 1}
    assert relocated["lesson_metadata"] == {"relocated": 1}


def test_reviewed_graph_rejects_conflicting_repository_evidence():
    current = export(["lesson"])
    registry = {"schema_version": 1, "corpus_root_id": "root", "sources": [
        {"id": "lesson", "kind": "learning_material", "title": "Lesson", "corpus_path": "Lesson",
         "modified_time": "2026-09-25T00:00:00Z", "snapshot_sha256": "a" * 64,
         "readable": True, "snapshot_kind": "extracted_text", "reviewed_at": "2026-09-25", "reviewer": "agent"}]}
    curriculum = {"schema_version": 1, "disciplines": {"discipline": {}},
                  "topics": {"one": {"title": "One", "discipline_id": "discipline", "source": {
                      "source_id": "lesson", "modified_time": "2026-09-25T00:00:00Z",
                      "snapshot_sha256": "b" * 64}}}}
    with pytest.raises(InventoryError, match="invalid_reviewed_lesson"):
        report(current, registry=registry, curriculum=curriculum)
    with pytest.raises(InventoryError, match="invalid_reviewed_source"):
        report(current, registry={**registry, "sources": registry["sources"] * 2},
               curriculum=curriculum)
    with pytest.raises(InventoryError, match="invalid_reviewed_graph"):
        report(current, registry={**registry, "corpus_root_id": "other"}, curriculum=curriculum)


def test_private_queue_keeps_file_level_work_ignored_and_aggregate_stdout_safe(tmp_path, monkeypatch, capsys):
    current = export(["reviewed-private", "unreviewed-private"])
    source = {"id": "reviewed-private", "kind": "learning_material", "title": "Lesson",
              "corpus_path": "Lesson",
              "modified_time": "2026-09-25T00:00:00Z", "snapshot_sha256": "a" * 64,
              "readable": True, "snapshot_kind": "extracted_text", "reviewed_at": "2026-09-25",
              "reviewer": "agent"}
    registry = {"schema_version": 1, "corpus_root_id": "root", "sources": [source]}
    curriculum = {"schema_version": 1, "disciplines": {"discipline": {}},
                  "topics": {"topic": {"title": "One", "discipline_id": "discipline", "source": {
                      "source_id": source["id"], "modified_time": source["modified_time"],
                      "snapshot_sha256": source["snapshot_sha256"]}}}}
    (tmp_path / "content").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "content/source-corpus.json").write_text(json.dumps(registry), encoding="utf-8")
    (tmp_path / "content/curriculum.json").write_text(json.dumps(curriculum), encoding="utf-8")
    reviews = {"schema_version": 1, "items": {"questions:example": {"decision": "approved",
        "sources": [{"source_id": source["id"], "modified_time": source["modified_time"],
                     "snapshot_sha256": source["snapshot_sha256"]}]}}}
    (tmp_path / "content/publication-reviews.json").write_text(
        json.dumps(reviews), encoding="utf-8")
    quality = {"schema_version": 1, "items": {
        "questions:legacy-supported": {"source_support": "supported", "sources": [
            {"source_id": source["id"], "modified_time": source["modified_time"],
             "snapshot_sha256": source["snapshot_sha256"], "locator": "slide 1"}]},
        "questions:legacy-partial": {"source_support": "partial", "sources": [
            {"source_id": source["id"], "modified_time": source["modified_time"],
             "snapshot_sha256": source["snapshot_sha256"], "locator": "slide 2"}]},
        "questions:wide-locator": {"source_support": "supported", "sources": [
            {"source_id": source["id"], "modified_time": source["modified_time"],
             "snapshot_sha256": source["snapshot_sha256"],
             "locator": "extracted text, Unicode characters (zero-based, end exclusive): 0:8564"}]},
    }}
    (tmp_path / "content/learning-quality-reviews.json").write_text(
        json.dumps(quality), encoding="utf-8")
    baseline = {"items": {}}
    (tmp_path / "content/legacy-publication-baseline.json").write_text(
        json.dumps(baseline), encoding="utf-8")
    monkeypatch.setattr(inventory_report, "LEGACY_SHA256", inventory_report.fingerprint(baseline))
    current_path = tmp_path / "data/current.json"
    current_path.write_text(json.dumps(current), encoding="utf-8")
    target = tmp_path / "data/private-queue.json"
    monkeypatch.setattr(inventory_report, "REPO_ROOT", tmp_path)
    args = ["--current", str(current_path), "--reviewed", "--private-queue", str(target)]
    assert main(args) == 0
    output = capsys.readouterr()
    assert "reviewed-private" not in output.out and "unreviewed-private" not in output.out
    queue = json.loads(target.read_text(encoding="utf-8"))
    entries = {item["file_id"]: item for item in queue["files"]}
    assert entries["reviewed-private"]["registry_state"] == "current"
    assert entries["reviewed-private"]["linked_topic_ids"] == ["topic"]
    assert entries["reviewed-private"]["linked_derivative_ids"] == ["questions:example"]
    assert entries["reviewed-private"]["legacy_derivative_ids"] == []
    assert entries["reviewed-private"]["derivative_ids_requiring_review"] == []
    assert entries["reviewed-private"]["derivative_review_required"] is False
    assert entries["reviewed-private"]["quality_review_item_ids"] == [
        "questions:legacy-partial", "questions:legacy-supported", "questions:wide-locator"]
    assert entries["reviewed-private"]["quality_review_priority_ids"] == [
        "questions:legacy-partial", "questions:wide-locator"]
    assert entries["reviewed-private"]["quality_review_evidence"] == {
        "questions:legacy-supported": {"locator": "slide 1", "source_support": "supported",
                                       "revision_current": True,
                                       "locator_precision_review_required": False},
        "questions:legacy-partial": {"locator": "slide 2", "source_support": "partial",
                                     "revision_current": True,
                                     "locator_precision_review_required": False},
        "questions:wide-locator": {
            "locator": "extracted text, Unicode characters (zero-based, end exclusive): 0:8564",
            "source_support": "supported", "revision_current": True,
            "locator_precision_review_required": True},
    }
    assert entries["unreviewed-private"]["quality_review_evidence"] == {}
    assert entries["unreviewed-private"]["registry_state"] == "untracked"
    assert all(item["processing_state"] == "unknown_no_processing_snapshot" for item in entries.values())
    assert all(item["paths"] == [["Lesson"]] for item in entries.values())

    changed = export(["reviewed-private"])
    changed["folders"]["root"][0]["children"][0]["modified_time"] = "2026-09-26T00:00:00Z"
    changed_queue = inventory_report.private_review_queue(
        inventory_report._snapshot(changed), registry, curriculum, reviews=reviews)
    changed_entry = changed_queue["files"][0]
    assert changed_entry["registry_state"] == "changed"
    assert changed_entry["linked_derivative_ids"] == ["questions:example"]
    assert changed_entry["derivative_ids_requiring_review"] == ["questions:example"]
    assert changed_entry["derivative_review_required"] is True
    assert inventory_report.private_review_queue(
        inventory_report._snapshot(changed), registry, curriculum, reviews=reviews,
        quality_reviews=quality)["files"][0]["quality_review_priority_ids"] == [
            "questions:legacy-partial", "questions:legacy-supported", "questions:wide-locator"]
    stale_quality = {"schema_version": 1, "items": {"questions:old": {
        "source_support": "supported", "sources": [{"source_id": source["id"],
            "modified_time": source["modified_time"], "snapshot_sha256": "b" * 64,
            "locator": "slide 3"}]}}}
    stale_entry = inventory_report.private_review_queue(
        inventory_report._snapshot(current), registry, curriculum,
        quality_reviews=stale_quality)["files"][0]
    assert stale_entry["quality_review_priority_ids"] == ["questions:old"]
    assert stale_entry["quality_review_evidence"]["questions:old"] == {
        "locator": "slide 3", "source_support": "supported", "revision_current": False,
        "locator_precision_review_required": False}
    with pytest.raises(InventoryError, match="invalid_quality_review_source"):
        inventory_report.private_review_queue(
            inventory_report._snapshot(current), registry, curriculum,
            quality_reviews={"schema_version": 1, "items": {"questions:missing-locator": {
                "source_support": "partial", "sources": [{"source_id": source["id"],
                "modified_time": source["modified_time"],
                "snapshot_sha256": source["snapshot_sha256"]}]}}})
    missing_queue = inventory_report.private_review_queue(
        inventory_report._snapshot(export([])), registry, curriculum, reviews=reviews)
    assert missing_queue["missing_tracked_sources"][0]["derivative_review_required"] is True

    # A discovered file must remain in the private work queue if it vanishes
    # before editorial review. Absence alone is not approval for deletion.
    vanished = inventory_report.private_review_queue(
        inventory_report._snapshot(export(["reviewed-private"])), registry, curriculum,
        previous=inventory_report._snapshot(current), reviews=reviews)
    assert vanished["missing_tracked_sources"] == []
    assert vanished["missing_untracked_files"] == [{
        "file_id": "unreviewed-private", "title": "Lesson",
        "mime_type": "application/pdf", "modified_time": "2026-09-25T00:00:00Z",
        "last_seen_paths": [["Lesson"]], "inventory_change": "missing",
        "processing_state": "unknown_no_processing_snapshot",
        "review_action": "verify_access_or_removal"}]
    stale_reviews = {"schema_version": 1, "items": {"questions:example": {
        "decision": "approved", "sources": [{"source_id": source["id"],
            "modified_time": source["modified_time"], "snapshot_sha256": "b" * 64}]}}}
    stale_queue = inventory_report.private_review_queue(
        inventory_report._snapshot(current), registry, curriculum, reviews=stale_reviews)
    assert stale_queue["files"][0]["registry_state"] == "current"
    assert stale_queue["files"][0]["derivative_ids_requiring_review"] == ["questions:example"]

    conflict_queue = inventory_report.private_review_queue(
        inventory_report._snapshot(current), registry, curriculum, reviews=reviews,
        processed={source["id"]: {"revision": [source["modified_time"], source["title"],
                                  "application/pdf"], "review_state": "conflict",
                                  "reason": "Same-lesson sources disagree"}})
    assert conflict_queue["files"][0]["registry_state"] == "current"
    assert conflict_queue["files"][0]["processing_state"] == "conflict_review"
    assert conflict_queue["files"][0]["derivative_ids_requiring_review"] == ["questions:example"]
    assert inventory_report.private_review_queue(
        inventory_report._snapshot(current), registry, curriculum, reviews=reviews,
        quality_reviews=quality, processed={source["id"]: {
            "revision": [source["modified_time"], source["title"], "application/pdf"],
            "review_state": "conflict", "reason": "Same-lesson sources disagree"}}
    )["files"][0]["quality_review_priority_ids"] == [
        "questions:legacy-partial", "questions:legacy-supported", "questions:wide-locator"]

    original = target.read_bytes()
    assert main(args) == 1
    assert "SOURCE_INVENTORY_STOP: FileExistsError" in capsys.readouterr().err
    assert target.read_bytes() == original
    outside = tmp_path / "unsafe.json"
    assert main([*args[:-1], str(outside)]) == 1
    assert capsys.readouterr().err.strip() == "SOURCE_INVENTORY_STOP: private_queue_requires_ignored_data_json"
    assert not outside.exists()
    (tmp_path / ".gitignore").write_text("", encoding="utf-8")
    not_ignored = tmp_path / "data/not-ignored.json"
    assert main([*args[:-1], str(not_ignored)]) == 1
    assert capsys.readouterr().err.strip() == "SOURCE_INVENTORY_STOP: private_queue_requires_ignored_data_json"
    assert not not_ignored.exists()
