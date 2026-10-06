import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.content_publication import PublicationPolicy, fingerprint
from app.curriculum import validate_private_bindings
from scripts import sign_private_publication as signer
from scripts.sign_private_publication import SigningError, sign_review, verify_current_sources
from scripts import validate_questions
from scripts import validate_glossary
from app import glossary


def fixture_review():
    public = {"id": "synthetic_question", "status": "approved", "kind": "theory",
              "question": "Какой ответ соответствует учебному примеру?",
              "explanation": "Синтетическое пояснение."}
    full = {**public, "source_ref": "drive:fixture#page-1"}
    source = {"id": "fixture", "kind": "learning_material", "readable": True,
              "title": "Synthetic source", "modified_time": "2026-09-27T00:00:00Z",
              "snapshot_sha256": "a" * 64, "snapshot_kind": "extracted_text",
              "reviewer": "test-reviewer", "reviewed_at": "2026-09-27"}
    evidence = {"source_id": "fixture", "snapshot_sha256": source["snapshot_sha256"],
                "modified_time": source["modified_time"], "locator": "page 1"}
    dossier = {"schema_version": 1, "kind": "questions", "item_id": public["id"],
               "nonce": "b" * 64, "source_ref": full["source_ref"], "sources": [source],
               "publication_review": {
                   "decision": "approved", "item_sha256": fingerprint(full),
                   "purpose": "learning_content", "reviewer": "test-reviewer",
                   "reviewed_at": "2026-09-27", "sources": [evidence],
               },
               "quality_review": {
                   "item_sha256": fingerprint(full), "source_support": "supported",
                   "meaning": "consistent", "issues": [], "note": "Synthetic source supports answer",
                   "reviewer": "test-reviewer", "reviewed_at": "2026-09-27",
                   "checks": ["meaning", "answer", "explanation", "ambiguity", "duplicates", "sources"],
                   "sources": [evidence],
               }}
    return public, dossier


def test_private_dossier_review_is_key_independent_but_does_not_grant_publication():
    public, dossier = fixture_review()
    review = signer.validate_review_dossier("questions", public, dossier)
    assert review == {"item_sha256": fingerprint(public), "review_sha256": fingerprint(dossier)}
    assert "source_ref" not in review and "sources" not in review
    # An unsigned validation result cannot bypass the existing publication gate.
    key = Ed25519PrivateKey.generate()
    policy = PublicationPolicy({}, {}, {}, certificates={"questions:synthetic_question": review},
                               certificate_key=key.public_key())
    assert policy.error("questions", public) == "invalid_publication_certificate"
    with pytest.raises(SigningError, match="derivative_changed_since_review"):
        signer.validate_review_dossier("questions", {**public, "explanation": "Changed claim"}, dossier)
    key = Ed25519PrivateKey.generate()
    certificate = sign_review("questions", public, dossier, key)
    assert all(certificate[field] == value for field, value in review.items())


