import hashlib
import json
from copy import deepcopy

import pytest

from app.content_publication import fingerprint
from scripts import sign_private_publication as signer
from scripts.sign_private_publication import SigningError, verify_current_sources
from scripts.source_conflict import record_conflict
from scripts.source_finalize import finalize


def test_later_hold_keeps_captured_edition_for_independent_fragment_review(tmp_path, monkeypatch):
    public, dossier, inventory, pending, path = fragment_fixture(tmp_path, monkeypatch, state="pending_review")
    source_id = "synthetic_source"
    completed = finalize(inventory, pending, source_id, path, reviewer="reviewer",
                         review_note="Reviewed captured edition", reviewed_at="2026-09-28T00:00:00Z")
    held = record_conflict(inventory, completed, source_id, reason="Disputed second sentence",
                           locator="characters:16:30", related_source_ids=[],
                           reviewed_at="2026-09-29T00:00:00Z")
    before = deepcopy(held)
    dossier["scoped_claim_review"]["processing_sha256"] = fingerprint(held[source_id])
    verify_current_sources(dossier, inventory, held, public_item=public)
    assert held == before and held[source_id]["review_state"] == "conflict"
    assert held[source_id]["previous_processed_review"] == completed[source_id]
    overlapping = deepcopy(held)
    overlapping[source_id]["locator"] = "characters:0:30"
    dossier["scoped_claim_review"]["processing_sha256"] = fingerprint(overlapping[source_id])
    with pytest.raises(SigningError, match="fragment_overlaps_conflict"):
        verify_current_sources(dossier, inventory, overlapping, public_item=public)


def fragment_fixture(tmp_path, monkeypatch, *, state="conflict", kind="questions"):
    root = tmp_path / "repo"
    (root / "content").mkdir(parents=True)
    text = "Supported fact. Disputed fact. Another disputed fact."
    path = root / "extract.txt"
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    public = {"id": "synthetic_fragment", "status": "approved", "title": "Synthetic title"}
    source = {"id": "synthetic_source", "title": "Synthetic lecture", "kind": "learning_material",
              "modified_time": "2026-09-27T00:00:00Z", "snapshot_kind": "extracted_text",
              "snapshot_sha256": digest, "readable": True, "reviewer": "reviewer",
              "reviewed_at": "2026-10-01"}
    record = {"revision": [source["modified_time"], source["title"], "application/vnd.google-apps.document"],
              "review_state": state, "snapshot_kind": "extracted_text", "snapshot_sha256": digest}
    if state == "conflict":
        record.update(locator="characters:16:30", reviewed_at="2026-09-28T00:00:00Z",
                      reason="Disputed passage", related_source_ids=[], issues=[{"locator": "characters:31:52"}])
    locator = "characters:0:15"
    field = "source_ref" if kind == "questions" else "source_refs"
    reference = "drive:" + source["id"] + "#" + locator
    full = {**public, field: reference if kind == "questions" else [reference]}
    purpose = "bibliographic_metadata" if kind == "literature" else "learning_content"
    evidence = [{"source_id": source["id"], "modified_time": source["modified_time"],
                 "snapshot_sha256": digest, "locator": locator}]
    review = {"purpose": purpose, "item_sha256": fingerprint(full), "decision": "approved",
              "reviewer": "reviewer", "reviewed_at": "2026-10-01", "sources": evidence}
    dossier = {"kind": kind, "item_id": public["id"], field: full[field], "sources": [source],
               "publication_review": review, "quality_review": {**review, "purpose": "learning_content"},
               "scoped_claim_review": {"schema_version": 2, "kind": kind, "item_id": public["id"],
                  "purpose": purpose, "source_id": source["id"], "item_sha256": fingerprint(full),
                  "snapshot_sha256": digest, "processing_sha256": fingerprint(record),
                  "snapshot_path": str(path), "locator": locator, "reviewer": "reviewer",
                  "reviewed_at": "2026-10-01T00:00:00Z", "note": "Exact first sentence only",
                  "excerpt_sha256": hashlib.sha256(json.dumps([text[:15]],ensure_ascii=False,separators=(",", ":")).encode("utf-8")).hexdigest()}}
    inventory = {"schema_version": 1, "root_id": "root", "folders": {"root": [{
        "page_token": None, "next_page_token": None,
        "children": [{"id": source["id"], "parent_ids": ["root"], "file_or_folder": "file",
                      "title": source["title"], "mime_type": record["revision"][2], "modified_time": source["modified_time"]}]}]}}
    (root / "content/source-corpus.json").write_text(json.dumps({"sources": [source]}), encoding="utf-8")
    monkeypatch.setattr(signer, "REPO_ROOT", root)
    monkeypatch.setattr(signer, "private_path", lambda path, *, suffix: path)
    return public, dossier, inventory, {source["id"]: record}, path


