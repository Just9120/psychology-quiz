import hashlib
import json
import os
import stat
import subprocess

import pytest

from app.source_inventory import InventoryError, processing_status
from scripts import source_batch_capture, source_capture
from tests.test_source_inventory import REVIEW_EVIDENCE
from tests.test_source_inventory_report import export


def test_capture_hashes_private_bytes_and_preserves_other_records(tmp_path):
    content = tmp_path / "private.txt"
    raw = b"x" * (1024 * 1024 - 1) + "ё".encode("utf-8")
    content.write_bytes(raw)
    prior = {"other": {"revision": ["old", "title", "mime"],
                       "review_state": "pending_review"}}
    updated = source_capture.capture(export(["private"]), prior, "private", content,
                                    "extracted_text")
    assert updated["other"] == prior["other"]
    assert updated["private"]["review_state"] == "pending_review"
    assert updated["private"]["snapshot_sha256"] == hashlib.sha256(raw).hexdigest()
    assert processing_status(source_capture._snapshot(export(["private"])), updated)["private"] == "pending_review"
    processed = {"private": {**updated["private"], "review_state": "processed",
                             **REVIEW_EVIDENCE}}
    with pytest.raises(InventoryError, match="source_revision_already_processed"):
        source_capture.capture(export(["private"]), processed, "private", content,
                               "extracted_text")
    content.write_bytes(raw + b" revised extraction")
    recheck = source_capture.capture(export(["private"]), processed, "private", content,
                                    "extracted_text")
    assert recheck["private"]["review_state"] == "pending_review"
    assert recheck["private"]["snapshot_sha256"] != processed["private"]["snapshot_sha256"]
    assert recheck["private"]["previous_processed_review"] == processed["private"]
    repeated = source_capture.capture(export(["private"]), recheck, "private", content,
                                     "extracted_text")
    assert repeated["private"]["previous_processed_review"] == processed["private"]
    invalid_history = {"private": {**recheck["private"],
                                   "previous_processed_review": {"review_state": "processed"}}}
    with pytest.raises(InventoryError, match="invalid_previous_processed_review"):
        source_capture.capture(export(["private"]), invalid_history, "private", content,
                               "extracted_text")
    assert processed["private"]["review_state"] == "processed"
    assert source_capture.capture(export(["private"]), processed, "private", content,
                                  "file_bytes")["private"]["review_state"] == "pending_review"
    content.write_bytes(raw)
    conflicted = {"private": {"revision": updated["private"]["revision"],
                              "review_state": "conflict",
                              "reason": "Transcript and slides disagree",
                              "locator": "slide 4", "related_source_ids": []}}
    with pytest.raises(InventoryError, match="source_revision_has_unresolved_conflict"):
        source_capture.capture(export(["private"]), conflicted, "private", content,
                               "extracted_text")
    captured_conflict = source_capture.capture(
        export(["private"]), conflicted, "private", content,
        "extracted_text", capture_conflict_evidence=True)
    assert captured_conflict["private"]["review_state"] == "conflict"
    assert captured_conflict["private"]["reason"] == conflicted["private"]["reason"]
    assert captured_conflict["private"]["snapshot_sha256"] == hashlib.sha256(raw).hexdigest()
    assert processing_status(source_capture._snapshot(export(["private"])),
                             captured_conflict)["private"] == "conflict_review"
    with pytest.raises(InventoryError, match="conflict_capture_already_recorded"):
        source_capture.capture(export(["private"]), captured_conflict, "private", content,
                               "extracted_text", capture_conflict_evidence=True)
    content.write_bytes(raw + b" different")
    with pytest.raises(InventoryError, match="conflict_capture_changed"):
        source_capture.capture(export(["private"]), captured_conflict, "private", content,
                               "extracted_text", capture_conflict_evidence=True)
    content.write_bytes(raw)
    with pytest.raises(InventoryError, match="current_conflict_required_for_capture"):
        source_capture.capture(export(["private"]), processed, "private", content,
                               "extracted_text", capture_conflict_evidence=True)
    newer = export(["private"])
    newer["folders"]["root"][0]["children"][0]["modified_time"] = "2026-09-26T00:00:00Z"
    newer_capture = source_capture.capture(newer, processed, "private", content,
                                          "extracted_text")["private"]
    assert newer_capture["review_state"] == "pending_review"
    assert newer_capture["previous_processed_review"] == processed["private"]
    reviewed_newer = {**newer_capture, "review_state": "processed", **REVIEW_EVIDENCE}
    newest = export(["private"])
    newest["folders"]["root"][0]["children"][0]["modified_time"] = "2026-09-27T00:00:00Z"
    newest_capture = source_capture.capture(newest, {"private": reviewed_newer},
                                            "private", content, "extracted_text")["private"]
    assert newest_capture["previous_processed_review"] == reviewed_newer
    assert newest_capture["previous_processed_review"]["previous_processed_review"] == processed["private"]
    from_conflict = source_capture.capture(newer, conflicted, "private", content,
                                           "extracted_text")["private"]
    assert from_conflict["review_state"] == "pending_review"
    assert from_conflict["conflict_hold"]["reason"] == "Transcript and slides disagree"
    with_prior_review = {"private": {**conflicted["private"],
                                      "previous_processed_review": processed["private"]}}
    retained = source_capture.capture(newer, with_prior_review, "private", content,
                                      "extracted_text")["private"]
    assert retained["previous_processed_review"] == processed["private"]
    assert source_capture.capture(newer, {"private": from_conflict}, "private", content,
                                  "extracted_text")["private"]["conflict_hold"] == from_conflict["conflict_hold"]
    with pytest.raises(InventoryError, match="invalid_conflict_hold"):
        source_capture.capture(newer, {"private": {**conflicted["private"], "locator": None}},
                               "private", content, "extracted_text")
    with pytest.raises(InventoryError, match="source_not_in_current_inventory"):
        source_capture.capture(export(["private"]), {}, "absent", content, "extracted_text")
    content.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        source_capture.capture(export(["private"]), {}, "private", content, "extracted_text")


