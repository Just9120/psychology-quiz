import copy
import json
from pathlib import Path
import shutil

import pytest

from app import content_publication as publication, glossary, literature
from scripts import seed_questions


def reviewed(kind="questions", source_kind="learning_material"):
    item = {"id": "fixture", "status": "approved", "question": "Synthetic material"}
    if kind == "questions":
        item["explanation"] = "Synthetic explanation"
    item["source_ref" if kind == "questions" else "source_refs"] = "drive:fixture#page-1" if kind == "questions" else ["drive:fixture#page-1"]
    source = {"id": "fixture", "kind": source_kind, "readable": True,
              "snapshot_sha256": "a" * 64, "modified_time": "2026-09-20T00:00:00Z"}
    review = {"decision": "approved", "item_sha256": publication.fingerprint(item),
              "purpose": "bibliographic_metadata" if kind == "literature" else "learning_content",
              "reviewer": "fixture-reviewer", "reviewed_at": "2026-09-20",
              "sources": [{"source_id": "fixture", "snapshot_sha256": "a" * 64,
                           "modified_time": source["modified_time"], "locator": "page 1"}]}
    quality = {"item_sha256": publication.fingerprint(item), "source_support": "supported",
               "meaning": "consistent", "issues": [], "note": "Synthetic item matches the source",
               "reviewer": "fixture-reviewer", "reviewed_at": "2026-09-20",
               "checks": (["meaning", "definition", "examples", "ambiguity", "duplicates", "sources"]
                          if kind == "glossary" else
                          ["meaning", "answer", "explanation", "ambiguity", "duplicates", "sources"]),
               "sources": copy.deepcopy(review["sources"])}
    policy = publication.PublicationPolicy({}, {"fixture": source},
                                           {f"{kind}:fixture": review},
                                           {f"{kind}:fixture": quality})
    return item, source, review, policy


@pytest.mark.parametrize("kind", ["questions", "glossary", "literature"])
def test_corpus_arrival_and_approved_label_do_not_publish_without_review(kind):
    item, _, _, policy = reviewed(kind)
    policy.reviews.clear()
    assert policy.error(kind, item) == "repository_review_required"
    assert not policy.can_publish(kind, item)


@pytest.mark.parametrize("kind", ["questions", "glossary"])
def test_bibliography_cannot_support_learning_even_if_readable_and_reviewed(kind):
    item, _, _, policy = reviewed(kind, "bibliography")
    assert policy.error(kind, item) == "bibliography_is_not_knowledge"
    assert not policy.can_publish(kind, item)


def test_read_bibliography_supports_only_its_catalog_metadata():
    item, _, _, policy = reviewed("literature", "bibliography")
    assert policy.can_publish("literature", item)
    assert not policy.can_publish("glossary", item)


def test_new_question_requires_private_publication_even_after_exact_source_review():
    kind = "questions"
    item, _, _, policy = reviewed(kind)
    assert policy.error(kind, item) == "new_public_question_source_ref_forbidden"
    assert not policy.can_publish(kind, item)
    assert policy.error(kind, item, private_review=True) is None
    # Content fingerprints ignore JSON formatting/key order, not content changes.
    assert policy.error(kind, dict(reversed(list(item.items()))), private_review=True) is None


def test_historical_direct_ref_allowance_is_bound_to_exact_question_edition(monkeypatch):
    item, _, review, policy = reviewed("questions")
    monkeypatch.setitem(publication.HISTORICAL_DIRECT_REF_SHA256,
                        "questions:fixture", publication.fingerprint(item))
    assert policy.can_publish("questions", item)
    item["explanation"] = "A revised explanation"
    review["item_sha256"] = publication.fingerprint(item)
    policy.quality_reviews["questions:fixture"]["item_sha256"] = review["item_sha256"]
    assert policy.error("questions", item) == "new_public_question_source_ref_forbidden"


def test_new_glossary_item_cannot_publish_a_direct_drive_reference():
    item, _, _, policy = reviewed("glossary")
    assert policy.error("glossary", item) == "private_glossary_source_review_required"
    assert not policy.can_publish("glossary", item)


def test_existing_dopamine_glossary_uses_private_certificate():
    item = next(item for item in json.loads(
        (publication.ROOT / "content/glossary/psihofiziologiya.json").read_text(encoding="utf-8"))
        if item["id"] == "dopamine")
    policy = publication.load_policy()
    assert policy.can_publish("glossary", item)
    assert "source_refs" not in item
    assert policy.certificates["glossary:dopamine"]["item_sha256"] == publication.fingerprint(item)