def private_classification_fixture(tmp_path, monkeypatch):
    import subprocess
    from app.source_inventory import complete_listing, scan

    public, dossier, inventory, processed, extract = fragment_fixture(
        tmp_path, monkeypatch, state="pending_review", kind="literature")
    root = signer.REPO_ROOT
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".gitignore").write_text("data/\n", encoding="utf-8")
    (root / "data").mkdir()
    (root / "content/source-corpus.json").write_text(json.dumps({
        "schema_version": 1, "corpus_root_id": "root", "sources": []}), encoding="utf-8")
    (root / "content/curriculum.json").write_text(json.dumps({
        "schema_version": 1, "disciplines": {}, "topics": {}}), encoding="utf-8")
    snapshot = scan("root", {"root": complete_listing(inventory["folders"]["root"])})
    source = deepcopy(dossier["sources"][0])
    source.update(reviewer="classification reviewer", reviewed_at="2026-09-29",
                  corpus_path="/".join(snapshot["paths"][source["id"]][0]),
                  classification_receipt={"content": str(extract), "locator": "characters:0:15",
                      "snapshot_kind": "extracted_text", "snapshot_sha256": source["snapshot_sha256"]})
    path = root / "data/classification.json"
    path.write_text(json.dumps({"schema_version": 1, "corpus_root_id": "root", "sources": [source]}), encoding="utf-8")
    path.chmod(0o600)
    return public, dossier, inventory, processed, extract, path


def test_private_classification_supports_fragment_without_finalizing_source(tmp_path, monkeypatch):
    public, dossier, inventory, processed, _, path = private_classification_fixture(tmp_path, monkeypatch)
    before = deepcopy(processed)
    with pytest.raises(SigningError, match="private_source_kind_mismatch"):
        verify_current_sources(dossier, inventory, processed, public_item=public)
    verify_current_sources(dossier, inventory, processed, public_item=public, private_registry_path=path)
    assert processed == before
    dossier["publication_review"]["decision"] = "pending"
    with pytest.raises(SigningError, match="fragment_review_required"):
        verify_current_sources(dossier, inventory, processed, public_item=public, private_registry_path=path)


def test_private_classification_cannot_override_public_source(tmp_path, monkeypatch):
    public, dossier, inventory, processed, _, path = private_classification_fixture(tmp_path, monkeypatch)
    registry = json.loads(path.read_text(encoding="utf-8"))
    (signer.REPO_ROOT / "content/source-corpus.json").write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(SigningError, match="invalid_private_inventory"):
        verify_current_sources(dossier, inventory, processed, public_item=public, private_registry_path=path)


def test_private_classification_checks_receipt_not_only_metadata(tmp_path, monkeypatch):
    public, dossier, inventory, processed, extract, path = private_classification_fixture(tmp_path, monkeypatch)
    extract.write_bytes(extract.read_bytes() + b"Changed")
    with pytest.raises(SigningError, match="private_source_classification_changed"):
        verify_current_sources(dossier, inventory, processed, public_item=public, private_registry_path=path)


def test_private_classification_still_rejects_overlapping_conflict(tmp_path, monkeypatch):
    public, dossier, inventory, processed, _, path = private_classification_fixture(tmp_path, monkeypatch)
    source_id = dossier["sources"][0]["id"]
    processed[source_id].update(review_state="conflict", locator="characters:0:15",
        reviewed_at="2026-09-28T00:00:00Z", reason="Held same fragment", related_source_ids=[])
    dossier["scoped_claim_review"]["processing_sha256"] = fingerprint(processed[source_id])
    with pytest.raises(SigningError, match="fragment_overlaps_conflict"):
        verify_current_sources(dossier, inventory, processed, public_item=public, private_registry_path=path)


def test_private_literature_labels_bind_current_reviewed_lesson(tmp_path, monkeypatch):
    public, dossier, inventory, processed, _, registry = private_classification_fixture(tmp_path, monkeypatch)
    sid = dossier["sources"][0]["id"]
    tid = "t_" + hashlib.sha256(sid.encode()).hexdigest()[:12]
    label = {"id": tid, "title": "Exact private lesson", "discipline_id": "one"}
    public.update(topic_id="one", curriculum_topic_ids=[tid], reviewed_curriculum_topics=[label])
    full = {**public, "source_refs": dossier["source_refs"]}
    for field in ("scoped_claim_review", "publication_review", "quality_review"):
        dossier[field]["item_sha256"] = fingerprint(full)
    topics = signer.REPO_ROOT / "data/topics.json"
    topics.write_text(json.dumps({"schema_version": 1, "corpus_root_id": "root",
        "disciplines": {"one": {"title": "Discipline"}}, "topics": {tid: {
            "title": label["title"], "discipline_id": "one", "source": {
                "source_id": sid, "modified_time": dossier["sources"][0]["modified_time"],
                "snapshot_sha256": dossier["sources"][0]["snapshot_sha256"]}}}}), encoding="utf-8")
    topics.chmod(0o600)
    before = deepcopy(processed)
    with pytest.raises(SigningError, match="private_literature_topics_required"):
        verify_current_sources(dossier, inventory, processed, public_item=public, private_registry_path=registry)
    verify_current_sources(dossier, inventory, processed, public_item=public,
                           private_registry_path=registry, private_topics_path=topics)
    assert processed == before
    label["title"] = "Unreviewed title"
    with pytest.raises(SigningError, match="private_literature_topics_required"):
        verify_current_sources(dossier, inventory, processed, public_item=public,
                               private_registry_path=registry, private_topics_path=topics)


