import copy
import json
from pathlib import Path
import shutil

import pytest

from app import content_publication as publication, glossary, literature
from scripts import seed_questions


def reviewed(kind="questions", source_kind="learning_material"):
    item = {"id": "fixture", "status": "approved", "question": "Synthetic material"}
    item["source_ref" if kind == "questions" else "source_refs"] = "drive:fixture#page-1" if kind == "questions" else ["drive:fixture#page-1"]
    source = {"id": "fixture", "kind": source_kind, "readable": True,
              "snapshot_sha256": "a" * 64, "modified_time": "2026-09-20T00:00:00Z"}
    review = {"decision": "approved", "item_sha256": publication.fingerprint(item),
              "purpose": "bibliographic_metadata" if kind == "literature" else "learning_content",
              "reviewer": "fixture-reviewer", "reviewed_at": "2026-09-20",
              "sources": [{"source_id": "fixture", "snapshot_sha256": "a" * 64,
                           "modified_time": source["modified_time"], "locator": "page 1"}]}
    policy = publication.PublicationPolicy({}, {"fixture": source}, {f"{kind}:fixture": review})
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


@pytest.mark.parametrize("kind", ["questions", "glossary"])
def test_exact_review_of_readable_learning_material_allows_publication(kind):
    item, _, _, policy = reviewed(kind)
    assert policy.can_publish(kind, item)
    # Content fingerprints ignore JSON formatting/key order, not content changes.
    assert policy.can_publish(kind, dict(reversed(list(item.items()))))


@pytest.mark.parametrize("failure", ["changed_item", "changed_source", "changed_revision", "unreadable", "missing_source",
                                      "no_locator", "no_reviewer", "no_date", "wrong_purpose", "rejected", "duplicate", "empty"])
def test_review_does_not_survive_missing_or_changed_evidence(failure):
    item, source, review, policy = reviewed()
    if failure == "changed_item": item["question"] = "Different material"
    if failure == "changed_source": source["snapshot_sha256"] = "b" * 64
    if failure == "changed_revision": source["modified_time"] = "2026-09-21T00:00:00Z"
    if failure == "unreadable": source["readable"] = False
    if failure == "missing_source": policy.sources.clear()
    if failure == "no_locator": review["sources"][0]["locator"] = ""
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


def test_current_legacy_counts_preserved_without_source_certification():
    policy = publication.load_policy()
    assert len(policy.legacy) == 716
    assert sum(review["purpose"] == "bibliographic_metadata" for review in policy.reviews.values()) == 130
    learning_reviews = {key for key, review in policy.reviews.items() if review["purpose"] == "learning_content"}
    assert learning_reviews == {"questions:m1_vnd_002", "questions:m2_exp_040", "glossary:dopamine"}
    assert sum(source["kind"] == "bibliography" for source in policy.sources.values()) == 14
    # Reading learning sources for an audit must not silently approve derivatives.
    assert any(source["kind"] == "learning_material" for source in policy.sources.values())
    for kind, expected in [("questions", 575), ("glossary", 99), ("literature", 130)]:
        entries = [item for path in (publication.ROOT / "content" / kind).rglob("*.json")
                   for item in json.loads(path.read_text(encoding="utf-8"))]
        assert sum(policy.can_publish(kind, item) for item in entries) == expected
        assert publication.validate_publications(kind) == []
    item = json.loads(next((publication.ROOT / "content/questions").rglob("*.json")).read_text(encoding="utf-8"))[0]
    assert policy.is_legacy("questions", item)
    item["explanation"] += " changed"
    assert not policy.can_publish("questions", item)


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
    assert ids == [entry["id"] for entry in sorted(entries, key=lambda entry: entry.get("global_order", 0))]
    assert "unreviewed_new_entry" not in ids


@pytest.mark.parametrize("failure", ["legacy_append", "wrong_root", "duplicate_source", "invalid_readable", "missing_fingerprint"])
def test_registry_corruption_fails_closed(tmp_path, monkeypatch, failure):
    target = tmp_path / "content"
    target.mkdir()
    for filename in ("legacy-publication-baseline.json", "source-corpus.json", "publication-reviews.json"):
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
    for filename in ("legacy-publication-baseline.json", "source-corpus.json", "publication-reviews.json"):
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
