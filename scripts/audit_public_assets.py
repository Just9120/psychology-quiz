"""Fail when a built public client asset contains private Drive provenance.

Use the current ignored Drive inventory for a complete local scan. CI can scan
against the tracked registry, but that smaller set is not a complete privacy
claim for sources kept only in operator storage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.source_inventory import complete_listing, scan

PUBLIC_MARKERS = (b"drive:", b"drive.google.com", b"docs.google.com")
MAX_ASSET_BYTES = 64 * 1024 * 1024


class AssetAuditError(ValueError):
    pass


def known_source_ids(inventory_path: Path | None = None) -> set[str]:
    registry = json.loads((ROOT / "content/source-corpus.json").read_text(encoding="utf-8"))
    ids = {source["id"] for source in registry["sources"]}
    ids.add(registry["corpus_root_id"])
    if inventory_path is not None:
        private_root = (ROOT / "data").resolve(strict=True)
        path = inventory_path.resolve(strict=True)
        if path.parent != private_root or path.suffix != ".json" or path.is_symlink():
            raise AssetAuditError("private_inventory_path_required")
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 1 or not isinstance(document.get("folders"), dict):
            raise AssetAuditError("invalid_private_inventory")
        snapshot = scan(document.get("root_id"), {
            folder: complete_listing(pages)
            for folder, pages in document["folders"].items()
        })
        ids.update(snapshot["files"])
        ids.update(document["folders"])
    return {source_id for source_id in ids if len(source_id) >= 20}


def audit_assets(directories: list[Path], source_ids: set[str]) -> tuple[int, int]:
    if not directories:
        raise AssetAuditError("asset_directory_required")
    needles = [source_id.encode("ascii") for source_id in source_ids]
    file_count = byte_count = 0
    for directory in directories:
        if not directory.is_dir() or directory.is_symlink():
            raise AssetAuditError("built_asset_directory_required")
        files = sorted(directory.rglob("*"))
        if not files:
            raise AssetAuditError("empty_asset_directory")
        for path in files:
            relative_name = path.relative_to(directory).as_posix().encode("utf-8")
            if any(marker in relative_name.lower() for marker in PUBLIC_MARKERS) or any(
                needle in relative_name for needle in needles
            ):
                raise AssetAuditError("private_provenance_in_public_asset")
            if path.is_symlink():
                raise AssetAuditError("symlink_in_public_assets")
            if path.is_dir():
                continue
            if not path.is_file() or path.stat().st_size > MAX_ASSET_BYTES:
                raise AssetAuditError("invalid_public_asset")
            payload = path.read_bytes()
            lowered = payload.lower()
            if any(marker in lowered for marker in PUBLIC_MARKERS) or any(
                needle in payload for needle in needles
            ):
                # Even an asset name could contain a private ID. Return only
                # the category; operator diagnosis stays in private storage.
                raise AssetAuditError("private_provenance_in_public_asset")
            file_count += 1
            byte_count += len(payload)
    if not file_count:
        raise AssetAuditError("empty_asset_directory")
    return file_count, byte_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-dir", type=Path, action="append", required=True)
    parser.add_argument("--private-inventory", type=Path)
    args = parser.parse_args()
    try:
        ids = known_source_ids(args.private_inventory)
        files, size = audit_assets(args.asset_dir, ids)
    except (AssetAuditError, OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        # Imported validators can include the offending private ID in their
        # error text. Keep CLI output deliberately generic.
        raise SystemExit(f"PUBLIC_ASSET_AUDIT_STOP: {type(error).__name__}") from None
    print(f"PUBLIC_ASSET_AUDIT_OK files={files} bytes={size} known_sources={len(ids)}")


if __name__ == "__main__":
    main()
