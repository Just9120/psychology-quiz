from contextlib import contextmanager
import json
from types import SimpleNamespace

import pytest

from app import owner_content
from app.web_api import _dispatch
from app.web_auth import AuthError
from scripts.owner_source_summary import build
from tests.test_web_auth import web, post, register, login
from tests.test_attempt_content import bank


def test_saved_input_summary_is_explicit_and_cannot_smuggle_private_observation_text(tmp_path, monkeypatch):
    current = {"schema_version": 1, "root_id": "private-root", "folders": {"private-root": [{
        "page_token": None, "next_page_token": None,
        "children": [{"id": "private-id", "title": "Private", "mime_type": "text/plain",
                      "modified_time": "2026-01-01T00:00:00Z", "file_or_folder": "file", "parent_ids": ["private-root"]}],
    }]}}
    value = build(current, {}, "2026-01-02T00:00:00Z", saved_inputs=True)
    path = tmp_path / "summary.json"
    monkeypatch.setenv("OWNER_SOURCE_SUMMARY_PATH", str(path))
    path.write_text(json.dumps(value), encoding="utf-8")
    returned = owner_content.source_summary()
    assert returned["state"] == "PARTIAL" and returned["observation_basis"] == "saved_inputs"
    assert "private-id" not in json.dumps(returned) and "Private" not in json.dumps(returned)
    value["observation_basis"] = "private-source-locator"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert owner_content.source_summary() == {"state": "UNSET", "reason": "source_snapshot_invalid"}


