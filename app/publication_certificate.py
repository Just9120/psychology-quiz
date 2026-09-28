"""Verify public approvals without putting new private Drive references in Git.

The signer checks the complete review dossier in private operator storage.
Only its digest and an Ed25519 signature over the exact public item are shipped.
This verifies who approved a revision, not the truth of its source claims.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


HEX64 = re.compile(r"^[0-9a-f]{64}$")


def key_id(public_key: Ed25519PublicKey) -> str:
    return hashlib.sha256(public_key.public_bytes_raw()).hexdigest()


def certificate_payload(kind: str, item_id: str, item_sha256: str,
                        review_sha256: str, signer_key_id: str) -> bytes:
    return json.dumps({
        "domain": "psychology-atlas-publication-v1",
        "kind": kind,
        "item_id": item_id,
        "item_sha256": item_sha256,
        "review_sha256": review_sha256,
        "key_id": signer_key_id,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def certificate_error(kind: str, item: dict, certificate: object,
                      public_key: Ed25519PublicKey | None, *, item_sha256: str) -> str | None:
    if public_key is None:
        return "publication_certificate_key_required"
    if not isinstance(certificate, dict) or set(certificate) != {
            "schema_version", "item_sha256", "review_sha256", "key_id", "signature"}:
        return "invalid_publication_certificate"
    if certificate["schema_version"] != 1 or type(certificate["schema_version"]) is not int:
        return "invalid_publication_certificate"
    if (not isinstance(item.get("id"), str) or not item["id"]
            or not isinstance(certificate["item_sha256"], str)
            or certificate["item_sha256"] != item_sha256
            or not isinstance(certificate["review_sha256"], str)
            or HEX64.fullmatch(certificate["review_sha256"]) is None
            or certificate["key_id"] != key_id(public_key)
            or not isinstance(certificate["signature"], str)):
        return "invalid_publication_certificate"
    try:
        signature = base64.b64decode(certificate["signature"], validate=True)
        if len(signature) != 64:
            return "invalid_publication_certificate"
        public_key.verify(signature, certificate_payload(
            kind, item["id"], item_sha256, certificate["review_sha256"], certificate["key_id"]))
    except (InvalidSignature, ValueError, binascii.Error):
        return "invalid_publication_certificate"
    return None