@pytest.mark.parametrize("stale_source", [False, True])
@pytest.mark.parametrize("review_only", [False, True])
def test_review_only_cli_never_reads_key_and_requires_current_sources(tmp_path, monkeypatch, capsys, stale_source, review_only):
    public, dossier = fixture_review()
    root = tmp_path / "repo"
    content = root / "content" / "questions"
    content.mkdir(parents=True)
    bank = content / "synthetic.json"
    bank.write_text(json.dumps([public]), encoding="utf-8")
    private = root / "data"
    private.mkdir()
    paths = []
    for name, value in (("dossier", dossier), ("inventory", {"synthetic": "inventory"}),
                        ("processed", {"synthetic": "processed"})):
        path = private / (name + ".json")
        path.write_text(json.dumps(value), encoding="utf-8")
        paths.append(path)
    output = private / "result.json"
    before = bank.read_bytes()
    calls = []
    def verify(d, inventory, processed, **kwargs):
        assert d == dossier and inventory == {"synthetic": "inventory"}
        assert processed == {"synthetic": "processed"} and kwargs["public_item"] == public
        calls.append("source-review")
        if stale_source:
            raise SigningError("source_revision_changed_since_review")
    def key_forbidden(*args, **kwargs):
        pytest.fail("Review-only must not touch a signing key")
    monkeypatch.setattr(signer, "REPO_ROOT", root)
    monkeypatch.setattr(signer, "private_path", lambda path, **kwargs: path)
    monkeypatch.setattr(signer, "verify_current_sources", verify)
    monkeypatch.setattr(signer, "private_signing_key", key_forbidden)
    monkeypatch.setattr(signer.serialization, "load_pem_private_key", key_forbidden)
    args = [*( ["--review-only"] if review_only else []), "--kind", "questions", "--item-id", public["id"],
            "--dossier", str(paths[0]), "--inventory", str(paths[1]), "--processed", str(paths[2]),
            "--output", str(output)]
    assert signer.main(args) == int(stale_source)
    assert calls == ["source-review"] and bank.read_bytes() == before
    if stale_source:
        assert not output.exists()
    else:
        result = json.loads(output.read_text(encoding="utf-8"))
        if review_only:
            assert result["scope"] == "private_review_validation"
            assert result["items"]["questions:" + public["id"]] == signer.validate_review_dossier("questions", public, dossier)
        else:
            assert result["questions:" + public["id"]] == signer.create_review_receipt("questions", public, dossier)
            assert PublicationPolicy({}, {}, {}, receipts=result).can_publish("questions", public)
        assert "signature" not in output.read_text(encoding="utf-8")
        saved = output.read_bytes()
        assert signer.main(args) == 1 and output.read_bytes() == saved
    captured = capsys.readouterr()
    assert "drive:fixture" not in captured.out + captured.err


def test_signing_key_must_be_outside_checkout_in_owner_secret_directory(tmp_path, monkeypatch):
    secrets = tmp_path / "secrets" / "psychology-quiz"
    secrets.mkdir(parents=True)
    secrets.chmod(0o700)
    key = secrets / "publication.pem"
    key.write_text("synthetic private key", encoding="ascii")
    key.chmod(0o600)
    monkeypatch.setattr(signer, "SIGNING_KEY_DIR", secrets)
    monkeypatch.setattr(signer, "REPO_ROOT", tmp_path / "checkout")
    assert signer.private_signing_key(key) == key
    inside = tmp_path / "checkout" / "data" / "publication.pem"
    inside.parent.mkdir(parents=True)
    inside.write_text("synthetic private key", encoding="ascii")
    with pytest.raises(SigningError, match="external_private_signing_key_required"):
        signer.private_signing_key(inside)


def test_signed_private_review_allows_exact_public_item_without_drive_ref():
    public, dossier = fixture_review()
    key = Ed25519PrivateKey.generate()
    certificate = sign_review("questions", public, dossier, key)
    policy = PublicationPolicy({}, {}, {}, {}, {"questions:synthetic_question": certificate},
                               key.public_key())
    assert policy.can_publish("questions", public)
    assert not policy.can_publish("questions", {**public, "question": "Changed"})
    assert not PublicationPolicy({}, {}, {}, {},
                                 {"questions:synthetic_question": certificate},
                                 Ed25519PrivateKey.generate().public_key()).can_publish("questions", public)
    assert not PublicationPolicy({}, {}, {}, {}).can_publish("questions", public)