@pytest.mark.parametrize("explanation", [None, "", "  "])
def test_new_approved_question_requires_an_explanation_at_publication_boundary(explanation):
    item, _, review, policy = reviewed()
    item["explanation"] = explanation
    review["item_sha256"] = publication.fingerprint(item)
    policy.quality_reviews["questions:fixture"]["item_sha256"] = review["item_sha256"]
    assert policy.error("questions", item) == "explanation_required"
    assert not policy.can_publish("questions", item)


@pytest.mark.parametrize("kind,field,text", [
    ("questions", "explanation", "Source: drive:private-file-id"),
    ("glossary", "definition", "See https://docs.google.com/document/d/private-file-id"),
    ("literature", "citation", "https://drive.google.com/file/d/private-file-id"),
])
def test_approved_public_text_cannot_expose_a_drive_location(kind, field, text):
    item, _, review, policy = reviewed(kind)
    if kind == "literature":
        item["source"] = {"id": "private-file-id", "title": "Reading list",
                          "locator": "Entry 1", "citation": text}
    else:
        item[field] = text
    digest = publication.fingerprint(item)
    review["item_sha256"] = digest
    policy.quality_reviews[f"{kind}:fixture"]["item_sha256"] = digest
    assert policy.error(kind, item) == "private_source_in_public_content"
    assert not policy.can_publish(kind, item)


def test_frozen_legacy_fingerprint_cannot_bypass_public_source_boundary():
    item, _, _, policy = reviewed()
    item["question"] = "Read source 1PrivateDriveFileIdentifier2345678"
    policy.sources["1PrivateDriveFileIdentifier2345678"] = policy.sources["fixture"]
    policy.legacy["questions:fixture"] = publication.fingerprint(item)
    assert policy.error("questions", item) == "private_source_in_public_content"
    assert not policy.can_publish("questions", item)


@pytest.mark.parametrize("kind", ["questions", "glossary"])
@pytest.mark.parametrize("failure", ["missing_quality", "changed_item_review", "changed_source", "missing_source"])
def test_frozen_legacy_learning_item_stops_when_source_evidence_is_stale(kind, failure):
    item, source, _, policy = reviewed(kind)
    policy.legacy[f"{kind}:fixture"] = publication.fingerprint(item)
    assert policy.can_publish(kind, item)
    quality = policy.quality_reviews[f"{kind}:fixture"]
    if failure == "missing_quality":
        policy.quality_reviews.clear()
        expected = "legacy_source_review_required"
    elif failure == "changed_item_review":
        quality["item_sha256"] = "b" * 64
        expected = "legacy_source_review_required"
    elif failure == "changed_source":
        source["snapshot_sha256"] = "b" * 64
        expected = "legacy_source_revision_changed_since_review"
    else:
        del policy.sources["fixture"]
        expected = "legacy_source_review_required"
    assert policy.error(kind, item) == expected
    assert not policy.can_publish(kind, item)


@pytest.mark.parametrize("kind", ["questions", "glossary"])
def test_frozen_legacy_learning_item_with_disputed_source_cannot_publish(kind):
    item, _, _, policy = reviewed(kind)
    policy.legacy[f"{kind}:fixture"] = publication.fingerprint(item)
    policy.quality_reviews[f"{kind}:fixture"]["source_support"] = "disputed"

    assert policy.error(kind, item) == "legacy_disputed_source_review"
    assert not policy.can_publish(kind, item)


@pytest.mark.parametrize("kind", ["questions", "glossary"])
@pytest.mark.parametrize("source_support", ["partial", "unconfirmed"])
def test_frozen_legacy_learning_item_with_incomplete_source_cannot_publish(kind, source_support):
    item, _, _, policy = reviewed(kind)
    policy.legacy[f"{kind}:fixture"] = publication.fingerprint(item)
    policy.quality_reviews[f"{kind}:fixture"]["source_support"] = source_support

    assert policy.error(kind, item) == "legacy_incomplete_source_review"
    assert not policy.can_publish(kind, item)


@pytest.mark.parametrize("kind", ["questions", "glossary"])
def test_frozen_legacy_explicit_drive_ref_must_match_quality_source(kind):
    item, source, _, policy = reviewed(kind)
    policy.legacy[f"{kind}:fixture"] = publication.fingerprint(item)
    policy.sources["other"] = {**source, "id": "other"}
    policy.quality_reviews[f"{kind}:fixture"]["sources"][0]["source_id"] = "other"

    assert policy.error(kind, item) == "legacy_source_reference_mismatch"
    assert not policy.can_publish(kind, item)


