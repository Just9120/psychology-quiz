from pathlib import Path

import pytest

from scripts.audit_public_assets import AssetAuditError, audit_approved_content, audit_assets


def test_public_asset_audit_rejects_private_id_without_echoing_it(tmp_path: Path):
    source_id = "private_drive_source_0123456789"
    assets = tmp_path / "dist"
    assets.mkdir()
    (assets / "index.html").write_text("<html>Public quiz</html>", encoding="utf-8")
    assert audit_assets([assets], {source_id}) == (1, 24)

    (assets / "app.js").write_text(f"const source = '{source_id}'", encoding="utf-8")
    with pytest.raises(AssetAuditError, match="private_provenance_in_public_asset") as caught:
        audit_assets([assets], {source_id})
    assert source_id not in str(caught.value)

    (assets / "app.js").write_text("const source = 'https://docs.google.com/document/d/unknown'", encoding="utf-8")
    with pytest.raises(AssetAuditError, match="private_provenance_in_public_asset"):
        audit_assets([assets], set())


def test_public_asset_audit_rejects_private_id_in_nested_name(tmp_path: Path):
    source_id = "private_drive_source_0123456789"
    assets = tmp_path / "dist"
    assets.mkdir()
    (assets / "index.html").write_text("Public quiz", encoding="utf-8")
    nested = assets / f"cached-{source_id}"
    nested.mkdir()
    (nested / "empty.css").write_text("body{}", encoding="utf-8")

    with pytest.raises(AssetAuditError, match="private_provenance_in_public_asset") as caught:
        audit_assets([assets], {source_id})
    assert source_id not in str(caught.value)


def test_approved_content_audit_checks_display_text_with_private_inventory(tmp_path: Path):
    source_id = "private_drive_source_0123456789"
    root = tmp_path / "content"
    for kind in ("questions", "glossary", "literature"):
        (root / kind).mkdir(parents=True)
        (root / kind / "items.json").write_text("[]", encoding="utf-8")
    questions = root / "questions" / "items.json"
    questions.write_text(
        '[{"status":"approved","question":"What happened?",'
        f'"source_ref":"drive:{source_id}"}}]', encoding="utf-8")
    assert audit_approved_content({source_id}, root) == 1

    questions.write_text(
        '[{"status":"approved",'
        f'"question":"See {source_id} for the answer"}}]', encoding="utf-8")
    with pytest.raises(AssetAuditError, match="private_provenance_in_public_content") as caught:
        audit_approved_content({source_id}, root)
    assert source_id not in str(caught.value)
