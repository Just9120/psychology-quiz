"""Private Vault export preserves owner files and rejects stale sources."""
import hashlib
from pathlib import Path

import pytest

from scripts.obsidian_vault import VaultError, render, write_vault


SOURCE = "1" * 32
REVISION = ["2026-09-29T12:00:00Z", "Учебная лекция", "application/pdf"]
DIGEST = hashlib.sha256(b"reviewed source").hexdigest()


def evidence():
    inventory = {"files": {SOURCE: {"modified_time": REVISION[0], "title": REVISION[1],
                                      "mime_type": REVISION[2]}}}
    processing = {SOURCE: {"revision": REVISION, "review_state": "processed",
                           "snapshot_kind": "file_bytes", "snapshot_sha256": DIGEST,
                           "reviewer": "editor", "review_note": "Exact passage checked",
                           "reviewed_at": "2026-09-29T12:30:00Z"}}
    return inventory, processing


def note(note_id="attention", body="Проверенное положение.", links=()):
    return {"id": note_id, "title": "Внимание", "body": body,
            "source_id": SOURCE, "source_revision": REVISION,
            "source_sha256": DIGEST, "source_locator": "стр. 2, абзац 1",
            "reviewer": "editor", "reviewed_at": "2026-09-29T12:40:00Z",
            "links": list(links), "question_ids": ["m1_gp_001"]}


def test_private_export_updates_generated_notes_but_preserves_personal_files(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    personal = vault / "personal"
    personal.mkdir()
    (personal / "my-note.md").write_text("Не менять", encoding="utf-8")
    inventory, processing = evidence()
    first = render({"schema_version": 1, "notes": [note()]}, inventory, processing)
    assert write_vault(vault, first) == {"notes": 1, "generated_files": 2}
    assert "[[attention|Внимание]]" in (vault / "generated/index.md").read_text(encoding="utf-8")
    assert "m1_gp_001" in (vault / "generated/attention.md").read_text(encoding="utf-8")
    second = render({"schema_version": 1, "notes": [note(body="Новая проверенная редакция.")]},
                    inventory, processing)
    write_vault(vault, second)
    assert "Новая проверенная редакция." in (vault / "generated/attention.md").read_text(encoding="utf-8")
    assert (personal / "my-note.md").read_text(encoding="utf-8") == "Не менять"
    assert not (vault / ".vault-generated-backup").exists()


def test_reject_stale_or_conflicted_source_and_missing_note_link():
    inventory, processing = evidence()
    manifest = {"schema_version": 1, "notes": [note(links=["missing"])]}
    with pytest.raises(VaultError, match="missing_note_link"):
        render(manifest, inventory, processing)
    manifest["notes"][0]["links"] = []
    manifest["notes"][0]["body"] = "Смотрите [[missing]]."
    with pytest.raises(VaultError, match="missing_body_wikilink"):
        render(manifest, inventory, processing)
    manifest["notes"][0]["body"] = "Проверенное положение."
    processing[SOURCE]["review_state"] = "pending_review"
    with pytest.raises(VaultError, match="source_not_current_reviewed"):
        render(manifest, inventory, processing)
    processing[SOURCE]["review_state"] = "processed"
    processing[SOURCE]["revision"] = ["2026-09-30T12:00:00Z", *REVISION[1:]]
    with pytest.raises(VaultError, match="source_not_current_reviewed"):
        render(manifest, inventory, processing)


def test_owner_edits_to_generated_file_are_not_overwritten(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    inventory, processing = evidence()
    files = render({"schema_version": 1, "notes": [note()]}, inventory, processing)
    write_vault(vault, files)
    path = vault / "generated/attention.md"
    path.write_text("Личная правка", encoding="utf-8")
    with pytest.raises(VaultError, match="generated_note_changed_by_owner"):
        write_vault(vault, files)
    assert path.read_text(encoding="utf-8") == "Личная правка"
