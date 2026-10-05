"""Signed private sources remain traceable without adding them to public items."""
from copy import deepcopy
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.content_publication import PublicationPolicy, fingerprint
from app.publication_certificate import certificate_payload, key_id
from app.source_inventory import InventoryError
from scripts.source_inventory_report import private_dossier_reviews


def signed_document(tmp_path):
    root = tmp_path / "repo"
    directory = root / "content/literature"
    directory.mkdir(parents=True)
    item = {"id": "book", "status": "approved", "title": "Book", "source": {"citation": "Author. Book."}}
    (directory / "discipline.json").write_text(json.dumps([item]), encoding="utf-8")
    review = {"decision": "approved", "sources": [{"source_id": "private_source", "modified_time": "2026-10-01T00:00:00Z", "snapshot_sha256": "a" * 64}]}
    dossier = {"schema_version": 1, "kind": "literature", "item_id": "book", "publication_review": review}
    key = Ed25519PrivateKey.generate()
    certificate = {"schema_version": 1, "item_sha256": fingerprint(item), "review_sha256": fingerprint(dossier), "key_id": key_id(key.public_key())}
    import base64
    certificate["signature"] = base64.b64encode(key.sign(certificate_payload("literature", "book", certificate["item_sha256"], certificate["review_sha256"], certificate["key_id"]))).decode("ascii")
    policy = PublicationPolicy({}, {}, {}, certificates={"literature:book": certificate}, certificate_key=key.public_key())
    return root, {"schema_version": 1, "dossiers": [dossier]}, policy


def test_private_edges_are_restored_from_exact_signed_dossier(tmp_path):
    root, document, policy = signed_document(tmp_path)
    before = deepcopy(document)
    reviews, quality = private_dossier_reviews(root, document, policy=policy)
    assert reviews["literature:book"]["sources"][0]["source_id"] == "private_source"
    assert quality == {} and document == before
    assert "private_source" not in (root / "content/literature/discipline.json").read_text(encoding="utf-8")


def test_changed_proof_item_signature_or_duplicate_cannot_restore_edges(tmp_path):
    root, document, policy = signed_document(tmp_path)
    changed = deepcopy(document)
    changed["dossiers"][0]["publication_review"]["sources"][0]["source_id"] = "another_source"
    with pytest.raises(InventoryError, match="not_current"):
        private_dossier_reviews(root, changed, policy=policy)
    with pytest.raises(InventoryError, match="not_current"):
        private_dossier_reviews(root, {"schema_version": 1, "dossiers": document["dossiers"] * 2}, policy=policy)
    path = root / "content/literature/discipline.json"
    item = json.loads(path.read_text())[0]
    item["title"] = "Changed"
    path.write_text(json.dumps([item]), encoding="utf-8")
    with pytest.raises(InventoryError, match="not_current"):
        private_dossier_reviews(root, document, policy=policy)
    item["title"] = "Book"
    path.write_text(json.dumps([item]), encoding="utf-8")
    policy.certificates["literature:book"]["signature"] = "invalid"
    # Frozen legacy acceptance must not serve as certificate authentication.
    policy.legacy["literature:book"] = fingerprint(item)
    assert policy.can_publish("literature", item)
    with pytest.raises(InventoryError, match="not_current"):
        private_dossier_reviews(root, document, policy=policy)
