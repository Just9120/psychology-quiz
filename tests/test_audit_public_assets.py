from pathlib import Path

import pytest

from scripts.audit_public_assets import AssetAuditError, audit_assets


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
