import hashlib
import json
import os
import stat
import subprocess

import pytest

from app.source_inventory import InventoryError, processing_status
from scripts import source_capture
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
    processed = {"private": {**updated["private"], "review_state": "processed"}}
    with pytest.raises(InventoryError, match="source_revision_already_processed"):
        source_capture.capture(export(["private"]), processed, "private", content,
                               "extracted_text")
    conflicted = {"private": {"revision": updated["private"]["revision"],
                              "review_state": "conflict",
                              "reason": "Transcript and slides disagree"}}
    with pytest.raises(InventoryError, match="source_revision_has_unresolved_conflict"):
        source_capture.capture(export(["private"]), conflicted, "private", content,
                               "extracted_text")
    newer = export(["private"])
    newer["folders"]["root"][0]["children"][0]["modified_time"] = "2026-09-26T00:00:00Z"
    assert source_capture.capture(newer, processed, "private", content,
                                  "extracted_text")["private"]["review_state"] == "pending_review"
    assert source_capture.capture(newer, conflicted, "private", content,
                                  "extracted_text")["private"]["review_state"] == "pending_review"
    with pytest.raises(InventoryError, match="source_not_in_current_inventory"):
        source_capture.capture(export(["private"]), {}, "absent", content, "extracted_text")
    content.write_bytes(b"\xff")
    with pytest.raises(UnicodeDecodeError):
        source_capture.capture(export(["private"]), {}, "private", content, "extracted_text")


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