def test_private_bibliography_source_id_is_not_treated_as_display_text():
    item, _, review, policy = reviewed("literature", "bibliography")
    item["source"] = {"id": "1PrivateDriveFileIdentifier2345678",
                      "title": "Reading list", "locator": "Entry 1", "citation": "Book entry"}
    policy.sources[item["source"]["id"]] = policy.sources["fixture"]
    review["item_sha256"] = publication.fingerprint(item)
    assert policy.can_publish("literature", item)


@pytest.mark.parametrize("failure", ["missing", "partial", "ambiguous", "stale_item",
                                      "stale_source", "wrong_source", "missing_checks",
                                      "broad_locator"])
def test_new_learning_content_requires_current_supported_quality_review(failure):
    item, _, _, policy = reviewed()
    quality = policy.quality_reviews["questions:fixture"]
    if failure == "missing":
        policy.quality_reviews.clear()
    elif failure == "partial":
        quality["source_support"] = "partial"
    elif failure == "ambiguous":
        quality["meaning"] = "ambiguous"
    elif failure == "stale_item":
        quality["item_sha256"] = "b" * 64
    elif failure == "stale_source":
        quality["sources"][0]["snapshot_sha256"] = "b" * 64
    elif failure == "wrong_source":
        quality["sources"][0]["source_id"] = "other"
    elif failure == "broad_locator":
        quality["sources"][0]["locator"] = (
            "extracted text, Unicode characters (zero-based, end exclusive): 0:8564"
        )
    else:
        quality["checks"].remove("sources")
    assert policy.error("questions", item)
    assert not policy.can_publish("questions", item)


@pytest.mark.parametrize("failure", ["changed_item", "changed_source", "changed_revision", "unreadable", "missing_source",
                                      "no_locator", "broad_locator", "no_reviewer", "no_date", "wrong_purpose", "rejected", "duplicate", "empty"])
def test_review_does_not_survive_missing_or_changed_evidence(failure):
    item, source, review, policy = reviewed()
    if failure == "changed_item": item["question"] = "Different material"
    if failure == "changed_source": source["snapshot_sha256"] = "b" * 64
    if failure == "changed_revision": source["modified_time"] = "2026-09-21T00:00:00Z"
    if failure == "unreadable": source["readable"] = False
    if failure == "missing_source": policy.sources.clear()
    if failure == "no_locator": review["sources"][0]["locator"] = ""
    if failure == "broad_locator":
        review["sources"][0]["locator"] = "extracted text, Unicode characters (zero-based, end exclusive): 0:8564"
    if failure == "no_reviewer": review["reviewer"] = ""
    if failure == "no_date": review["reviewed_at"] = ""
    if failure == "wrong_purpose": review["purpose"] = "bibliographic_metadata"
    if failure == "rejected": review["decision"] = "rejected"
    if failure == "duplicate": review["sources"].append(copy.deepcopy(review["sources"][0]))
    if failure == "empty": review["sources"] = []
    assert policy.error("questions", item)
    assert not policy.can_publish("questions", item)


@pytest.mark.parametrize("ref", ["question:old", "supplied_snippet:unverified", "https://example.test/book", "LLM", "Obsidian", "drive:unreviewed"])
def test_unsupported_or_unreviewed_source_cannot_replace_corpus(ref):
    item, _, review, policy = reviewed()
    item["source_ref"] = ref
    review["item_sha256"] = publication.fingerprint(item)
    assert policy.error("questions", item) in {"direct_corpus_sources_required", "unreviewed_source_reference"}


@pytest.mark.parametrize("kind", ["questions", "glossary", "literature"])
@pytest.mark.parametrize("status", ["draft", "review", "deprecated", "placeholder"])
def test_preparation_can_validate_without_becoming_public(kind, status):
    item, _, review, policy = reviewed(kind)
    item["status"] = status
    review["item_sha256"] = publication.fingerprint(item)
    assert policy.error(kind, item) is None
    assert not policy.can_publish(kind, item)