def test_signed_alternate_lesson_binding_rejects_topic_or_edition_change():
    public, dossier = fixture_review()
    topic_id = "t_" + "a" * 12
    dossier["curriculum_topic_id"] = topic_id
    dossier["curriculum_link"] = {"source_id": "fixture", "topic_id": topic_id,
                                  "lesson_id": topic_id, "format": "presentation"}
    key = Ed25519PrivateKey.generate()
    certificate = sign_review("questions", public, dossier, key)
    assert certificate["schema_version"] == 2
    policy = PublicationPolicy({}, {}, {}, {},
                               {"questions:synthetic_question": certificate}, key.public_key())
    assert policy.can_publish("questions", public)
    edition = {"external_id": "synthetic_question", "topic_id": topic_id,
               "item_sha256": fingerprint(public),
               "locator": "private certificate:questions:synthetic_question"}
    catalog = {"editions": {"c" * 64: edition}}
    document = {"schema_version": 1, "items": {"c" * 64: certificate}}
    active = {"questions:synthetic_question": certificate}
    assert validate_private_bindings(catalog, document, key.public_key(), active) == document["items"]
    with pytest.raises(ValueError, match="Missing current private curriculum binding"):
        validate_private_bindings(catalog, {"schema_version": 1, "items": {}},
                                  key.public_key(), active)
    with pytest.raises(ValueError, match="Missing current private curriculum edition"):
        validate_private_bindings({"editions": {}}, {"schema_version": 1, "items": {}},
                                  key.public_key(), active)
    with pytest.raises(ValueError, match="Invalid private curriculum binding"):
        validate_private_bindings({"editions": {"c" * 64: {**edition,
            "topic_id": "t_" + "b" * 12}}}, document, key.public_key())
    with pytest.raises(ValueError, match="Invalid private curriculum binding"):
        validate_private_bindings({"editions": {"c" * 64: {**edition,
            "item_sha256": "d" * 64}}}, document, key.public_key())
    assert not PublicationPolicy({}, {}, {}, {},
                                 {"questions:synthetic_question": {**certificate,
                                     "topic_id": "t_" + "b" * 12}},
                                 key.public_key()).can_publish("questions", public)