def test_extraction_profile_is_private_and_validated(tmp_path):
    content = tmp_path / "private.txt"
    content.write_text("Учебный текст", encoding="utf-8")
    inventory = export(["private"])
    record = source_capture.capture(inventory, {}, "private", content,
                                    "extracted_text", extraction_profile="docs-paragraphs-v1")
    assert record["private"]["extraction_profile"] == "docs-paragraphs-v1"
    assert processing_status(source_capture._snapshot(inventory), record)["private"] == "pending_review"
    for profile in ("", "Docs v1", "../unsafe", 123):
        with pytest.raises(InventoryError, match="invalid_extraction_profile"):
            source_capture.capture(inventory, {}, "private", content,
                                   "extracted_text", extraction_profile=profile)
    with pytest.raises(InventoryError, match="invalid_extraction_profile"):
        source_capture.capture(inventory, {}, "private", content,
                               "file_bytes", extraction_profile="docs-paragraphs-v1")
    altered = {"private": {**record["private"], "extraction_profile": "Docs v1"}}
    with pytest.raises(InventoryError, match="invalid_extraction_profile"):
        processing_status(source_capture._snapshot(inventory), altered)


def test_capture_cli_writes_only_new_ignored_private_record(tmp_path, monkeypatch, capsys):
    (tmp_path / "data").mkdir()
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    current = tmp_path / "data/current.json"
    current.write_text(json.dumps(export(["private"])), encoding="utf-8")
    content = tmp_path / "data/content.txt"
    content.write_text("Проверяемый снимок", encoding="utf-8")
    target = tmp_path / "data/processed.json"
    monkeypatch.setattr(source_capture, "REPO_ROOT", tmp_path)
    args = ["--current", str(current), "--source-id", "private", "--content", str(content),
            "--snapshot-kind", "extracted_text", "--output", str(target)]
    assert source_capture.main(args) == 0
    output = capsys.readouterr()
    assert output.out.strip() == "SOURCE_CAPTURE_PENDING_REVIEW"
    assert "private" not in output.out
    assert json.loads(target.read_text(encoding="utf-8"))["private"]["review_state"] == "pending_review"
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    before = target.read_bytes()
    assert source_capture.main(args) == 1
    assert target.read_bytes() == before
    outside = tmp_path / "unsafe.json"
    assert source_capture.main([*args[:-1], str(outside)]) == 1
    assert not outside.exists()


def test_batch_capture_is_atomic_and_keeps_private_paths(tmp_path, monkeypatch, capsys):
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    current = data / "current.json"
    current.write_text(json.dumps(export(["first", "second"])), encoding="utf-8")
    (data / "first.txt").write_text("Первый текст", encoding="utf-8")
    (data / "second.txt").write_text("Второй текст", encoding="utf-8")
    manifest = data / "batch.json"
    output = data / "processed.json"
    monkeypatch.setattr(source_batch_capture, "REPO_ROOT", tmp_path)
    entries = [
        {"source_id": source, "content": f"data/{source}.txt",
         "snapshot_kind": "extracted_text",
         **({"extraction_profile": "docs-paragraphs-v1"} if source == "first" else {})}
        for source in ("first", "second")
    ]
    args = ["--current", str(current), "--manifest", str(manifest), "--output", str(output)]
    manifest.write_text(json.dumps({"schema_version": 1, "sources": entries}), encoding="utf-8")
    assert source_batch_capture.main(args) == 0
    assert capsys.readouterr().out.strip() == "SOURCE_BATCH_CAPTURE_PENDING_REVIEW"
    records = json.loads(output.read_text(encoding="utf-8"))
    assert set(records) == {"first", "second"}
    assert {item["review_state"] for item in records.values()} == {"pending_review"}
    assert records["first"]["extraction_profile"] == "docs-paragraphs-v1"
    assert "extraction_profile" not in records["second"]
    if os.name == "posix":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600

    output.unlink()
    manifest.write_text(json.dumps({"schema_version": 1, "sources": [entries[0],
        {**entries[1], "content": "../outside.txt"}]}), encoding="utf-8")
    assert source_batch_capture.main(args) == 1
    assert not output.exists()
    manifest.write_text(json.dumps({"schema_version": 1, "sources": [
        {**entries[0], "extraction_profile": None}]}), encoding="utf-8")
    assert source_batch_capture.main(args) == 1
    assert not output.exists()