def test_historical_baseline_preserved_and_current_learning_content_is_reviewed():
    policy = publication.load_policy()
    assert len(policy.legacy) == 716
    assert sum(review["purpose"] == "bibliographic_metadata" for review in policy.reviews.values()) == 143
    learning_reviews = {key for key, review in policy.reviews.items() if review["purpose"] == "learning_content"}
    assert learning_reviews == {
        "questions:m1_vnd_002", "questions:m2_exp_040",
        "questions:case_first_consultation_001",
        "questions:m2_exp_001", "questions:m2_exp_012", "questions:m2_exp_036",
        "questions:m2_exp_050", "questions:m2_exp_052", "questions:m2_exp_053",
        "questions:m2_exp_054", "questions:m2_exp_058", "questions:m2_exp_109",
    }
    assert "glossary:dopamine" in policy.certificates
    assert sum(source["kind"] == "bibliography" for source in policy.sources.values()) == 17
    # Reading learning sources for an audit must not silently approve derivatives.
    assert any(source["kind"] == "learning_material" for source in policy.sources.values())
    for kind, expected in [("questions", 595), ("glossary", 85), ("literature", 319)]:
        entries = [item for path in (publication.ROOT / "content" / kind).rglob("*.json")
                   for item in json.loads(path.read_text(encoding="utf-8"))]
        assert sum(policy.can_publish(kind, item) for item in entries) == expected
        assert publication.validate_publications(kind) == []
    current = [item for path in (publication.ROOT / "content/questions").rglob("*.json")
               for item in json.loads(path.read_text(encoding="utf-8"))
               if item.get("status") == "approved"]
    # Historical allowances remain frozen; every currently approved edition
    # now has an exact review, rather than relying on its legacy fingerprint.
    assert all(not policy.is_legacy("questions", item) for item in current)
    for item in current:
        assert policy.can_publish("questions", item)
        changed = copy.deepcopy(item)
        changed["explanation"] += " changed"
        assert not policy.can_publish("questions", changed), item["id"]
    # A frozen legacy allowance cannot stand in for an exact private review.
    for kind in ("questions", "glossary"):
        for path in (publication.ROOT / "content" / kind).rglob("*.json"):
            for item in json.loads(path.read_text(encoding="utf-8")):
                if item.get("status") != "approved":
                    continue
                assert policy.has_private_review(kind, item), (kind, item["id"])
                if kind == "glossary":
                    changed = copy.deepcopy(item)
                    changed["definition"] += " changed"
                    assert not policy.can_publish(kind, changed), item["id"]


def test_current_learning_reviews_do_not_use_bibliographies_as_knowledge():
    policy = publication.load_policy()
    quality = json.loads((publication.ROOT / "content" / "learning-quality-reviews.json")
                         .read_text(encoding="utf-8"))["items"]
    published = set()
    for kind in ("questions", "glossary"):
        for path in (publication.ROOT / "content" / kind).rglob("*.json"):
            for item in json.loads(path.read_text(encoding="utf-8")):
                if policy.can_publish(kind, item):
                    published.add(f"{kind}:{item['id']}")
    assert published <= quality.keys() | policy.certificates.keys()
    for key, review in quality.items():
        if not key.startswith(("questions:", "glossary:")):
            continue
        for evidence in review["sources"]:
            source = policy.sources[evidence["source_id"]]
            assert source["kind"] == "learning_material", key


@pytest.mark.parametrize("kind", ["glossary", "literature"])
@pytest.mark.parametrize("status", ["draft", "review", "approved", "deprecated"])
def test_actual_runtime_loader_excludes_unreviewed_new_content(tmp_path, monkeypatch, kind, status):
    source = next((publication.ROOT / "content" / kind).glob("*.json"))
    entries = json.loads(source.read_text(encoding="utf-8"))
    new = copy.deepcopy(entries[0])
    new.update(id="unreviewed_new_entry", status=status)
    (tmp_path / source.name).write_text(json.dumps(entries + [new]), encoding="utf-8")
    if kind == "glossary":
        monkeypatch.setattr(glossary, "_GLOSSARY_DIR", tmp_path)
        ids = [entry.id for entry in glossary.load_glossary_entries(source.stem)]
    else:
        monkeypatch.setattr(literature, "LITERATURE_DIR", tmp_path)
        ids = [entry["id"] for entry in literature.load_literature_items()]
    policy = publication.load_policy()
    assert ids == [entry["id"] for entry in sorted(entries, key=lambda entry: entry.get("global_order", 0))
                   if policy.can_publish(kind, entry)]
    assert "unreviewed_new_entry" not in ids


