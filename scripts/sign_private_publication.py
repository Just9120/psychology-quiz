"""Create a public approval certificate from a private, fully reviewed dossier.

The dossier stays in ignored data/. The signing key is read from a separate
user-owned secret directory outside the checkout. Output is written to a new
ignored file for explicit review before its certificate enters content/.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNING_KEY_DIR = Path.home() / ".codex" / "secrets" / "psychology-quiz"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.content_publication import KINDS, PUBLIC_DRIVE_LINK, PublicationPolicy, fingerprint
from app.publication_certificate import certificate_payload, key_id
from app.source_inventory import InventoryError, complete_listing, processing_status, scan, unresolved_related_conflicts


class SigningError(ValueError):
    pass


# Owner-approved editions only. A changed question or conflict needs a new review decision.
SCOPED_LECTURE_CLAIMS = {
    "m1_psyf_070": (
        "9d5d84b0422ddcf0df7513051d949727d455861c580742c03f47b94a950fcce3",
        "characters:15300:15970",
    ),
    "m1_psyf_071": (
        "76f30228e4a5d31da54583a58076caf0c68db3b8be9a387946b07cc7c9a70124",
        "characters:14000:15000",
    ),
}
LECTURE14_SOURCE_SHA256 = "2b6c44d6b7e3ba0511b16b4d8d5884e19812e0bbdba5ffbf8a06b14483e45a5c"
LECTURE14_CONFLICT_SHA256 = "28e80d17983ba8747aeed407bd322b5d356e2d1ebce133206db894d5db5551d9"


def _character_ranges(locator: object) -> list[tuple[int, int]]:
    if not isinstance(locator, str):
        raise SigningError("scoped_claim_locator_required")
    parts = [part.strip() for part in locator.split(";")]
    ranges = []
    for part in parts:
        match = re.fullmatch(r"characters:(\d+):(\d+)", part)
        if match is None or int(match[1]) >= int(match[2]):
            raise SigningError("scoped_claim_locator_required")
        ranges.append((int(match[1]), int(match[2])))
    if not ranges or any(left[1] > right[0] for left, right in zip(ranges, ranges[1:])):
        raise SigningError("scoped_claim_locator_required")
    return ranges


def _verify_scoped_claim(dossier: dict, source: dict, record: dict) -> None:
    """Permit only named, reviewed claims outside a source's held passage."""
    claim = dossier.get("scoped_claim_review")
    source_id = source["id"]
    publication_review = dossier.get("publication_review")
    quality_review = dossier.get("quality_review")
    permitted = {
        ("glossary", "dopamine", "1N5lBZzLSmiGqtQpxIHGIz8y630BfYc8hI7kD9Qcc97w"),
        ("questions", "m1_psyf_070", "1IkZqA_0yVgzsavRbChHb4hWVUYE1BmuYgtlNp7I3264"),
        ("questions", "m1_psyf_071", "1IkZqA_0yVgzsavRbChHb4hWVUYE1BmuYgtlNp7I3264"),
    }
    if ((dossier.get("kind"), dossier.get("item_id"), source_id) not in permitted
            or len(dossier.get("sources", [])) != 1
            or not isinstance(claim, dict)
            or not isinstance(publication_review, dict)
            or not isinstance(quality_review, dict)
            or claim.get("source_id") != source_id
            or claim.get("item_sha256") != publication_review.get("item_sha256")
            or claim.get("snapshot_sha256") != record.get("snapshot_sha256")
            or claim.get("conflict_sha256") != fingerprint(record)
            or not isinstance(claim.get("reviewer"), str) or not claim["reviewer"].strip()
            or not isinstance(claim.get("note"), str) or not claim["note"].strip()):
        raise SigningError("scoped_claim_review_required")
    if dossier.get("kind") == "questions":
        expected_item_sha, expected_locator = SCOPED_LECTURE_CLAIMS[dossier["item_id"]]
        if (claim.get("item_sha256") != expected_item_sha
                or claim.get("locator") != expected_locator
                or claim.get("snapshot_sha256") != LECTURE14_SOURCE_SHA256
                or claim.get("conflict_sha256") != LECTURE14_CONFLICT_SHA256):
            raise SigningError("scoped_claim_review_required")
    try:
        reviewed_at = datetime.fromisoformat(claim["reviewed_at"])
        held_at = datetime.fromisoformat(record["reviewed_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise SigningError("scoped_claim_review_required") from error
    if (reviewed_at.tzinfo is None or held_at.tzinfo is None
            or reviewed_at <= held_at):
        raise SigningError("scoped_claim_review_required")
    ranges = _character_ranges(claim.get("locator"))
    held_locator = record.get("locator")
    if (source_id == "1IkZqA_0yVgzsavRbChHb4hWVUYE1BmuYgtlNp7I3264"
            and isinstance(held_locator, str)):
        legacy = re.fullmatch(
            r"extracted_text UTF-8 characters (\d+):(\d+); SHA-256 ([0-9a-f]{64})",
            held_locator,
        )
        if legacy is None or legacy[3] != record.get("snapshot_sha256"):
            raise SigningError("scoped_claim_locator_required")
        held_locator = f"characters:{legacy[1]}:{legacy[2]}"
    held_ranges = _character_ranges(held_locator)
    if any(start < held_end and held_start < end
           for start, end in ranges for held_start, held_end in held_ranges):
        raise SigningError("scoped_claim_overlaps_conflict")
    source_ref = f"drive:{source_id}#{claim['locator']}"
    actual_ref = (dossier.get("source_ref") if dossier.get("kind") == "questions"
                  else dossier.get("source_refs"))
    expected_ref = (source_ref if dossier.get("kind") == "questions"
                    else [source_ref])
    if (actual_ref != expected_ref
            or any(review.get("sources") != [{
                "source_id": source_id,
                "snapshot_sha256": source["snapshot_sha256"],
                "modified_time": source["modified_time"],
                "locator": claim["locator"],
            }] for review in (publication_review, quality_review))):
        raise SigningError("scoped_claim_evidence_mismatch")
    try:
        path = private_path(Path(claim["snapshot_path"]), suffix=".txt")
        if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
            raise SigningError("scoped_claim_snapshot_invalid")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != source["snapshot_sha256"]:
            raise SigningError("scoped_claim_snapshot_changed")
        extracted = content.decode("utf-8")
        if any(end > len(extracted) for _, end in ranges):
            raise SigningError("scoped_claim_locator_out_of_bounds")
        excerpts = [extracted[start:end] for start, end in ranges]
        excerpt_sha256 = hashlib.sha256(json.dumps(
            excerpts, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
    except SigningError:
        raise
    except (OSError, UnicodeError, KeyError, TypeError, ValueError) as error:
        raise SigningError("scoped_claim_snapshot_invalid") from error
    if claim.get("excerpt_sha256") != excerpt_sha256:
        raise SigningError("scoped_claim_excerpt_changed")


def private_path(path: Path, *, suffix: str) -> Path:
    root = (REPO_ROOT / "data").resolve(strict=True)
    candidate = path.resolve(strict=False)
    if candidate.parent != root or candidate.suffix != suffix or path.is_symlink():
        raise SigningError("private_ignored_file_required")
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", candidate.relative_to(REPO_ROOT).as_posix()],
        cwd=REPO_ROOT, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if ignored.returncode != 0:
        raise SigningError("private_ignored_file_required")
    if candidate.exists():
        info = candidate.stat()
        if (not stat.S_ISREG(info.st_mode)
                or (os.name == "posix" and (info.st_uid != os.geteuid()
                                            or stat.S_IMODE(info.st_mode) & 0o077))):
            raise SigningError("private_owned_regular_file_required")
    return candidate


def private_signing_key(path: Path) -> Path:
    """Read an existing key only from the owner's separate secret directory."""
    directory = SIGNING_KEY_DIR.resolve(strict=False)
    candidate = path.resolve(strict=False)
    if (not path.is_absolute() or path.is_symlink() or SIGNING_KEY_DIR.is_symlink()
            or candidate.suffix != ".pem" or candidate.parent != directory
            or candidate.is_relative_to(REPO_ROOT.resolve())):
        raise SigningError("external_private_signing_key_required")
    parent = directory.stat()
    if (not stat.S_ISDIR(parent.st_mode)
            or (os.name == "posix" and
                (parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) & 0o077))):
        raise SigningError("private_signing_key_permissions_required")
    info = candidate.stat()
    if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 16_384
            or (os.name == "posix" and
                (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077))):
        raise SigningError("private_signing_key_permissions_required")
    return candidate


def sign_review(kind: str, public_item: dict, dossier: dict,
                private_key: Ed25519PrivateKey) -> dict:
    if kind not in KINDS or not isinstance(public_item, dict) or not isinstance(dossier, dict):
        raise SigningError("invalid_review_dossier")
    if (public_item.get("status") != "approved"
            or not isinstance(public_item.get("id"), str) or not public_item["id"]
            or "source_ref" in public_item or "source_refs" in public_item
            or dossier.get("schema_version") != 1
            or dossier.get("kind") != kind or dossier.get("item_id") != public_item["id"]
            or not isinstance(dossier.get("nonce"), str)
            or re.fullmatch(r"[0-9a-f]{64}", dossier["nonce"]) is None):
        raise SigningError("invalid_review_dossier")
    reference_field = "source_ref" if kind == "questions" else "source_refs"
    full_item = {**public_item, reference_field: dossier.get(reference_field)}
    sources = dossier.get("sources")
    if not isinstance(sources, list) or not sources:
        raise SigningError("private_sources_required")
    source_map = {}
    for source in sources:
        if (not isinstance(source, dict) or not isinstance(source.get("id"), str)
                or not source["id"] or source["id"] in source_map
                or source.get("kind") not in {"learning_material", "bibliography"}
                or source.get("readable") is not True
                or any(not isinstance(source.get(field), str) or not source[field].strip()
                       for field in ("title", "modified_time", "snapshot_sha256",
                                     "reviewer", "reviewed_at", "snapshot_kind"))
                or re.fullmatch(r"[0-9a-f]{64}", source["snapshot_sha256"]) is None
                or source["snapshot_kind"] not in {"file_bytes", "extracted_text"}):
            raise SigningError("invalid_private_source_review")
        source_map[source["id"]] = source
    public_text = json.dumps(public_item, ensure_ascii=False, sort_keys=True)
    if (PUBLIC_DRIVE_LINK.search(public_text)
            or any(source_id in public_text for source_id in source_map)
            or ("source" in public_item
                and (kind != "literature" or not isinstance(public_item["source"], dict)
                     or set(public_item["source"]) - {"title", "locator", "citation"}))):
        raise SigningError("private_source_in_public_content")
    key = f"{kind}:{public_item['id']}"
    policy = PublicationPolicy({}, source_map,
                               {key: dossier.get("publication_review")},
                               {key: dossier.get("quality_review")})
    error = policy.error(kind, full_item, private_review=True)
    if error is not None:
        raise SigningError(error)
    public_sha256 = fingerprint(public_item)
    review_sha256 = fingerprint(dossier)
    signer_key_id = key_id(private_key.public_key())
    signature = private_key.sign(certificate_payload(
        kind, public_item["id"], public_sha256, review_sha256, signer_key_id))
    return {"schema_version": 1, "item_sha256": public_sha256,
            "review_sha256": review_sha256, "key_id": signer_key_id,
            "signature": base64.b64encode(signature).decode("ascii")}


def verify_current_sources(dossier: dict, inventory: dict, processed: dict,
                           *, public_item: dict | None = None) -> None:
    """Require every private source to match a completed review in this inventory."""
    if (not isinstance(inventory, dict) or inventory.get("schema_version") != 1
            or not isinstance(inventory.get("folders"), dict)
            or not isinstance(processed, dict)):
        raise SigningError("invalid_private_inventory")
    try:
        registry = json.loads((REPO_ROOT / "content/source-corpus.json").read_text(encoding="utf-8"))
        if not isinstance(registry, dict) or not isinstance(registry.get("sources"), list):
            raise SigningError("invalid_reviewed_source_registry")
        registered = {source["id"]: source for source in registry["sources"]}
        if len(registered) != len(registry["sources"]):
            raise SigningError("invalid_reviewed_source_registry")
        snapshot = scan(inventory.get("root_id"), {
            folder: complete_listing(pages)
            for folder, pages in inventory["folders"].items()
        })
        if public_item is not None:
            visible_text = json.dumps(public_item, ensure_ascii=False, sort_keys=True)
            if any(file_id in visible_text for file_id in snapshot["files"]
                   if len(file_id) >= 20):
                raise SigningError("private_source_in_public_content")
        states = processing_status(snapshot, processed)
        related_conflicts = unresolved_related_conflicts(processed)
    except SigningError:
        raise
    except (InventoryError, KeyError, TypeError, OSError, ValueError) as error:
        raise SigningError("invalid_private_inventory") from error
    for source in dossier.get("sources", []):
        if not isinstance(source, dict) or not isinstance(source.get("id"), str):
            raise SigningError("invalid_private_source_review")
        source_id = source["id"]
        item = snapshot["files"].get(source_id)
        record = processed.get(source_id)
        canonical = registered.get(source_id)
        state = states.get(source_id)
        if (item is None or state not in {"processed", "conflict_review"}
                or source_id in related_conflicts
                or not isinstance(record, dict)
                or source.get("title") != item["title"]
                or source.get("modified_time") != item["modified_time"]
                or source.get("snapshot_kind") != record.get("snapshot_kind")
                or source.get("snapshot_sha256") != record.get("snapshot_sha256")
                or (state == "processed" and
                    (source.get("reviewer") != record.get("reviewer")
                     or source.get("reviewed_at") != record.get("reviewed_at", "")[:10]))
                or (state == "conflict_review" and
                    (not isinstance(canonical, dict)
                     or source.get("reviewer") != canonical.get("reviewer")
                     or source.get("reviewed_at") != canonical.get("reviewed_at")))):
            raise SigningError("private_source_revision_not_current")
        if state == "conflict_review":
            _verify_scoped_claim(dossier, source, record)
        elif "scoped_claim_review" in dossier:
            raise SigningError("scoped_claim_review_unnecessary")
        if (record.get("source_kind") is not None
                and record["source_kind"] != source.get("kind")):
            raise SigningError("private_source_kind_mismatch")
        if canonical is not None:
            if (canonical.get("kind") != source.get("kind")
                    or canonical.get("modified_time") != item["modified_time"]
                    or canonical.get("snapshot_kind") != record.get("snapshot_kind")
                    or canonical.get("snapshot_sha256") != record.get("snapshot_sha256")):
                raise SigningError("private_source_kind_mismatch")
        elif record.get("source_kind") != source.get("kind"):
            raise SigningError("private_source_kind_mismatch")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sign a private source review for one public item")
    parser.add_argument("--kind", required=True, choices=sorted(KINDS))
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--dossier", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--processed", required=True, type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        dossier_path = private_path(args.dossier, suffix=".json")
        inventory_path = private_path(args.inventory, suffix=".json")
        processed_path = private_path(args.processed, suffix=".json")
        key_path = private_signing_key(args.private_key)
        output_path = private_path(args.output, suffix=".json")
        if output_path.exists() or not stat.S_ISREG(key_path.stat().st_mode):
            raise SigningError("private_output_or_key_invalid")
        items = []
        pattern = "**/*.json" if args.kind == "questions" else "*.json"
        for path in (REPO_ROOT / "content" / args.kind).glob(pattern):
            entries = json.loads(path.read_text(encoding="utf-8"))
            items.extend(item for item in entries if isinstance(item, dict)
                         and item.get("id") == args.item_id)
        if len(items) != 1:
            raise SigningError("public_item_not_unique")
        dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        processed = json.loads(processed_path.read_text(encoding="utf-8"))
        verify_current_sources(dossier, inventory, processed, public_item=items[0])
        private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise SigningError("ed25519_signing_key_required")
        certificate = sign_review(args.kind, items[0], dossier, private_key)
        descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({f"{args.kind}:{args.item_id}": certificate}, output, indent=2)
            output.write("\n")
    except (SigningError, OSError, ValueError, TypeError, KeyError) as error:
        print("PRIVATE_PUBLICATION_SIGN_STOP: " +
              (str(error) if isinstance(error, SigningError) else type(error).__name__),
              file=sys.stderr)
        return 1
    print("PRIVATE_PUBLICATION_CERTIFICATE_CREATED; no item published")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