@pytest.mark.parametrize("kind", ["questions", "glossary", "literature"])
def test_new_fragment_review_preserves_all_source_holds(tmp_path, monkeypatch, kind):
    public, dossier, inventory, processed, _ = fragment_fixture(tmp_path, monkeypatch, kind=kind)
    before = deepcopy(processed)
    verify_current_sources(dossier, inventory, processed, public_item=public)
    assert processed == before and processed["synthetic_source"]["review_state"] == "conflict"
    # Neither another publication nor a changed public item can reuse this proof.
    with pytest.raises(SigningError, match="fragment_review_required"):
        verify_current_sources({**dossier,"item_id":"other"}, inventory, processed, public_item=public)
    with pytest.raises(SigningError, match="fragment_item_changed"):
        verify_current_sources(dossier, inventory, processed, public_item={**public,"title":"Changed"})


def test_fragment_review_checks_secondary_issue_and_changed_hold(tmp_path, monkeypatch):
    public,dossier,inventory,processed,path = fragment_fixture(tmp_path, monkeypatch)
    changed = deepcopy(processed)
    changed["synthetic_source"]["issues"] = [{"locator":"characters:0:10"}]
    with pytest.raises(SigningError, match="fragment_review_required"):
        verify_current_sources(dossier, inventory, changed, public_item=public)
    changed_dossier = deepcopy(dossier)
    changed_dossier["scoped_claim_review"]["processing_sha256"] = fingerprint(changed["synthetic_source"])
    with pytest.raises(SigningError, match="fragment_overlaps_conflict"):
        verify_current_sources(changed_dossier, inventory, changed, public_item=public)
    changed["synthetic_source"]["issues"] = [{"reason":"Unbounded issue"}]
    changed_dossier["scoped_claim_review"]["processing_sha256"] = fingerprint(changed["synthetic_source"])
    with pytest.raises(SigningError, match="fragment_locator_required"):
        verify_current_sources(changed_dossier, inventory, changed, public_item=public)
    path.write_text(path.read_text(encoding="utf-8") + " Changed", encoding="utf-8")
    with pytest.raises(SigningError, match="fragment_snapshot_changed"):
        verify_current_sources(dossier, inventory, processed, public_item=public)


def test_pending_used_fragment_is_not_source_finalization(tmp_path, monkeypatch):
    public,dossier,inventory,processed,_ = fragment_fixture(tmp_path, monkeypatch,state="pending_review",kind="literature")
    dossier.pop("quality_review")  # Bibliographic metadata does not certify textbook science.
    verify_current_sources(dossier,inventory,processed,public_item=public)
    assert processed["synthetic_source"]["review_state"] == "pending_review"
    with pytest.raises(SigningError, match="fragment_review_required"):
        verify_current_sources(dossier,inventory,processed)
    changed = deepcopy(inventory)
    changed["folders"]["root"][0]["children"][0]["modified_time"] = "2026-10-02T00:00:00Z"
    with pytest.raises(SigningError, match="private_source_revision_not_current"):
        verify_current_sources(dossier,changed,processed,public_item=public)


@pytest.mark.parametrize("field", ["publication_review", "quality_review"])
def test_fragment_requires_explicit_approval(tmp_path, monkeypatch, field):
    public, dossier, inventory, processed, _ = fragment_fixture(tmp_path, monkeypatch)
    dossier[field]["decision"] = "pending"
    with pytest.raises(SigningError, match="fragment_.*review_required"):
        verify_current_sources(dossier, inventory, processed, public_item=public)


def test_fragment_cannot_infer_offsets_from_previous_edition_hold(tmp_path, monkeypatch):
    public, dossier, inventory, processed, _ = fragment_fixture(tmp_path, monkeypatch)
    record = processed["synthetic_source"]
    record["conflict_hold"] = deepcopy(record)
    dossier["scoped_claim_review"]["processing_sha256"] = fingerprint(record)
    # Call the fragment verifier directly: malformed historical records are also
    # rejected by the outer inventory validator before reaching this check.
    from scripts.scoped_fragment_review import FragmentReviewError, verify_fragment_review
    with pytest.raises(FragmentReviewError, match="fragment_previous_hold_unresolved"):
        verify_fragment_review(dossier, dossier["sources"][0], record, public,
                               private_path=lambda path, *, suffix: path)