@pytest.mark.parametrize("failure", ["legacy_append", "wrong_root", "duplicate_source", "invalid_readable", "missing_fingerprint"])
def test_registry_corruption_fails_closed(tmp_path, monkeypatch, failure):
    target = tmp_path / "content"
    target.mkdir()
    for filename in ("legacy-publication-baseline.json", "source-corpus.json", "publication-reviews.json",
                     "learning-quality-reviews.json"):
        shutil.copyfile(publication.ROOT / "content" / filename, target / filename)
    filename = "legacy-publication-baseline.json" if failure == "legacy_append" else "source-corpus.json"
    path = target / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    if failure == "legacy_append": data["items"]["questions:forged"] = "a" * 64
    if failure == "wrong_root": data["corpus_root_id"] = "another-corpus"
    if failure == "duplicate_source": data["sources"].append(data["sources"][0])
    if failure == "invalid_readable": data["sources"][0]["readable"] = "true"
    if failure == "missing_fingerprint": data["sources"][0].pop("snapshot_sha256")
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(publication, "ROOT", tmp_path)
    publication.load_policy.cache_clear()
    try:
        assert publication.validate_publications("questions") == ["Publication registry unavailable or invalid"]
    finally:
        publication.load_policy.cache_clear()


def test_checkout_line_endings_do_not_change_frozen_baseline(tmp_path, monkeypatch):
    expected = publication.load_policy().legacy
    target = tmp_path / "content"
    target.mkdir()
    for filename in ("legacy-publication-baseline.json", "source-corpus.json", "publication-reviews.json",
                     "learning-quality-reviews.json"):
        original = (publication.ROOT / "content" / filename).read_text(encoding="utf-8")
        (target / filename).write_bytes(original.replace("\n", "\r\n").encode("utf-8"))
    monkeypatch.setattr(publication, "ROOT", tmp_path)
    publication.load_policy.cache_clear()
    try:
        assert publication.load_policy().legacy == expected
    finally:
        publication.load_policy.cache_clear()


def test_canonical_seed_refuses_unreviewed_approved_content_before_db_write(tmp_path, monkeypatch):
    item, _, _, policy = reviewed()
    policy.reviews.clear()
    question_dir = tmp_path / "content/questions/module1"
    question_dir.mkdir(parents=True)
    (question_dir / "fixture.json").write_text(json.dumps([item]), encoding="utf-8")
    db_path = tmp_path / "exists.sqlite3"
    db_path.touch()
    monkeypatch.setattr(publication, "ROOT", tmp_path)
    monkeypatch.setattr(publication, "load_policy", lambda: policy)
    monkeypatch.setattr(seed_questions, "resolve_db_path", lambda: str(db_path))
    monkeypatch.setattr(seed_questions, "get_connection", lambda *a: pytest.fail("Unreviewed seed reached the DB"))
    assert seed_questions.main() == 1
    assert db_path.stat().st_size == 0


def test_canonical_seed_imports_reviewed_additional_course(tmp_path, monkeypatch):
    from contextlib import closing
    from app.db import get_connection

    policy = publication.load_policy()
    item = json.loads((publication.ROOT / "content/questions/other/turning_point.json").read_text(encoding="utf-8"))[0]
    assert policy.can_publish("questions", item)
    schema = (publication.ROOT / "sql/schema.sql").read_text(encoding="utf-8")
    numbered = tmp_path / "content/questions/module1"
    additional = tmp_path / "content/questions/other"
    numbered.mkdir(parents=True)
    additional.mkdir()
    (numbered / "empty.json").write_text("[]", encoding="utf-8")
    (additional / "reviewed.json").write_text(json.dumps([item]), encoding="utf-8")
    db_path = tmp_path / "seed.sqlite3"
    from app.identity_schema import migrate_identity_schema
    from app.learning_schema import migrate_learning_schema
    with closing(get_connection(str(db_path))) as conn, conn:
        conn.executescript(schema)
        migrate_identity_schema(conn)
        migrate_learning_schema(conn)
    monkeypatch.setattr(publication, "ROOT", tmp_path)
    monkeypatch.setattr(publication, "load_policy", lambda: policy)
    monkeypatch.setattr(seed_questions, "__file__", str(tmp_path / "scripts/seed_questions.py"))
    monkeypatch.setattr(seed_questions, "resolve_db_path", lambda: str(db_path))
    monkeypatch.setattr(seed_questions, "projected_questions", lambda: [])
    assert seed_questions.main() == 0
    with closing(get_connection(str(db_path))) as conn:
        row = conn.execute("SELECT external_id,status FROM questions").fetchone()
        assert tuple(row) == (item["id"], "approved")
