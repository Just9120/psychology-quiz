import json

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
        "changes": {"new": 1, "changed": 0, "unchanged": 1, "missing": 0}}
    assert report(current, processed={"first": {"revision": ("2026-09-25T00:00:00Z", "Lesson", "application/pdf"),
        "review_state": "processed"}})["processing"] == {"new_unprocessed": 1, "processed": 1}


def test_private_inventory_report_rejects_truncated_export_without_leak(tmp_path, capsys):
    path = tmp_path / "sensitive-name.json"
    data = export(["private-file-id"])
    data["folders"]["root"][0]["next_page_token"] = "still-more"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert main(["--current", str(path)]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.strip() == "SOURCE_INVENTORY_STOP: incomplete_folder_listing"