def test_owner_content_requires_session_csrf_and_does_not_return_source_ids(web, monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_SOURCE_SUMMARY_PATH", str(tmp_path / "absent.json"))
    assert post(web, "owner/content").status_code == 401
    register(web)
    csrf = login(web)
    assert post(web, "owner/content").status_code == 403
    result = post(web, "owner/content", csrf=csrf)
    assert result.status_code == 200
    data = result.json()
    assert data["sources"]["state"] == "UNSET"
    assert data["topics"]
    assert not any(field in json.dumps(data) for field in ("source_id", "snapshot_sha256", "source_ref", "telegram_user_id", "owner@example.test"))


@pytest.mark.parametrize("action", ["owner/content", "owner/stats"])
def test_nonowner_cannot_reach_content_loader(monkeypatch, action):
    @contextmanager
    def transaction():
        yield object()
    auth = SimpleNamespace(transaction=transaction, settings=SimpleNamespace(owner_email="owner@example.test"),
                           authenticate=lambda *args, **kwargs: {"email": "other@example.test"})
    monkeypatch.setattr(owner_content, "dashboard", lambda conn: pytest.fail("nonowner reached loader"))
    from app import owner_stats
    monkeypatch.setattr(owner_stats, "get_owner_period_stats", lambda *args: pytest.fail("nonowner reached analytics"))
    with pytest.raises(AuthError, match="forbidden"):
        _dispatch(auth, action, {}, "token", "csrf")


def test_source_snapshot_is_partial_allowlisted_and_rejects_inconsistent_totals(tmp_path, monkeypatch):
    current = {"schema_version": 1, "root_id": "private-root", "folders": {"private-root": [{
        "page_token": None, "next_page_token": None,
        "children": [{"id": "private-id", "title": "Private", "mime_type": "text/plain", "modified_time": "2026-01-01T00:00:00Z", "file_or_folder": "file", "parent_ids": ["private-root"]}],
    }]}}
    record = {"revision": ["2026-01-01T00:00:00Z", "Private", "text/plain"], "review_state": "pending_review"}
    value = build(current, {"private-id": record}, "2026-01-02T00:00:00Z")
    assert value["state"] == "PARTIAL" and value["processing"] == {"pending_review": 1}
    assert "private-id" not in json.dumps(value)
    path = tmp_path / "summary.json"
    value["private_notes"] = "must not leave operator storage"
    path.write_text(json.dumps(value), encoding="utf-8")
    monkeypatch.setenv("OWNER_SOURCE_SUMMARY_PATH", str(path))
    result = owner_content.source_summary()
    assert "private_notes" not in result
    assert result["processing_records"] == 1
    value["files"] = 2
    path.write_text(json.dumps(value), encoding="utf-8")
    assert owner_content.source_summary()["state"] == "UNSET"


def test_topic_coverage_distinguishes_empty_kinds_unknown_notes_and_deduplicated_books(monkeypatch):
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.executescript("""CREATE TABLE categories(id INTEGER,slug TEXT,name TEXT);
        CREATE TABLE questions(category_id INTEGER,kind TEXT,status TEXT);
        INSERT INTO categories VALUES(1,'imported-category-slug','One'),(2,'outside','one');
        INSERT INTO questions VALUES(1,'case','approved'),(1,'theory','draft'),(2,'theory','approved');""")
    monkeypatch.setattr(owner_content, "load_topic_registry", lambda: {"one": {"title": "One", "module": "module1", "order": 1}})
    monkeypatch.setattr(owner_content, "load_glossary_entries", lambda topic: None)
    monkeypatch.setattr(owner_content, "load_literature_items", lambda: [{"topic_id": "one", "work_id": "book"}, {"topic_id": "one", "work_id": "book"}])
    monkeypatch.setattr(owner_content, "source_summary", lambda: {"state": "UNSET"})
    try:
        data = owner_content.dashboard(conn)
    finally:
        conn.close()
    topic = data["topics"][0]
    assert topic["questions"] == 1 and topic["kinds"]["case"] == 1
    assert topic["gaps"] == ["theory", "glossary"]
    assert topic["glossary_terms"] is None and topic["notes_state"] == "UNSET"
    assert topic["literature_works"] == 1 and data["unmapped_questions"] == 1


def test_lesson_graph_requires_exact_question_edition_and_preserves_known_holds(monkeypatch, tmp_path):
    from app.content_publication import fingerprint
    current = {"schema_version": 1, "root_id": "private-root", "folders": {"private-root": [{
        "page_token": None, "next_page_token": None,
        "children": [{"id": "private-source", "title": "Lecture", "mime_type": "text/plain", "modified_time": "2026-01-01T00:00:00Z", "file_or_folder": "file", "parent_ids": ["private-root"]}],
    }]}}
    source = {"id": "private-source", "title": "Lecture", "modified_time": "2026-01-01T00:00:00Z", "snapshot_sha256": "a" * 64, "kind": "learning_material", "readable": True, "snapshot_kind": "extracted_text", "corpus_path": "Lecture", "reviewed_at": "2026-01-02", "reviewer": "private-editor"}
    registry = {"schema_version": 1, "corpus_root_id": "private-root", "sources": [source]}
    item = {"id": "question", "kind": "case", "text": "Current edition"}
    topic = "t_aaaaaaaaaaaa"
    curriculum = {"schema_version": 1, "disciplines": {"one": {"title": "Discipline"}}, "topics": {topic: {"title": "Public lesson", "discipline_id": "one", "source": {"source_id": source["id"], "modified_time": source["modified_time"], "snapshot_sha256": source["snapshot_sha256"]}}}, "editions": {"b" * 64: {"external_id": item["id"], "item_sha256": fingerprint(item), "topic_id": topic}}}
    processed = {source["id"]: {"revision": [source["modified_time"], source["title"], "text/plain"], "review_state": "pending_review", "conflict_hold": {"reason": "private objection", "locator": "characters:1:2", "related_source_ids": []}}}
    result = build(current, processed, "2026-01-02T00:00:00Z", registry=registry, curriculum=curriculum, published_items=[item])
    lesson = result["coverage"]["lessons"][0]
    assert lesson["known_hold"] and lesson["source_metadata_current"]
    assert lesson["kinds"] == {"theory": 0, "glossary": 0, "case": 1}
    assert not any(private in json.dumps(result) for private in ("private-source", "private-editor", "private objection", "characters:"))
    changed = build(current, processed, "2026-01-02T00:00:00Z", registry=registry, curriculum=curriculum, published_items=[{**item, "text": "Changed edition"}])
    assert changed["coverage"]["lessons"][0]["kinds"]["case"] == 0
    assert changed["coverage"]["unmapped_published_questions"] == 1
    monkeypatch.setattr(owner_content, "load_catalog", lambda: curriculum)
    result["coverage"]["lessons"][0]["title"] = "private-source"
    result["coverage"]["lessons"][0]["source_ref"] = "private-source"
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    monkeypatch.setenv("OWNER_SOURCE_SUMMARY_PATH", str(path))
    returned = owner_content.source_summary()
    assert returned["coverage"]["lessons"][0]["title"] == "Public lesson"
    assert "private-source" not in json.dumps(returned)


def test_prepared_notes_require_current_review_and_return_only_aggregate_counts(monkeypatch):
    from copy import deepcopy
    from scripts.obsidian_vault import VaultError
    from tests.test_obsidian_vault import evidence, note, SOURCE, REVISION, DIGEST

    _, processed = evidence()
    current = {"schema_version": 1, "root_id": "private-root", "folders": {
        "private-root": [{"page_token": None, "next_page_token": None, "children": [{
            "id": SOURCE, "title": REVISION[1], "mime_type": REVISION[2],
            "modified_time": REVISION[0], "file_or_folder": "file", "parent_ids": ["private-root"]}]}]}}
    registry = {"schema_version": 1, "corpus_root_id": "private-root", "sources": [{
        "id": SOURCE, "title": REVISION[1], "modified_time": REVISION[0],
        "snapshot_sha256": DIGEST, "kind": "learning_material", "readable": True,
        "snapshot_kind": "file_bytes", "corpus_path": "Private lecture",
        "reviewed_at": "2026-09-29", "reviewer": "private-editor"}]}
    key = "t_aaaaaaaaaaaa"
    curriculum = {"schema_version": 1, "disciplines": {"one": {"title": "Discipline"}},
                  "topics": {key: {"title": "Public lesson", "discipline_id": "one",
                      "source": {"source_id": SOURCE, "modified_time": REVISION[0], "snapshot_sha256": DIGEST}}},
                  "editions": {}}
    manifest = {"schema_version": 1, "notes": [note(body="Private body must not appear") ]}
    inputs = dict(registry=registry, curriculum=curriculum, published_items=[])
    result = build(current, processed, "2026-09-30T00:00:00Z", note_manifest=manifest, **inputs)
    lesson = result["coverage"]["lessons"][0]
    assert lesson["notes_state"] == "PREPARED" and lesson["notes"] == 1
    assert result["coverage"]["prepared_notes_unmapped"] == 0
    assert not any(value in json.dumps(result) for value in (SOURCE, "Private body", "private-editor", "attention", "стр. 2"))
    monkeypatch.setattr(owner_content, "load_catalog", lambda: curriculum)
    result["coverage"]["lessons"][0]["private_body"] = "private"
    returned = owner_content._coverage(result["coverage"])
    assert returned["lessons"][0]["notes"] == 1 and "private_body" not in json.dumps(returned)
    unchanged = build(current, processed, "2026-09-30T00:00:00Z", **inputs)
    assert unchanged["coverage"]["lessons"][0]["notes"] is None
    stale = deepcopy(processed)
    stale[SOURCE]["review_state"] = "pending_review"
    stale[SOURCE].pop("source_kind")
    stale[SOURCE].pop("source_kind_review")
    with pytest.raises(VaultError, match="source_not_current_reviewed"):
        build(current, stale, "2026-09-30T00:00:00Z", note_manifest=manifest, **inputs)
    mismatched = deepcopy(curriculum)
    mismatched["topics"][key]["source"]["snapshot_sha256"] = "f" * 64
    # A note reviewed against another digest cannot acquire this lesson.
    from scripts.owner_source_summary import prepared_note_coverage
    coverage = deepcopy(result["coverage"])
    prepared_note_coverage(coverage, manifest, current, processed, mismatched)
    assert coverage["lessons"][0]["notes"] == 0 and coverage["prepared_notes_unmapped"] == 1
    invalid = deepcopy(result["coverage"])
    invalid["lessons"][0]["known_hold"] = True
    with pytest.raises(ValueError, match="invalid_coverage"):
        owner_content._coverage(invalid)
    result["coverage"]["lessons"][0]["notes"] = "private text"
    with pytest.raises(ValueError, match="invalid_coverage"):
        owner_content._coverage(result["coverage"])


def test_glossary_coverage_requires_current_edition_source_and_review_without_leaking_refs(monkeypatch):
    from copy import deepcopy
    from app.content_publication import fingerprint
    from app.source_inventory import InventoryError
    from scripts.owner_source_summary import glossary_coverage

    key = "t_aaaaaaaaaaaa"
    source = {"source_id": "private-source", "modified_time": "2026-01-01T00:00:00Z", "snapshot_sha256": "a" * 64}
    curriculum = {"topics": {key: {"title": "Lesson", "discipline_id": "one", "source": source}},
                  "disciplines": {"one": {"title": "Discipline"}}}
    lesson = {"id": key, "kinds": {"theory": 0, "glossary": 0, "case": 0},
              "source_metadata_current": True, "known_hold": False, "processing_state": "processed",
              "notes": None, "notes_state": "UNSET", "glossary_terms": None}
    coverage = {"lessons": [lesson], "tracked_sources": 1, "untracked_files": 0,
                "source_metadata": {"current": 1}, "unmapped_published_questions": 0}
    term = {"id": "term", "status": "approved", "term": "Definition"}
    unmatched = {"id": "other", "status": "approved", "term": "Other definition"}
    policy = SimpleNamespace(can_publish=lambda kind, item: kind == "glossary" and item["status"] == "approved",
        quality_reviews={"glossary:term": {"item_sha256": fingerprint(term), "source_support": "supported",
                                          "sources": [deepcopy(source), deepcopy(source)]}})
    glossary_coverage(coverage, [term, unmatched], policy, curriculum)
    assert lesson["glossary_terms"] == 1 and coverage["unmapped_published_glossary"] == 1
    assert "private-source" not in json.dumps(coverage)
    monkeypatch.setattr(owner_content, "load_catalog", lambda: curriculum)
    assert owner_content._coverage(coverage)["lessons"][0]["glossary_terms"] == 1
    for change in ({"known_hold": True}, {"source_metadata_current": False}, {"processing_state": "pending_review"}):
        stale = deepcopy(coverage)
        stale["lessons"][0].update(change)
        with pytest.raises(ValueError, match="invalid_coverage"):
            owner_content._coverage(stale)
        glossary_coverage(stale, [term], policy, curriculum)
        assert stale["lessons"][0]["glossary_terms"] == 0 and stale["unmapped_published_glossary"] == 1
    for field in ("modified_time", "snapshot_sha256", "source_id"):
        changed = deepcopy(curriculum)
        changed["topics"][key]["source"][field] = "different"
        glossary_coverage(coverage, [term], policy, changed)
        assert lesson["glossary_terms"] == 0 and coverage["unmapped_published_glossary"] == 1
    glossary_coverage(coverage, [{**term, "term": "Changed definition"}], policy, curriculum)
    assert lesson["glossary_terms"] == 0
    with pytest.raises(InventoryError, match="duplicate_glossary_derivative"):
        glossary_coverage(coverage, [term, term], policy, curriculum)
    with pytest.raises(InventoryError, match="published_glossary_required"):
        glossary_coverage(coverage, [{**term, "status": "draft"}], policy, curriculum)
    lesson["glossary_terms"] = True
    with pytest.raises(ValueError, match="invalid_coverage"):
        owner_content._coverage(coverage)


def test_owner_summary_cli_accepts_only_private_registry_and_preserves_pending_state(tmp_path, monkeypatch, capsys):
    import subprocess
    from scripts import owner_source_summary as summary
    (tmp_path / "content").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    source_id = "private-glossary-id-123456789"
    current = {"schema_version": 1, "root_id": "private-root", "folders": {"private-root": [{
        "page_token": None, "next_page_token": None, "children": [{
            "id": source_id, "title": "Glossary", "mime_type": "text/plain",
            "modified_time": "2026-01-01T00:00:00Z", "file_or_folder": "file",
            "parent_ids": ["private-root"]}]}]}}
    source = {"id": source_id, "title": "Glossary", "modified_time": "2026-01-01T00:00:00Z",
              "snapshot_sha256": "a" * 64, "kind": "learning_material", "readable": True,
              "snapshot_kind": "extracted_text", "corpus_path": "Glossary",
              "reviewed_at": "2026-01-02", "reviewer": "editor", "discipline_id": "one"}
    private = {"schema_version": 1, "corpus_root_id": "private-root", "sources": [source]}
    public = {"schema_version": 1, "corpus_root_id": "private-root", "sources": []}
    processed = {source_id: {"revision": ["2026-01-01T00:00:00Z", "Glossary", "text/plain"],
                            "review_state": "pending_review", "snapshot_kind": "extracted_text",
                            "snapshot_sha256": "a" * 64}}
    paths = {name: tmp_path / "data" / name for name in ("current.json", "processed.json", "registry.json")}
    for name, value in (("current.json", current), ("processed.json", processed), ("registry.json", private)):
        paths[name].write_text(json.dumps(value), encoding="utf-8")
        paths[name].chmod(0o600)
    (tmp_path / "content/source-corpus.json").write_text(json.dumps(public), encoding="utf-8")
    monkeypatch.setattr(summary, "ROOT", tmp_path)
    monkeypatch.setattr(summary, "load_reviewed_catalog", lambda: {
        "schema_version": 1, "disciplines": {"one": {"title": "Discipline"}}, "topics": {}, "editions": {}})
    monkeypatch.setattr(summary, "published_questions", lambda: [])
    monkeypatch.setattr(summary, "published_glossary", lambda policy: [])
    monkeypatch.setattr(summary, "load_policy", lambda: object())
    output = tmp_path / "data/summary.json"
    args = ["--current", str(paths["current.json"]), "--processed", str(paths["processed.json"]),
            "--observed-at", "2026-01-02T00:00:00Z", "--private-registry", str(paths["registry.json"]),
            "--output", str(output)]
    assert summary.main(args) == 1
    assert "private_registry_requires_reviewed" in capsys.readouterr().out
    assert not output.exists()
    assert summary.main([*args, "--reviewed"]) == 0
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["coverage"]["tracked_sources"] == 1
    assert value["coverage"]["untracked_files"] == 0 and value["coverage"]["lessons"] == []
    assert value["processing"] == {"pending_review": 1} and value["known_holds"] == 0
    assert source_id not in output.read_text(encoding="utf-8") + capsys.readouterr().out
    assert json.loads((tmp_path / "content/source-corpus.json").read_text(encoding="utf-8")) == public
    assert json.loads(paths["processed.json"].read_text(encoding="utf-8")) == processed
    private["sources"][0].pop("discipline_id")
    paths["registry.json"].write_text(json.dumps(private), encoding="utf-8")
    paths["registry.json"].chmod(0o600)
    topics = tmp_path / "data/topics.json"
    topics.write_text(json.dumps({"schema_version": 1, "corpus_root_id": "private-root", "topics": {
        "t_aaaaaaaaaaaa": {"title": "Unreleased private lesson", "discipline_id": "one", "source": {
            "source_id": source_id, "modified_time": source["modified_time"], "snapshot_sha256": source["snapshot_sha256"]}}}}), encoding="utf-8")
    topics.chmod(0o600)
    private_output = tmp_path / "data/private-summary.json"
    private_args = [str(private_output) if part == str(output) else part for part in args]
    assert summary.main([*private_args, "--private-topics", str(topics)]) == 1
    assert "private_registry_requires_reviewed" in capsys.readouterr().out
    assert not private_output.exists()
    assert summary.main([*private_args, "--reviewed", "--private-topics", str(topics)]) == 0
    private_value = json.loads(private_output.read_text(encoding="utf-8"))
    assert private_value["coverage"]["lessons"] == []
    assert private_value["coverage"]["unreleased_lessons"] == {
        "total": 1, "processing": {"pending_review": 1}, "metadata_current": 1, "known_holds": 0}
    assert not any(value in private_output.read_text(encoding="utf-8") for value in
                   (source_id, "Unreleased private lesson", "t_aaaaaaaaaaaa"))
    private["sources"].append(source)
    paths["registry.json"].write_text(json.dumps(private), encoding="utf-8")
    paths["registry.json"].chmod(0o600)
    duplicate_output = tmp_path / "data/duplicate.json"
    duplicate_args = [str(duplicate_output) if part == str(output) else part for part in args]
    assert summary.main([*duplicate_args, "--reviewed"]) == 1
    assert "duplicate_or_invalid_private_source" in capsys.readouterr().out
    assert not duplicate_output.exists()
    outside = tmp_path / "public-registry.json"
    outside.write_text(json.dumps(private), encoding="utf-8")
    outside_args = [str(outside) if part == str(paths["registry.json"]) else part for part in duplicate_args]
    assert summary.main([*outside_args, "--reviewed"]) == 1
    assert "private_registry_requires_ignored_data_json" in capsys.readouterr().out
    assert not duplicate_output.exists()


def test_unreleased_lesson_summary_is_numeric_and_rejects_private_fields(monkeypatch):
    from copy import deepcopy
    from scripts.owner_source_summary import build
    from tests.test_obsidian_vault import evidence, SOURCE, REVISION, DIGEST
    _, processed = evidence()
    current = {"schema_version": 1, "root_id": "private-root", "folders": {
        "private-root": [{"page_token": None, "next_page_token": None, "children": [{
            "id": SOURCE, "title": REVISION[1], "mime_type": REVISION[2],
            "modified_time": REVISION[0], "file_or_folder": "file", "parent_ids": ["private-root"]}]}]}}
    registry = {"schema_version": 1, "corpus_root_id": "private-root", "sources": [{
        "id": SOURCE, "title": REVISION[1], "modified_time": REVISION[0],
        "snapshot_sha256": DIGEST, "kind": "learning_material", "readable": True,
        "snapshot_kind": "file_bytes", "corpus_path": "Private lecture",
        "reviewed_at": "2026-09-29", "reviewer": "private-editor"}]}
    public = {"schema_version": 1, "disciplines": {"one": {"title": "Discipline"}}, "topics": {}, "editions": {}}
    key = "t_aaaaaaaaaaaa"
    curriculum = {**public, "topics": {key: {"title": "Unreleased private title", "discipline_id": "one",
        "source": {"source_id": SOURCE, "modified_time": REVISION[0], "snapshot_sha256": DIGEST}}}}
    held = deepcopy(processed)
    held[SOURCE]["review_state"] = "pending_review"
    held[SOURCE].pop("source_kind", None)
    held[SOURCE].pop("source_kind_review", None)
    held[SOURCE]["conflict_hold"] = {"reason": "private objection", "locator": "page:1", "related_source_ids": []}
    value = build(current, held, "2026-09-30T00:00:00Z", registry=registry,
                  curriculum=curriculum, published_items=[], public_topic_ids=set())
    coverage = value["coverage"]
    assert coverage["lessons"] == []
    expected = {"total": 1, "processing": {"pending_review": 1}, "metadata_current": 1, "known_holds": 1}
    assert coverage["unreleased_lessons"] == expected
    assert not any(private in json.dumps(value) for private in (SOURCE, key, "Unreleased private title", "private objection", DIGEST))
    monkeypatch.setattr(owner_content, "load_catalog", lambda: public)
    assert owner_content._coverage(coverage)["unreleased_lessons"] == expected
    for changed in ({**expected, "total": 2}, {**expected, "known_holds": 2},
                    {**expected, "metadata_current": True}, {**expected, "source_id": SOURCE},
                    {**expected, "processing": {SOURCE: 1}}):
        invalid = {**coverage, "unreleased_lessons": changed}
        with pytest.raises(ValueError, match="invalid_coverage"):
            owner_content._coverage(invalid)
    with pytest.raises(Exception, match="invalid_public_topics"):
        build(current, held, "2026-09-30T00:00:00Z", registry=registry,
              curriculum=curriculum, published_items=[], public_topic_ids={"missing"})


def test_release_bundles_safe_summary_without_operator_file(monkeypatch):
    monkeypatch.delenv("OWNER_SOURCE_SUMMARY_PATH", raising=False)
    path = owner_content.ROOT / "content" / "owner-source-summary.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    result = owner_content.source_summary()
    assert result["state"] == "PARTIAL" and result["observation_basis"] == "saved_inputs"
    assert result["files"] == sum(result["processing"].values()) > 0
    assert set(raw) == {"schema_version", "state", "captured_at", "files", "folders",
                        "processing", "processing_records", "known_holds",
                        "observation_basis", "coverage"}
    coverage = raw["coverage"]
    assert set(coverage) <= {"tracked_sources", "untracked_files", "source_metadata",
                             "lessons", "unreleased_lessons", "prepared_notes_unmapped",
                             "unmapped_published_glossary", "unmapped_published_questions"}
    for lesson in coverage["lessons"]:
        assert set(lesson) == {"id", "kinds", "source_metadata_current", "processing_state",
                               "known_hold", "glossary_terms", "notes", "notes_state"}
    # Runtime validates nested counts and public topic identifiers; the release
    # file cannot carry private prose, source locators or operator identities.
    expected = {key: raw[key] for key in raw if key != "schema_version"}
    expected["coverage"] = owner_content._coverage(coverage)
    assert result == expected


def test_explicit_operator_path_never_falls_back_to_release_summary(tmp_path, monkeypatch):
    path = tmp_path / "operator.json"
    monkeypatch.setenv("OWNER_SOURCE_SUMMARY_PATH", str(path))
    assert owner_content.source_summary() == {"state": "UNSET", "reason": "source_snapshot_not_installed"}
    path.write_text("{}", encoding="utf-8")
    assert owner_content.source_summary() == {"state": "UNSET", "reason": "source_snapshot_invalid"}
