"""Render reviewed private notes into an owner-only Obsidian Vault.

This command never contacts Drive. Repository output requires an authenticated
GitHub visibility check; local staging remains outside the application repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.source_inventory import (InventoryError, complete_listing, processing_status, scan,
                                  unresolved_related_conflicts, valid_review_timestamp)


NOTE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}\Z")
CONTENT_ID = re.compile(r"[A-Za-z0-9:_-]{1,120}\Z")
WIKI_LINK = re.compile(r"\[\[([^\]]+)\]\]")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SOURCE_ID = re.compile(r"[A-Za-z0-9_-]{20,}\Z")
GENERATED = "generated"
STATE = ".psychology-atlas-generated.json"


class VaultError(ValueError):
    pass


def _private_input(path: Path) -> dict:
    real = path.resolve(strict=True)
    if path.is_symlink() or not real.is_file() or real.stat().st_size > 20_000_000:
        raise VaultError("private_regular_json_required")
    if real.is_relative_to(ROOT):
        relative = real.relative_to(ROOT).as_posix()
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", relative],
                                 cwd=ROOT, capture_output=True, check=False)
        if tracked.returncode == 0:
            raise VaultError("tracked_private_input_forbidden")
        if tracked.returncode != 1:
            raise VaultError("private_input_git_check_failed")
        ignored = subprocess.run(["git", "check-ignore", "--quiet", "--", relative],
                                 cwd=ROOT, capture_output=True, check=False)
        if ignored.returncode != 0:
            raise VaultError("ignored_private_input_required")
    try:
        value = json.loads(real.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise VaultError("invalid_private_json") from error
    if not isinstance(value, dict):
        raise VaultError("invalid_private_json")
    return value


def _required_text(item: dict, key: str, limit: int) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise VaultError(f"invalid_{key}")
    return value.strip()


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _content_ids() -> dict[str, set[str]]:
    result = {}
    for field, directory in (("question_ids", "questions"), ("term_ids", "glossary"),
                             ("literature_ids", "literature")):
        ids = set()
        for path in sorted((ROOT / "content" / directory).rglob("*.json")):
            entries = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                raise VaultError("invalid_content_registry")
            ids.update(item["id"] for item in entries if isinstance(item, dict)
                       and isinstance(item.get("id"), str))
        result[field] = ids
    return result


def _git_common_directory(directory: Path) -> Path | None:
    result = subprocess.run(["git", "-C", str(directory), "rev-parse", "--path-format=absolute",
                             "--git-common-dir"], capture_output=True, text=True, encoding="utf-8", timeout=10)
    if result.returncode == 128:
        return None
    if result.returncode or not result.stdout.strip():
        raise VaultError("repository_identity_unavailable")
    return Path(result.stdout.strip()).resolve(strict=True)


def render(manifest: dict, inventory: dict, processing: dict) -> dict[str, bytes]:
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("notes"), list):
        raise VaultError("invalid_note_manifest")
    if inventory.get("schema_version") == 1 and isinstance(inventory.get("folders"), dict):
        try:
            inventory = scan(inventory.get("root_id"),
                             {folder: complete_listing(pages)
                              for folder, pages in inventory["folders"].items()})
        except (InventoryError, KeyError, TypeError) as error:
            raise VaultError("invalid_source_evidence") from error
    if not isinstance(inventory.get("files"), dict) or not isinstance(processing, dict):
        raise VaultError("invalid_source_evidence")
    try:
        statuses = processing_status(inventory, processing)
        held = unresolved_related_conflicts(processing)
    except (InventoryError, KeyError, TypeError) as error:
        raise VaultError("invalid_source_evidence") from error
    notes: dict[str, dict] = {}
    for item in manifest["notes"]:
        if not isinstance(item, dict):
            raise VaultError("invalid_note")
        note_id = item.get("id")
        if (not isinstance(note_id, str) or not NOTE_ID.fullmatch(note_id)
                or note_id == "index" or note_id in notes):
            raise VaultError("invalid_or_duplicate_note_id")
        _required_text(item, "title", 160)
        _required_text(item, "body", 20_000)
        source_id = _required_text(item, "source_id", 200)
        if not SOURCE_ID.fullmatch(source_id) or source_id in held:
            raise VaultError("source_not_current_reviewed")
        source = processing.get(source_id)
        revision = item.get("source_revision")
        digest = item.get("source_sha256")
        if (statuses.get(source_id) != "processed" or not isinstance(source, dict)
                or revision != source.get("revision") or digest != source.get("snapshot_sha256")
                or not isinstance(digest, str) or not SHA256.fullmatch(digest)):
            raise VaultError("source_not_current_reviewed")
        if source.get("source_kind") != "learning_material":
            raise VaultError("learning_source_required")
        _required_text(item, "source_locator", 300)
        _required_text(item, "reviewer", 160)
        if any("\n" in item[key] or "\r" in item[key] or "`" in item[key]
               for key in ("source_locator", "reviewer")):
            raise VaultError("invalid_review_metadata")
        reviewed_ranges = source.get("search_ranges")
        if reviewed_ranges:
            match = re.fullmatch(r"(\d+):(\d+)", item["source_locator"])
            if not match or [int(match[1]), int(match[2])] not in reviewed_ranges:
                raise VaultError("unreviewed_source_locator")
        if not valid_review_timestamp(item.get("reviewed_at")):
            raise VaultError("invalid_reviewed_at")
        links = item.get("links", [])
        if not isinstance(links, list) or any(not isinstance(link, str) or not NOTE_ID.fullmatch(link)
                                              for link in links) or len(set(links)) != len(links):
            raise VaultError("invalid_note_links")
        notes[note_id] = item
    if any(link not in notes for item in notes.values() for link in item.get("links", [])):
        raise VaultError("missing_note_link")
    if any(link.split("|", 1)[0] not in notes for item in notes.values()
           for link in WIKI_LINK.findall(item["body"])):
        raise VaultError("missing_body_wikilink")

    content_ids = _content_ids()
    files: dict[str, bytes] = {}
    index = ["# Личная база знаний", "", "Сгенерированные заметки из проверенных материалов:", ""]
    for note_id, item in sorted(notes.items()):
        title = item["title"].strip()
        if any(char in title for char in "\r\n[]|"):
            raise VaultError("invalid_note_title")
        index.append(f"- [[{note_id}|{title}]]")
        parts = [f"# {title}", "", item["body"].strip(), "", "## Проверенное основание", "",
                 f"- Source ID: `{item['source_id']}`",
                 f"- Revision: `{json.dumps(item['source_revision'], ensure_ascii=False).replace('`', '\\`')}`",
                 f"- SHA-256: `{item['source_sha256']}`",
                 f"- Locator: {item['source_locator']}",
                 f"- Review: {item['reviewer']} · {item['reviewed_at']}"]
        if item.get("links"):
            parts.extend(["", "## Связанные заметки", ""])
            parts.extend(f"- [[{link}]]" for link in item["links"])
        for key, label in (("question_ids", "Вопросы"), ("term_ids", "Термины"),
                           ("literature_ids", "Литература")):
            values = item.get(key, [])
            if not isinstance(values, list) or any(not isinstance(value, str)
                                                 or not CONTENT_ID.fullmatch(value) for value in values):
                raise VaultError(f"invalid_{key}")
            if any(value not in content_ids[key] for value in values):
                raise VaultError(f"unresolved_{key}")
            if values:
                parts.extend(["", f"## {label}", ""])
                parts.extend(f"- `{value}`" for value in values)
        files[f"{note_id}.md"] = ("\n".join(parts) + "\n").encode("utf-8")
    files["index.md"] = ("\n".join(index) + "\n").encode("utf-8")
    return files


def _remove_owned_directory(path: Path, target: Path) -> None:
    # Recursive cleanup is limited to this export's verified direct children.
    if (path.is_symlink() or not path.is_dir()
            or path.resolve(strict=True).parent != target
            or not (path.name == ".vault-generated-backup" or path.name.startswith(".vault-stage-"))):
        raise VaultError("unsafe_vault_cleanup_target")
    shutil.rmtree(path)


def _verify_repository_vault(target: Path, *, published_content: bool = False) -> None:
    """Verify target and access; private manifests still require private Git."""
    if target != ROOT.resolve() / "vault":
        raise VaultError("repository_vault_path_required")
    try:
        remote = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=ROOT,
                                capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        if remote not in {"https://github.com/Just9120/psychology-quiz.git",
                          "https://github.com/Just9120/psychology-quiz",
                          "git@github.com:Just9120/psychology-quiz.git"}:
            raise VaultError("repository_identity_mismatch")
        response = subprocess.run(["gh", "api", "--hostname", "github.com", "repos/Just9120/psychology-quiz"], cwd=ROOT,
                                  capture_output=True, text=True, timeout=15, check=True)
        metadata = json.loads(response.stdout)
        if (metadata.get("full_name") != "Just9120/psychology-quiz"
                or type(metadata.get("private")) is not bool
                or (not published_content and metadata.get("private") is not True)
                or metadata.get("archived") is not False
                or metadata.get("permissions", {}).get("push") is not True):
            raise VaultError("private_repository_required")
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError) as error:
        if isinstance(error, VaultError):
            raise
        raise VaultError("private_repository_verification_unavailable") from None


def write_vault(vault: Path, files: dict[str, bytes], *, repository_vault: bool = False,
                published_content: bool = False) -> dict:
    if (not isinstance(files, dict) or "index.md" not in files
            or any(not isinstance(content, bytes) or not content for content in files.values())):
        raise VaultError("generated_files_required")
    files = dict(files)
    if published_content:
        from scripts.obsidian_catalogue import render_published
        if files != render_published()[0]:
            raise VaultError("published_catalogue_required")
    target = vault.resolve(strict=True)
    if not target.is_dir() or vault.is_symlink():
        raise VaultError("separate_private_vault_required")
    repository = _git_common_directory(ROOT)
    if repository_vault:
        _verify_repository_vault(target, published_content=published_content)
    elif target.is_relative_to(ROOT) or (repository is not None and _git_common_directory(target) == repository):
        raise VaultError("separate_private_vault_required")
    generated = target / GENERATED
    if generated.is_symlink():
        raise VaultError("generated_symlink_forbidden")
    previous: dict[str, str] = {}
    if generated.exists():
        state_path = generated / STATE
        if not generated.is_dir() or not state_path.is_file() or state_path.is_symlink():
            raise VaultError("unowned_generated_directory")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("schema_version") != 1:
            raise VaultError("invalid_generated_state")
        previous = state.get("files")
        if not isinstance(previous, dict) or any(not NOTE_ID.fullmatch(name.removesuffix(".md"))
                or not name.endswith(".md") or not isinstance(digest, str) or not SHA256.fullmatch(digest)
                for name, digest in previous.items()):
            raise VaultError("invalid_generated_state")
        actual = {p.name for p in generated.iterdir()}
        if actual != set(previous) | {STATE}:
            raise VaultError("unowned_generated_file")
        for name, digest in previous.items():
            path = generated / name
            if not path.is_file() or path.is_symlink() or _hash(path.read_bytes()) != digest:
                raise VaultError("generated_note_changed_by_owner")
    # An incremental manifest is not permission to remove previous note IDs.
    # Preserve their bytes and make the older review scope explicit in the index.
    retained = {name: (generated / name).read_bytes() for name in previous
                if name != "index.md" and name not in files}
    if published_content and retained:
        from scripts.obsidian_catalogue import RETIRED_NOTE
        # Keep IDs, but never republish withdrawn editions or private manifests.
        if any(b"source id:" in data.lower() or b"drive:" in data.lower()
               for data in retained.values()):
            raise VaultError("private_provenance_in_public_vault")
        retained = {name: RETIRED_NOTE for name in retained}
    if retained and not published_content:
        lines = ["", "## Заметки предыдущих пакетов", "",
                 "Эти заметки сохранены для существующих ссылок; в текущем обновлении их источники не проверялись.", ""]
        lines.extend(f"- [[{name[:-3]}]]" for name in sorted(retained))
        files["index.md"] += ("\n".join(lines) + "\n").encode("utf-8")
    files.update(retained)
    if published_content:
        from scripts.audit_public_assets import PUBLIC_MARKERS, known_source_ids
        from scripts.obsidian_catalogue import validate_links
        needles = [value.encode() for value in known_source_ids()]
        if any(any(marker in data.lower() for marker in PUBLIC_MARKERS)
               or any(needle in data for needle in needles) for data in files.values()):
            raise VaultError("private_provenance_in_public_vault")
        validate_links(files)
    staged = Path(tempfile.mkdtemp(prefix=".vault-stage-", dir=target))
    backup = target / ".vault-generated-backup"
    try:
        if backup.exists() or backup.is_symlink():
            raise VaultError("unrecovered_vault_backup")
        for name, content in files.items():
            if not name.endswith(".md") or not NOTE_ID.fullmatch(name[:-3]):
                raise VaultError("invalid_generated_name")
            (staged / name).write_bytes(content)
        state = {"schema_version": 1, "files": {name: _hash(content)
                                                  for name, content in sorted(files.items())}}
        (staged / STATE).write_text(json.dumps(state, sort_keys=True, indent=2) + "\n",
                                   encoding="utf-8", newline="\n")
        if generated.exists():
            os.replace(generated, backup)
        try:
            os.replace(staged, generated)
        except OSError:
            if backup.exists():
                os.replace(backup, generated)
            raise
        if backup.exists():
            _remove_owned_directory(backup, target)
    finally:
        if staged.exists():
            _remove_owned_directory(staged, target)
    return {"notes": len(files) - 1, "generated_files": len(files)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--processing", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--repository-vault", action="store_true",
                        help="Write to this project's vault/ only after authenticated private visibility verification")
    args = parser.parse_args()
    try:
        files = render(_private_input(args.manifest), _private_input(args.inventory),
                       _private_input(args.processing))
        print(json.dumps(write_vault(args.vault, files, repository_vault=args.repository_vault), sort_keys=True))
    except (OSError, VaultError, json.JSONDecodeError) as error:
        raise SystemExit(f"VAULT_STOP: {type(error).__name__}; private details withheld") from None


if __name__ == "__main__":
    main()
