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


def test_nonowner_cannot_reach_content_loader(monkeypatch):
    @contextmanager
    def transaction():
        yield object()
    auth = SimpleNamespace(transaction=transaction, settings=SimpleNamespace(owner_email="owner@example.test"),
                           authenticate=lambda *args, **kwargs: {"email": "other@example.test"})
    monkeypatch.setattr(owner_content, "dashboard", lambda conn: pytest.fail("nonowner reached loader"))
    with pytest.raises(AuthError, match="forbidden"):
        _dispatch(auth, "owner/content", {}, "token", "csrf")


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
    conn.executescript("""CREATE TABLE categories(id INTEGER,slug TEXT);
        CREATE TABLE questions(category_id INTEGER,kind TEXT,status TEXT);
        INSERT INTO categories VALUES(1,'one'),(2,'outside');
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
