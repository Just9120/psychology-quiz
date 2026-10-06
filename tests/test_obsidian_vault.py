"""Private Vault export preserves owner files and rejects stale sources."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

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
                           "source_kind": "learning_material",
                           "source_kind_review": {"reviewer": "editor", "note": "Learning material read",
                                                  "reviewed_at": "2026-09-29T12:30:00Z"},
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
    processing[SOURCE]["search_ranges"] = [[10, 20]]
    with pytest.raises(VaultError, match="unreviewed_source_locator"):
        render(manifest, inventory, processing)
    processing[SOURCE].pop("search_ranges")
    processing[SOURCE]["review_state"] = "pending_review"
    processing[SOURCE].pop("source_kind")
    processing[SOURCE].pop("source_kind_review")
    with pytest.raises(VaultError, match="source_not_current_reviewed"):
        render(manifest, inventory, processing)
    processing[SOURCE] = evidence()[1][SOURCE]
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


def test_note_links_must_resolve_to_current_content():
    inventory, processing = evidence()
    for field in ("question_ids", "term_ids", "literature_ids"):
        item = note()
        item[field] = ["absent-content-id"]
        with pytest.raises(VaultError, match="unresolved_" + field):
            render({"schema_version": 1, "notes": [item]}, inventory, processing)


def test_another_checkout_of_this_repository_is_not_a_private_vault(tmp_path, monkeypatch):
    from scripts import obsidian_vault
    vault = tmp_path / "other-checkout"
    vault.mkdir()
    common = tmp_path / "git-common"
    common.mkdir()
    monkeypatch.setattr(obsidian_vault, "_git_common_directory", lambda directory: common)
    with pytest.raises(VaultError, match="separate_private_vault_required"):
        write_vault(vault, {"index.md": b"reviewed"})
    assert not (vault / "generated").exists()


def test_unknown_generated_state_version_preserves_existing_files(tmp_path):
    import json
    from scripts.obsidian_vault import STATE
    vault = tmp_path / "vault"
    vault.mkdir()
    inventory, processing = evidence()
    files = render({"schema_version": 1, "notes": [note()]}, inventory, processing)
    write_vault(vault, files)
    state = vault / "generated" / STATE
    data = json.loads(state.read_text(encoding="utf-8"))
    data["schema_version"] = 99
    state.write_text(json.dumps(data), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in (vault / "generated").iterdir()}
    with pytest.raises(VaultError, match="invalid_generated_state"):
        write_vault(vault, files)
    assert {p.name: p.read_bytes() for p in (vault / "generated").iterdir()} == before


def test_repo_inputs_must_be_ignored_and_never_tracked(tmp_path, monkeypatch):
    import subprocess
    from scripts import obsidian_vault
    subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
    monkeypatch.setattr(obsidian_vault, "ROOT", tmp_path)
    untracked = tmp_path / "untracked.json"
    untracked.write_text("{}", encoding="utf-8")
    with pytest.raises(VaultError, match="ignored_private_input_required"):
        obsidian_vault._private_input(untracked)
    subprocess.run(["git", "-C", str(tmp_path), "add", "untracked.json"], capture_output=True, check=True)
    with pytest.raises(VaultError, match="tracked_private_input_forbidden"):
        obsidian_vault._private_input(untracked)
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    private = tmp_path / "data" / "notes.json"
    private.write_text('{"schema_version": 1}', encoding="utf-8")
    assert obsidian_vault._private_input(private) == {"schema_version": 1}


def test_partial_update_preserves_prior_note_ids_and_personal_wikilinks(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    personal = vault / "personal.md"
    personal.write_text("Моя связь: [[generated/perception]].", encoding="utf-8")
    inventory, processing = evidence()
    initial = render({"schema_version": 1, "notes": [note(), note("perception", body="Проверенная заметка о восприятии.")]}, inventory, processing)
    write_vault(vault, initial)
    preserved = (vault / "generated/perception.md").read_bytes()
    update = render({"schema_version": 1, "notes": [note(body="Новая редакция внимания.")]}, inventory, processing)
    assert write_vault(vault, update) == {"notes": 2, "generated_files": 3}
    assert (vault / "generated/perception.md").read_bytes() == preserved
    assert personal.read_text(encoding="utf-8") == "Моя связь: [[generated/perception]]."
    index = (vault / "generated/index.md").read_bytes()
    assert b"[[perception]]" in index and "источники не проверялись".encode() in index
    before = {p.name: p.read_bytes() for p in (vault / "generated").iterdir()}
    write_vault(vault, update)
    assert {p.name: p.read_bytes() for p in (vault / "generated").iterdir()} == before
    assert set(update) == {"attention.md", "index.md"}


def test_bibliography_and_unclassified_capture_are_not_knowledge_sources():
    inventory, processing = evidence()
    processing[SOURCE]["source_kind"] = "bibliography"
    with pytest.raises(VaultError, match="learning_source_required"):
        render({"schema_version": 1, "notes": [note()]}, inventory, processing)
    processing[SOURCE].pop("source_kind")
    processing[SOURCE].pop("source_kind_review")
    with pytest.raises(VaultError, match="learning_source_required"):
        render({"schema_version": 1, "notes": [note()]}, inventory, processing)


@pytest.mark.parametrize("metadata,allowed", [
    ({"private": True, "archived": False, "permissions": {"push": True}}, True),
    ({"private": False, "archived": False, "permissions": {"push": True}}, False),
    ({"private": True, "archived": True, "permissions": {"push": True}}, False),
    ({"private": True, "archived": False, "permissions": {"push": False}}, False),
])
def test_unified_repository_export_requires_authenticated_private_target(tmp_path, monkeypatch, metadata, allowed):
    from scripts import obsidian_vault as vault_module
    monkeypatch.setattr(vault_module, "ROOT", tmp_path)
    monkeypatch.setattr(vault_module, "_git_common_directory", lambda _: tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    personal = vault / "personal.md"
    personal.write_text("Мои заметки.", encoding="utf-8")
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "git":
            return SimpleNamespace(stdout="https://github.com/Just9120/psychology-quiz.git\n")
        assert command == ["gh", "api", "--hostname", "github.com", "repos/Just9120/psychology-quiz"]
        return SimpleNamespace(stdout=json.dumps({"full_name": "Just9120/psychology-quiz", **metadata}))
    monkeypatch.setattr(vault_module.subprocess, "run", run)
    files = {"index.md": b"# Private index\n"}
    if allowed:
        write_vault(vault, files, repository_vault=True)
        assert (vault / "generated/index.md").read_bytes() == files["index.md"]
    else:
        with pytest.raises(VaultError, match="private_repository_required"):
            write_vault(vault, files, repository_vault=True)
        assert not (vault / "generated").exists()
    assert personal.read_text(encoding="utf-8") == "Мои заметки."
    assert len(calls) == 2


def test_unified_vault_refuses_unknown_visibility_and_other_destinations(tmp_path, monkeypatch):
    from scripts import obsidian_vault as vault_module
    monkeypatch.setattr(vault_module, "ROOT", tmp_path)
    monkeypatch.setattr(vault_module, "_git_common_directory", lambda _: tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir()
    def unavailable(command, **kwargs):
        raise FileNotFoundError("synthetic unavailable gh")
    monkeypatch.setattr(vault_module.subprocess, "run", unavailable)
    with pytest.raises(VaultError, match="private_repository_verification_unavailable"):
        write_vault(vault, {"index.md": b"# Private\n"}, repository_vault=True)
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(VaultError, match="repository_vault_path_required"):
        write_vault(other, {"index.md": b"# Private\n"}, repository_vault=True)
    assert not (vault / "generated").exists() and not (other / "generated").exists()
