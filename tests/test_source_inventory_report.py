import json

import pytest

from app.source_inventory import InventoryError
from scripts.source_inventory_report import main, report
from tests.test_source_inventory import item


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
        "changes": {"new": 1, "changed": 0, "unchanged": 1, "missing": 0}}
    assert report(current, processed={"first": {"revision": ("2026-09-25T00:00:00Z", "Lesson", "application/pdf"),
        "review_state": "processed"}})["processing"] == {"new_unprocessed": 1, "processed": 1}
    assert report(current, processed={"first": {"revision": ("2026-09-25T00:00:00Z", "Lesson", "application/pdf"),
        "review_state": "processed"}})["processing_by_format"] == {
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


def test_reviewed_graph_counts_exact_lesson_edges_and_stale_metadata_without_ids():
    current = export(["private-lesson", "private-bibliography", "unreviewed"])
    registry = {"schema_version": 1, "corpus_root_id": "root", "sources": [
        {"id": "private-lesson", "kind": "learning_material", "title": "Lesson",
         "modified_time": "2026-09-25T00:00:00Z", "snapshot_sha256": "a" * 64,
         "readable": True, "snapshot_kind": "extracted_text", "reviewed_at": "2026-09-25", "reviewer": "agent"},
        {"id": "private-bibliography", "kind": "bibliography", "title": "Lesson",
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


def test_reviewed_graph_rejects_conflicting_repository_evidence():
    current = export(["lesson"])
    registry = {"schema_version": 1, "corpus_root_id": "root", "sources": [
        {"id": "lesson", "kind": "learning_material", "title": "Lesson",
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