@pytest.mark.parametrize("signed", [True, False])
def test_question_validator_requires_verified_certificate_when_source_ref_is_private(tmp_path, monkeypatch, signed):
    public, dossier = fixture_review()
    public.update({"category": "Тема", "options": ["А", "Б", "В", "Г"],
                   "correct_option_index": 0, "difficulty": "easy"})
    full = {**public, "source_ref": dossier["source_ref"]}
    for key in ("publication_review", "quality_review"):
        dossier[key]["item_sha256"] = fingerprint(full)
    key = Ed25519PrivateKey.generate()
    certificate = sign_review("questions", public, dossier, key)
    policy = PublicationPolicy({}, {}, {}, {},
                               {"questions:synthetic_question": certificate}, key.public_key()) if signed else PublicationPolicy(
                                   {}, {}, {}, receipts={"questions:synthetic_question": signer.create_review_receipt("questions", public, dossier)})
    content = tmp_path / "content"
    content.mkdir()
    (content / "topics.json").write_text(json.dumps([{
        "id": "topic", "title": "Тема", "status": "active", "order": 1,
        "available_contours": ["questions"], "question_file": "content/questions.json"}]),
        encoding="utf-8")
    questions = content / "questions.json"
    questions.write_text(json.dumps([public]), encoding="utf-8")
    monkeypatch.setattr(validate_questions, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(validate_questions, "TOPICS_PATH", content / "topics.json")
    monkeypatch.setattr(validate_questions, "memberships", lambda: {})
    monkeypatch.setattr(validate_questions, "load_policy", lambda: policy)
    monkeypatch.setattr(validate_questions, "load_homework_catalog", lambda: ())
    assert validate_questions.validate() == []
    questions.write_text(json.dumps([{**public, "question": "Подменённый вопрос"}]), encoding="utf-8")
    assert any("source_ref" in error for error in validate_questions.validate())
    questions.write_text(json.dumps([{**public, "status": "draft"}]), encoding="utf-8")
    assert validate_questions.validate() == []


@pytest.mark.parametrize("signed", [True, False])
def test_glossary_loader_requires_verified_certificate_when_refs_are_private(tmp_path, monkeypatch, signed):
    public = {"id": "synthetic_term", "topic_id": "vvedenie_v_professiyu", "term": "Опора",
              "aliases": [], "short_definition": "Источник поддержки",
              "definition": "То, что помогает человеку справляться с учебными задачами.",
              "examples": ["Поддержка наставника"], "confusable_with": [],
              "difficulty": "easy", "status": "approved"}
    source = {"id": "fixture", "kind": "learning_material", "readable": True,
              "title": "Synthetic source", "modified_time": "2026-09-27T00:00:00Z",
              "snapshot_sha256": "a" * 64, "snapshot_kind": "extracted_text",
              "reviewer": "test-reviewer", "reviewed_at": "2026-09-27"}
    evidence = {"source_id": "fixture", "snapshot_sha256": source["snapshot_sha256"],
                "modified_time": source["modified_time"], "locator": "page 1"}
    full = {**public, "source_refs": ["drive:fixture#page-1"]}
    dossier = {"schema_version": 1, "kind": "glossary", "item_id": public["id"],
               "nonce": "b" * 64, "source_refs": full["source_refs"], "sources": [source],
               "publication_review": {"decision": "approved", "item_sha256": fingerprint(full),
                                      "purpose": "learning_content", "reviewer": "test-reviewer",
                                      "reviewed_at": "2026-09-27", "sources": [evidence]},
               "quality_review": {"item_sha256": fingerprint(full),
                                  "source_support": "supported", "meaning": "consistent",
                                  "issues": [], "note": "Exact synthetic definition reviewed",
                                  "reviewer": "test-reviewer", "reviewed_at": "2026-09-27",
                                  "checks": ["meaning", "definition", "examples", "ambiguity",
                                             "duplicates", "sources"], "sources": [evidence]}}
    key = Ed25519PrivateKey.generate()
    certificate = sign_review("glossary", public, dossier, key)
    policy = PublicationPolicy({}, {}, {}, {},
                               {"glossary:synthetic_term": certificate}, key.public_key()) if signed else PublicationPolicy(
                                   {}, {}, {}, receipts={"glossary:synthetic_term": signer.create_review_receipt("glossary", public, dossier)})
    directory = tmp_path / "glossary"
    directory.mkdir()
    path = directory / "vvedenie_v_professiyu.json"
    path.write_text(json.dumps([public]), encoding="utf-8")
    monkeypatch.setattr(glossary, "_GLOSSARY_DIR", directory)
    monkeypatch.setattr(glossary, "load_policy", lambda: policy)
    monkeypatch.setattr(validate_glossary, "load_policy", lambda: policy)
    errors = []
    validate_glossary.validate_entry(public, "term", "vvedenie_v_professiyu",
                                     {"vvedenie_v_professiyu": {}}, {}, {}, errors)
    assert errors == []
    assert glossary.load_glossary_entries("vvedenie_v_professiyu")[0].source_refs == ()
    path.write_text(json.dumps([{**public, "definition": "Подменено"}]), encoding="utf-8")
    assert glossary.load_glossary_entries("vvedenie_v_professiyu") == []
    altered_errors = []
    validate_glossary.validate_entry({**public, "definition": "Подменено"}, "term",
                                     "vvedenie_v_professiyu", {"vvedenie_v_professiyu": {}},
                                     {}, {}, altered_errors)
    assert any("certificate" in error for error in altered_errors)


def test_invalid_signature_or_mixed_public_private_evidence_is_rejected():
    public, dossier = fixture_review()
    key = Ed25519PrivateKey.generate()
    certificate = sign_review("questions", public, dossier, key)
    signature = bytearray(base64.b64decode(certificate["signature"]))
    signature[0] ^= 1
    forged = {**certificate, "signature": base64.b64encode(signature).decode("ascii")}
    policy = PublicationPolicy({}, {}, {}, {}, {"questions:synthetic_question": forged},
                               key.public_key())
    assert policy.error("questions", public) == "invalid_publication_certificate"
    policy.certificates["questions:synthetic_question"] = {**certificate, "signature": "!"}
    assert policy.error("questions", public) == "invalid_publication_certificate"
    policy.certificates["questions:synthetic_question"] = certificate
    assert policy.error("questions", {**public, "source_ref": dossier["source_ref"]}) == \
        "mixed_public_private_source_review"


def test_signer_requires_source_revision_quality_and_private_nonce():
    public, dossier = fixture_review()
    key = Ed25519PrivateKey.generate()
    with pytest.raises(SigningError, match="source_revision_changed_since_review"):
        changed = {**dossier, "sources": [{**dossier["sources"][0], "snapshot_sha256": "c" * 64}]}
        sign_review("questions", public, changed, key)
    with pytest.raises(SigningError, match="learning_quality_not_approved"):
        changed = {**dossier, "quality_review": {**dossier["quality_review"], "issues": ["ambiguous"]}}
        sign_review("questions", public, changed, key)
    with pytest.raises(SigningError, match="invalid_review_dossier"):
        sign_review("questions", public, {**dossier, "nonce": ""}, key)
    with pytest.raises(SigningError, match="private_source_in_public_content"):
        sign_review("questions", {**public, "notes": "drive:fixture"}, dossier, key)
    with pytest.raises(SigningError, match="private_source_in_public_content"):
        sign_review("questions", {**public, "source": {"id": "fixture"}}, dossier, key)


def test_signer_checks_processed_private_source_against_complete_inventory():
    public, dossier = fixture_review()
    source = dossier["sources"][0]
    inventory = {"schema_version": 1, "root_id": "root", "folders": {"root": [{
        "page_token": None, "next_page_token": None,
        "children": [{"id": source["id"], "parent_ids": ["root"],
                      "file_or_folder": "file", "title": source["title"],
                      "mime_type": "application/vnd.google-apps.document",
                      "modified_time": source["modified_time"]}],
    }]}}
    processed = {source["id"]: {
        "revision": [source["modified_time"], source["title"],
                     "application/vnd.google-apps.document"],
        "review_state": "processed", "snapshot_kind": source["snapshot_kind"],
        "source_kind": "learning_material",
        "source_kind_review": {"reviewer": "test-reviewer",
                               "reviewed_at": "2026-09-27T00:00:00Z",
                               "note": "Reviewed as learning material"},
        "snapshot_sha256": source["snapshot_sha256"], "reviewer": "test-reviewer",
        "review_note": "Reviewed exact source", "reviewed_at": "2026-09-27T00:00:00Z",
    }}
    verify_current_sources(dossier, inventory, processed)
    verify_current_sources(dossier, inventory, processed, public_item=public)
    other_private_id = "another_private_drive_file_1234567890"
    inventory_with_other = {**inventory, "folders": {"root": [{
        **inventory["folders"]["root"][0],
        "children": [*inventory["folders"]["root"][0]["children"], {
            "id": other_private_id, "parent_ids": ["root"],
            "file_or_folder": "file", "title": "Other lecture",
            "mime_type": "application/vnd.google-apps.document",
            "modified_time": source["modified_time"]}]}]}}
    with pytest.raises(SigningError, match="private_source_in_public_content"):
        verify_current_sources(dossier, inventory_with_other, processed,
                               public_item={**public, "explanation": other_private_id})
    with pytest.raises(SigningError, match="private_source_kind_mismatch"):
        verify_current_sources(dossier, inventory, {source["id"]: {
            **processed[source["id"]], "source_kind": "bibliography"}})
    with pytest.raises(SigningError, match="private_source_revision_not_current"):
        verify_current_sources(dossier, inventory, {source["id"]: {
            **processed[source["id"]], "source_kind": "excluded"}})
    with pytest.raises(SigningError, match="private_source_kind_mismatch"):
        verify_current_sources(dossier, inventory, {source["id"]: {
            key: value for key, value in processed[source["id"]].items()
            if key != "source_kind"}})
    with pytest.raises(SigningError, match="private_source_revision_not_current"):
        verify_current_sources(dossier, inventory, {**processed, "other": {
            "review_state": "conflict", "related_source_ids": [source["id"]]}})
    with pytest.raises(SigningError, match="private_source_revision_not_current"):
        verify_current_sources(dossier, inventory, {**processed, source["id"]: {
            **processed[source["id"]], "snapshot_sha256": "c" * 64}})
    with pytest.raises(SigningError, match="private_source_revision_not_current"):
        changed = {**inventory, "folders": {"root": [{**inventory["folders"]["root"][0],
            "children": [{**inventory["folders"]["root"][0]["children"][0],
                          "modified_time": "2026-09-28T00:00:00Z"}]}]}}
        verify_current_sources(dossier, changed, processed)


@pytest.mark.parametrize("kind,item_id,source_id,legacy_locator", [
    ("glossary", "dopamine", "1N5lBZzLSmiGqtQpxIHGIz8y630BfYc8hI7kD9Qcc97w", False),
    ("questions", "m1_psyf_070", "1IkZqA_0yVgzsavRbChHb4hWVUYE1BmuYgtlNp7I3264", True),
    ("questions", "m1_psyf_071", "1IkZqA_0yVgzsavRbChHb4hWVUYE1BmuYgtlNp7I3264", True),
])
def test_scoped_claim_keeps_conflicted_source_on_hold(
        tmp_path, monkeypatch, kind, item_id, source_id, legacy_locator):
    _, dossier = fixture_review()
    source = dossier["sources"][0]
    source["id"] = source_id
    extracted = "Supported sentence. Disputed medical statement."
    source["snapshot_sha256"] = hashlib.sha256(extracted.encode("utf-8")).hexdigest()
    root = tmp_path / "repo"
    (root / "content").mkdir(parents=True)
    snapshot_path = root / "source.txt"
    snapshot_path.write_text(extracted, encoding="utf-8")
    (root / "content" / "source-corpus.json").write_text(json.dumps({
        "schema_version": 1, "sources": [source],
    }), encoding="utf-8")
    monkeypatch.setattr(signer, "REPO_ROOT", root)
    monkeypatch.setattr(signer, "private_path", lambda path, *, suffix: path)
    inventory = {"schema_version": 1, "root_id": "root", "folders": {"root": [{
        "page_token": None, "next_page_token": None,
        "children": [{"id": source["id"], "parent_ids": ["root"],
                      "file_or_folder": "file", "title": source["title"],
                      "mime_type": "application/vnd.google-apps.document",
                      "modified_time": source["modified_time"]}],
    }]}}
    record = {"revision": [source["modified_time"], source["title"],
                           "application/vnd.google-apps.document"],
              "review_state": "conflict", "reason": "Disputed medical statement",
              "locator": "characters:20:45", "related_source_ids": [],
              "reviewed_at": "2026-09-27T00:00:00Z",
              "snapshot_kind": "extracted_text",
              "snapshot_sha256": source["snapshot_sha256"]}
    if legacy_locator:
        record["locator"] = ("extracted_text UTF-8 characters 20:45; SHA-256 "
                             + source["snapshot_sha256"])
    dossier["kind"] = kind
    dossier["item_id"] = item_id
    locator = "characters:0:19"
    if kind == "glossary":
        dossier.pop("source_ref")
        dossier["source_refs"] = [f"drive:{source['id']}#{locator}"]
    else:
        dossier["source_ref"] = f"drive:{source['id']}#{locator}"
    evidence = {"source_id": source["id"], "snapshot_sha256": source["snapshot_sha256"],
                "modified_time": source["modified_time"], "locator": locator}
    dossier["publication_review"]["sources"] = [evidence]
    dossier["quality_review"]["sources"] = [evidence]
    dossier["scoped_claim_review"] = {
        "source_id": source["id"],
        "item_sha256": dossier["publication_review"]["item_sha256"],
        "snapshot_sha256": source["snapshot_sha256"],
        "conflict_sha256": fingerprint(record),
        "snapshot_path": str(snapshot_path), "locator": locator,
        "excerpt_sha256": hashlib.sha256(json.dumps(
            [extracted[:19]], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")).hexdigest(),
        "reviewer": "test-reviewer", "reviewed_at": "2026-09-28T00:00:00Z",
        "note": "Only the first sentence supports this exact glossary claim",
    }
    if kind == "questions":
        monkeypatch.setattr(signer, "SCOPED_LECTURE_CLAIMS", {
            item_id: (dossier["publication_review"]["item_sha256"], locator),
        })
        monkeypatch.setattr(signer, "LECTURE14_SOURCE_SHA256", source["snapshot_sha256"])
        monkeypatch.setattr(signer, "LECTURE14_CONFLICT_SHA256", fingerprint(record))
    verify_current_sources(dossier, inventory, {source["id"]: record})
    with pytest.raises(SigningError, match="scoped_claim_review_required"):
        verify_current_sources({**dossier, "item_id": "another_term"},
                               inventory, {source["id"]: record})
    changed = {**dossier, "scoped_claim_review": {
        **dossier["scoped_claim_review"], "locator": "characters:18:25"}}
    expected_error = ("scoped_claim_review_required" if kind == "questions"
                      else "scoped_claim_overlaps_conflict")
    with pytest.raises(SigningError, match=expected_error):
        verify_current_sources(changed, inventory, {source["id"]: record})
    with pytest.raises(SigningError, match="scoped_claim_review_required"):
        verify_current_sources(dossier, inventory, {source["id"]: {
            **record, "reason": "New conflict added"}})
    snapshot_path.write_text(extracted + " changed", encoding="utf-8")
    with pytest.raises(SigningError, match="scoped_claim_snapshot_changed"):
        verify_current_sources(dossier, inventory, {source["id"]: record})


def test_registered_bibliography_cannot_be_relabelled_as_learning_source():
    registry = json.loads((Path(__file__).resolve().parents[1] /
                           "content/source-corpus.json").read_text(encoding="utf-8"))
    source = next(item for item in registry["sources"] if item["kind"] == "bibliography")
    source_id = source["id"]
    reviewed_at = source["reviewed_at"] + "T00:00:00Z"
    inventory = {"schema_version": 1, "root_id": "root", "folders": {"root": [{
        "page_token": None, "next_page_token": None,
        "children": [{"id": source_id, "parent_ids": ["root"],
                      "file_or_folder": "file", "title": source["title"],
                      "mime_type": "application/pdf", "modified_time": source["modified_time"]}],
    }]}}
    processed = {source_id: {
        "revision": [source["modified_time"], source["title"], "application/pdf"],
        "review_state": "processed", "snapshot_kind": source["snapshot_kind"],
        "snapshot_sha256": source["snapshot_sha256"],
        "reviewer": source["reviewer"], "review_note": "Reviewed source category",
        "reviewed_at": reviewed_at,
    }}
    dossier_source = {**source, "reviewed_at": source["reviewed_at"]}
    verify_current_sources({"sources": [dossier_source]}, inventory, processed)
    with pytest.raises(SigningError, match="private_source_kind_mismatch"):
        verify_current_sources({"sources": [{**dossier_source, "kind": "learning_material"}]},
                               inventory, processed)


def test_review_receipt_keeps_quality_tamper_and_signature_boundaries():
    from copy import deepcopy
    public, dossier = fixture_review()
    receipt = signer.create_review_receipt("questions", public, dossier)
    policy = PublicationPolicy({}, {}, {}, receipts={"questions:synthetic_question": receipt})
    assert policy.has_private_review("questions", public)
    assert receipt["reviewer"] == "private-review" and "test-reviewer" not in json.dumps(receipt)
    assert not policy.can_publish("questions", {**public, "status": "draft"})
    assert not policy.can_publish("questions", {**public, "explanation": "Changed"})
    assert not policy.can_publish("questions", {**public, "source_ref": "drive:fixture"})
    for change in ({"checks": []}, {"source_support": "disputed"}, {"review_sha256": "bad"},
                   {"reviewed_at": "invalid"}, {"sources": []}, {"decision": "draft"}, {"schema_version": True}):
        invalid = PublicationPolicy({}, {}, {}, receipts={"questions:synthetic_question": {**receipt, **change}})
        assert not invalid.can_publish("questions", public)
    for change in ({"checks": []}, {"source_support": "disputed"}, {"issues": ["ambiguous"]}):
        invalid = deepcopy(dossier)
        invalid["quality_review"].update(change)
        with pytest.raises(SigningError):
            signer.create_review_receipt("questions", public, invalid)
    # Existing signed records still require a valid signature even with a valid receipt.
    key = Ed25519PrivateKey.generate()
    certificate = sign_review("questions", public, dossier, key)
    invalid = PublicationPolicy({}, {}, {}, certificates={"questions:synthetic_question": {**certificate, "signature": "bad"}},
                                certificate_key=key.public_key(), receipts={"questions:synthetic_question": receipt})
    assert invalid.error("questions", public) == "invalid_publication_certificate"
    assert "drive:" not in json.dumps(receipt) and "signature" not in receipt


def test_unsigned_curriculum_binding_preserves_exact_editions():
    public, dossier = fixture_review()
    topic = "t_" + "a" * 12
    dossier["curriculum_topic_id"] = topic
    dossier["curriculum_link"] = {"source_id": "fixture", "topic_id": topic, "lesson_id": topic, "format": "presentation"}
    receipt = signer.create_review_receipt("questions", public, dossier)
    edition = {"external_id": public["id"], "topic_id": topic, "item_sha256": fingerprint(public),
               "locator": "private review:questions:" + public["id"]}
    catalog = {"editions": {"c" * 64: edition}}
    document = {"schema_version": 1, "items": {"c" * 64: receipt}}
    active = {"questions:" + public["id"]: receipt}
    assert validate_private_bindings(catalog, document, None, active_receipts=active) == document["items"]
    with pytest.raises(ValueError, match="Missing current private curriculum binding"):
        validate_private_bindings(catalog, {"schema_version": 1, "items": {}}, None, active_receipts=active)
    with pytest.raises(ValueError, match="Invalid private curriculum binding"):
        validate_private_bindings({"editions": {"c" * 64: {**edition, "topic_id": "t_" + "b" * 12}}}, document, None)


def test_unsigned_bibliography_receipt_keeps_public_projection_and_metadata_validation(monkeypatch):
    from scripts import validate_literature
    public = json.loads(Path("content/literature/psychological_consulting.json").read_text(encoding="utf-8"))[0]
    public = {key: value for key, value in public.items() if key not in {"source_ref", "source_refs", "reviewed_curriculum_topics"}}
    public["source"] = {"citation": "Synthetic bibliographic citation"}
    public["id"] = "synthetic_book"
    _, dossier = fixture_review()
    dossier.update(kind="literature", item_id=public["id"], source_refs=["drive:fixture#page-1"])
    dossier.pop("source_ref")
    dossier["publication_review"].update(purpose="bibliographic_metadata",
        item_sha256=fingerprint({**public, "source_refs": dossier["source_refs"]}))
    receipt = signer.create_review_receipt("literature", public, dossier)
    policy = PublicationPolicy({}, {}, {}, receipts={"literature:synthetic_book": receipt})
    monkeypatch.setattr(validate_literature, "load_policy", lambda: policy)
    assert policy.can_publish("literature", public)
    errors = []
    validate_literature.validate_entry(public, "receipt book", public["topic_id"], {public["topic_id"]}, {}, errors)
    assert errors == []
    assert not policy.can_publish("literature", {**public, "title": "Changed"})
