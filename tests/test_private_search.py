import hashlib
import json
from pathlib import Path

import pytest

from app.private_search import MAX_CHARS, SearchError, benchmark_retrieval, capacity_estimate, chunks, load_private_chunks, load_qa_cases, model_probe, require_current_reviewed_index, reviewed_chunks, search, statement_timeout_seconds, vector_text, verify_retrieval


def test_operator_rebuild_has_bounded_timeout_without_weakening_reads():
    assert statement_timeout_seconds("search", None) == 30
    assert statement_timeout_seconds("qa", None) == 30
    assert statement_timeout_seconds("rebuild", None) == 600
    assert statement_timeout_seconds("rebuild", 3600) == 3600
    for invalid in (0, 29, 3601, True):
        with pytest.raises(SearchError, match="invalid_rebuild_timeout"):
            statement_timeout_seconds("rebuild", invalid)
    with pytest.raises(SearchError, match="rebuild_timeout_only"):
        statement_timeout_seconds("search", 600)


def test_private_search_requires_exact_reviewed_extract_and_preserves_locators(tmp_path):
    text = "Психолог уточняет запрос клиента. " * 50
    raw = text.encode("utf-8")
    (tmp_path / "lesson.txt").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    source_id = "source_12345678901234567890"
    corpus = {"sources": [{"id": source_id, "kind": "learning_material", "readable": True,
        "modified_time": "2026-09-27T00:00:00Z", "snapshot_kind": "extracted_text",
        "snapshot_sha256": digest}]}
    item = {"source_id": source_id, "modified_time": "2026-09-27T00:00:00Z",
            "snapshot_sha256": digest, "text_path": "lesson.txt"}
    corpus["sources"][0]["title"] = "Учебная лекция"
    review = {source_id: {"revision": [item["modified_time"], "Учебная лекция",
            "application/vnd.google-apps.document"], "review_state": "processed",
            "snapshot_kind": "extracted_text", "snapshot_sha256": digest,
            "reviewer": "owner", "review_note": "Полный текст прочитан",
            "reviewed_at": "2026-09-27T00:00:00Z",
            "search_ranges": [[0, len(text)]],
            "search_reviewer": "owner",
            "search_review_note": "Индексирование проверенного фрагмента разрешено",
            "search_reviewed_at": "2026-09-27T00:00:00Z"}}
    manifest = {"schema_version": 1, "sources": [item]}
    entries = reviewed_chunks(manifest, corpus, tmp_path, review)
    with pytest.raises(SearchError, match="private_source_review_incomplete"):
        reviewed_chunks(manifest, corpus, tmp_path,
                        {source_id: {**review[source_id], "source_kind": "bibliography"}})
    with pytest.raises(SearchError, match="private_source_review_incomplete"):
        reviewed_chunks(manifest, corpus, tmp_path,
                        {source_id: {**review[source_id], "reviewed_at": "yesterday"}})
    with pytest.raises(SearchError, match="private_source_review_incomplete"):
        reviewed_chunks(manifest, corpus, tmp_path,
                        {source_id: {**review[source_id], "revision": [item["modified_time"],
                            "Учебная лекция", ""]}})
    with pytest.raises(SearchError, match="unresolved_related_source_conflict"):
        reviewed_chunks(manifest, corpus, tmp_path, {**review, "other": {
            "review_state": "pending_review", "conflict_hold": {
                "related_source_ids": [source_id]}}})
    assert len(entries) > 1
    assert all(entry[0] == source_id and entry[3].startswith("characters:") for entry in entries)
    assert all(len(entry[4]) <= MAX_CHARS for entry in entries)
    with pytest.raises(SearchError, match="private_search_passages_not_reviewed"):
        reviewed_chunks(manifest, corpus, tmp_path,
                        {source_id: {key: value for key, value in review[source_id].items()
                                     if not key.startswith("search_")}})
    restricted = {source_id: {**review[source_id], "search_ranges": [[10, 42]]}}
    excerpt = reviewed_chunks(manifest, corpus, tmp_path, restricted)
    assert all(text[int(entry[3].split(":")[1]):int(entry[3].split(":")[2])]
               == entry[4] for entry in excerpt)
    assert all(10 <= int(entry[3].split(":")[1])
               < int(entry[3].split(":")[2]) <= 42 for entry in excerpt)
    with pytest.raises(SearchError, match="invalid_private_search_ranges"):
        reviewed_chunks(manifest, corpus, tmp_path,
                        {source_id: {**review[source_id], "search_ranges": [[0, 40], [39, 50]]}})
    with pytest.raises(SearchError, match="private_source_review_required"):
        reviewed_chunks(manifest, corpus, tmp_path)
    with pytest.raises(SearchError, match="private_source_review_incomplete"):
        reviewed_chunks(manifest, corpus, tmp_path, {source_id: {**review[source_id],
            "review_state": "pending_review"}})
    with pytest.raises(SearchError, match="source_revision_not_reviewed"):
        reviewed_chunks({"schema_version": 1, "sources": [{**item, "modified_time": "changed"}]},
                        corpus, tmp_path, review)
    (tmp_path / "lesson.txt").write_text(text + "changed", encoding="utf-8")
    with pytest.raises(SearchError, match="fingerprint_changed"):
        reviewed_chunks(manifest, corpus, tmp_path, review)
    assert list(chunks("")) == []


def test_private_chunk_locator_matches_returned_excerpt_exactly():
    source = "  \n" + "Память и обучение. " * 24 + "\n  "
    fragments = list(chunks(source))
    assert len(fragments) > 1
    assert all(source[start:end] == excerpt for start, end, excerpt in fragments)


def test_private_search_rejects_unreviewed_or_malformed_vectors(tmp_path):
    source_id = "source_12345678901234567890"
    item = {"source_id": source_id, "modified_time": "now", "snapshot_sha256": "0" * 64,
            "text_path": "lesson.txt"}
    with pytest.raises(SearchError, match="unreviewed_or_duplicate_source"):
        reviewed_chunks({"schema_version": 1, "sources": [item]}, {"sources": []}, tmp_path, {})
    with pytest.raises(SearchError, match="invalid_embedding_dimensions"):
        vector_text([0.0, 1.0])
    with pytest.raises(SearchError, match="zero_embedding_not_searchable"):
        vector_text([0.0] * 384)


def test_private_manifest_requires_processed_revision_file(monkeypatch, tmp_path):
    from app import private_search

    text = "Метод исследования задаёт проверяемую процедуру."
    raw = text.encode("utf-8")
    (tmp_path / "lecture.txt").write_bytes(raw)
    source_id = "source_12345678901234567890"
    digest = hashlib.sha256(raw).hexdigest()
    modified = "2026-09-27T00:00:00Z"
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(json.dumps({"sources": [{"id": source_id,
        "title": "Лекция", "kind": "learning_material", "readable": True,
        "modified_time": modified, "snapshot_kind": "extracted_text",
        "snapshot_sha256": digest}]}), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest = {"schema_version": 1, "sources": [{"source_id": source_id,
        "modified_time": modified, "snapshot_sha256": digest,
        "text_path": "lecture.txt"}]}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(private_search, "PRIVATE_ROOT", tmp_path)
    monkeypatch.setattr(private_search, "CORPUS", corpus_path)
    with pytest.raises(SearchError, match="private_source_review_required"):
        load_private_chunks(manifest_path)

    manifest["processing_path"] = "reviews.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    review = {source_id: {"revision": [modified, "Лекция",
        "application/vnd.google-apps.document"], "review_state": "processed",
        "snapshot_kind": "extracted_text", "snapshot_sha256": digest,
        "reviewer": "owner", "review_note": "Полный текст прочитан",
        "reviewed_at": modified, "search_ranges": [[0, len(text)]],
        "search_reviewer": "owner",
        "search_review_note": "Весь фрагмент проверен", "search_reviewed_at": modified}}
    (tmp_path / "reviews.json").write_text(json.dumps(review), encoding="utf-8")
    assert len(load_private_chunks(manifest_path)) == 1
    review[source_id]["revision"][0] = "older"
    (tmp_path / "reviews.json").write_text(json.dumps(review), encoding="utf-8")
    with pytest.raises(SearchError, match="private_source_review_incomplete"):
        load_private_chunks(manifest_path)


def test_private_search_accepts_only_reviewed_private_registry_source(monkeypatch, tmp_path):
    from app import private_search

    source_id = "private-source-12345678901234567890"
    title = "Проверенная лекция"
    modified = "2026-09-28T00:00:00Z"
    text = "Личность описывается разными теориями."
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    (tmp_path / "lesson.txt").write_text(text, encoding="utf-8")
    public = {"schema_version": 1, "corpus_root_id": "root", "sources": []}
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(json.dumps(public), encoding="utf-8")
    private = {"schema_version": 1, "corpus_root_id": "root", "sources": [{
        "id": source_id, "title": title, "kind": "learning_material", "readable": True,
        "modified_time": modified, "snapshot_kind": "extracted_text",
        "snapshot_sha256": digest}]}
    registry_path = tmp_path / "private-registry.json"
    registry_path.write_text(json.dumps(private), encoding="utf-8")
    review = {source_id: {"revision": [modified, title, "application/vnd.google-apps.document"],
        "review_state": "processed", "snapshot_kind": "extracted_text",
        "snapshot_sha256": digest, "reviewer": "editor", "review_note": "Текст прочитан",
        "reviewed_at": modified, "search_ranges": [[0, len(text)]],
        "search_reviewer": "editor", "search_review_note": "Фрагмент проверен",
        "search_reviewed_at": modified}}
    (tmp_path / "reviews.json").write_text(json.dumps(review), encoding="utf-8")
    manifest = {"schema_version": 1, "processing_path": "reviews.json",
                "sources": [{"source_id": source_id, "modified_time": modified,
                             "snapshot_sha256": digest, "text_path": "lesson.txt"}]}
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(private_search, "PRIVATE_ROOT", tmp_path)
    monkeypatch.setattr(private_search, "CORPUS", corpus_path)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SearchError, match="unreviewed_or_duplicate_source"):
        load_private_chunks(manifest_path)
    manifest["private_registry_path"] = registry_path.name
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert len(load_private_chunks(manifest_path)) == 1
    public["sources"] = private["sources"]
    corpus_path.write_text(json.dumps(public), encoding="utf-8")
    with pytest.raises(SearchError, match="invalid_private_source_registry"):
        load_private_chunks(manifest_path)


def test_private_notes_require_exact_private_snapshot_without_drive_publication(tmp_path):
    text = "Личная заметка владельца о последовательности консультации."
    (tmp_path / "note.txt").write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    note = {"note_id": "my-note", "modified_time": "2026-09-27T00:00:00Z",
            "snapshot_sha256": digest, "text_path": "note.txt"}
    manifest = {"schema_version": 1, "sources": [], "notes": [note]}
    entries = reviewed_chunks(manifest, {"sources": []}, tmp_path)
    assert len(entries) == 1
    assert entries[0][:3] == ("note:my-note", note["modified_time"], digest)
    estimate = capacity_estimate(entries)
    assert estimate["sources"] == estimate["chunks"] == 1
    assert estimate["raw_vector_bytes"] == 384 * 4
    with pytest.raises(SearchError, match="invalid_private_note"):
        reviewed_chunks({**manifest, "notes": [note, note]}, {"sources": []}, tmp_path)
    (tmp_path / "note.txt").write_text(text + " changed", encoding="utf-8")
    with pytest.raises(SearchError, match="private_note_fingerprint_changed"):
        reviewed_chunks(manifest, {"sources": []}, tmp_path)


def test_private_hybrid_search_combines_lexical_and_semantic_evidence(monkeypatch):
    monkeypatch.setattr("app.private_search.ensure_index", lambda *args, **kwargs: None)
    class Model:
        def embed(self, texts):
            assert texts == ["прояснение запроса"]
            return [[1.0] + [0.0] * 383]

    class Connection:
        def execute(self, query, params):
            assert "private_search.chunks" in query
            common = ("source-12345678901234567890", "2026-09-27", "a" * 64,
                      "characters:0:30", "Сначала проясните запрос", 0.8)
            lexical_only = ("note:consulting", "2026-09-27", "b" * 64,
                            "characters:10:40", "Рабочая заметка", 0.5)
            rows = [common, lexical_only] if "ts_rank_cd" in query else [common]
            return type("Rows", (), {"fetchall": lambda self: rows})()

    result = search(Connection(), "прояснение запроса", Model(), limit=2)
    assert [row["source_id"] for row in result] == [
        "source-12345678901234567890", "note:consulting"]
    assert result[0]["rank_score"] > result[1]["rank_score"]
    with pytest.raises(SearchError, match="invalid_search_query"):
        search(Connection(), " ", Model())


def test_operator_search_rejects_index_from_older_private_review(monkeypatch):
    from app import private_search

    assert private_search.main(["search", "--query", "проверка"]) == 1
    monkeypatch.setattr(private_search, "ensure_index", lambda conn: None)
    chunks = [("source-one", "revision", "a" * 64, "characters:0:12", "Текст")]
    monkeypatch.setattr(private_search, "load_private_chunks", lambda path: chunks)

    class Connection:
        def __init__(self, rows):
            self.rows = rows

        def execute(self, query):
            assert "private_search.chunks" in query
            return type("Rows", (), {"fetchall": lambda _: self.rows})()

    current = chunks[0]
    require_current_reviewed_index(Connection([current]), Path("manifest.json"))
    with pytest.raises(SearchError, match="private_index_stale_for_review"):
        require_current_reviewed_index(
            Connection([("source-one", "revision", "b" * 64, "characters:0:12", "Текст")]),
            Path("manifest.json"))
    with pytest.raises(SearchError, match="private_index_stale_for_review"):
        require_current_reviewed_index(
            Connection([("source-one", "revision", "a" * 64, "characters:0:12", "Подмена")]),
            Path("manifest.json"))
    with pytest.raises(SearchError, match="private_index_stale_for_review"):
        require_current_reviewed_index(Connection([current, current]), Path("manifest.json"))
    monkeypatch.setattr(private_search, "load_private_chunks",
                        lambda path: (_ for _ in ()).throw(SearchError("unresolved_related_source_conflict")))
    with pytest.raises(SearchError, match="unresolved_related_source_conflict"):
        require_current_reviewed_index(Connection([current]), Path("manifest.json"))


def test_model_probe_reports_only_local_resource_evidence(monkeypatch, tmp_path):
    class Model:
        def embed(self, texts):
            assert texts == ["проверка поиска по учебному материалу"]
            return [[1.0] + [0.0] * 383]

    monkeypatch.setattr("app.private_search.embedder", lambda: Model())
    monkeypatch.setenv("SEARCH_MODEL_CACHE", str(tmp_path))
    (tmp_path / "model.bin").write_bytes(b"synthetic")
    result = model_probe()
    assert result["dimensions"] == 384 and result["cache_bytes"] == 9
    assert result["elapsed_ms"] >= 0
    assert result["process_cpu_ms"] >= 0
    assert result["process_peak_rss_bytes"] is None or result["process_peak_rss_bytes"] > 0
    assert set(result) == {"model", "dimensions", "elapsed_ms", "cache_bytes",
                           "process_cpu_ms", "process_peak_rss_bytes"}


def test_private_hybrid_qa_requires_exact_top_source_revision(monkeypatch, tmp_path):
    from app import private_search

    source_id = "source_12345678901234567890"
    digest = "a" * 64
    path = tmp_path / "qa.json"
    path.write_text(json.dumps({"schema_version": 1, "cases": [{
        "query": "Как передаётся нервный сигнал?", "source_id": source_id,
        "snapshot_sha256": digest}]}), encoding="utf-8")
    monkeypatch.setattr(private_search, "PRIVATE_ROOT", tmp_path)
    cases = load_qa_cases(path)
    monkeypatch.setattr(private_search, "search", lambda *args, **kwargs: [{
        "source_id": source_id, "snapshot_sha256": digest}])
    assert verify_retrieval(None, cases, object()) == {"cases_passed": 1}
    monkeypatch.setattr(private_search, "search", lambda *args, **kwargs: [{
        "source_id": source_id, "snapshot_sha256": "b" * 64}])
    with pytest.raises(SearchError, match="private_retrieval_qa_failed"):
        verify_retrieval(None, cases, object())
    path.write_text(json.dumps({"schema_version": 1, "cases": [{
        "query": "Что я отметил о консультации?", "source_id": "note:my-note",
        "snapshot_sha256": digest}]}), encoding="utf-8")
    assert load_qa_cases(path)[0]["source_id"] == "note:my-note"


def test_private_benchmark_reports_only_aggregate_and_fails_on_wrong_revision(monkeypatch):
    from app import private_search

    source = "source_12345678901234567890"
    digest = "a" * 64
    cases = [{"query": "проверка", "source_id": source, "snapshot_sha256": digest}]

    class Connection:
        def execute(self, query):
            assert "pg_total_relation_size" in query
            return type("Row", (), {"fetchone": lambda _: (4096,)})()

    monkeypatch.setattr(private_search, "search", lambda *args, **kwargs: [
        {"source_id": source, "snapshot_sha256": digest}])
    result = benchmark_retrieval(Connection(), cases, object())
    assert result["cases_passed"] == 1 and result["storage_bytes"] == 4096
    assert result["max_ms"] >= 0
    assert source not in str(result) and "проверка" not in str(result)

    monkeypatch.setattr(private_search, "search", lambda *args, **kwargs: [
        {"source_id": source, "snapshot_sha256": "b" * 64}])
    with pytest.raises(SearchError, match="private_retrieval_qa_failed"):
        benchmark_retrieval(Connection(), cases, object())


def test_probe_peak_memory_units_and_unavailable_platform(monkeypatch):
    from types import SimpleNamespace
    from app import private_search
    fake = SimpleNamespace(RUSAGE_SELF=0, getrusage=lambda _: SimpleNamespace(ru_maxrss=123))
    monkeypatch.setitem(private_search.sys.modules, "resource", fake)
    monkeypatch.setattr(private_search.sys, "platform", "linux")
    assert private_search.process_peak_rss_bytes() == 123 * 1024
    monkeypatch.setattr(private_search.sys, "platform", "darwin")
    assert private_search.process_peak_rss_bytes() == 123
    monkeypatch.setattr(private_search.sys, "platform", "unsupported")
    assert private_search.process_peak_rss_bytes() is None
    monkeypatch.setitem(private_search.sys.modules, "resource", None)
    assert private_search.process_peak_rss_bytes() is None


def test_operator_lexical_empty_result_never_downloads_or_calls_model(monkeypatch):
    from app import private_search
    monkeypatch.setattr(private_search, "ensure_index", lambda *args, **kwargs: None)
    class Connection:
        def execute(self, query, params):
            assert "ts_rank_cd" in query and "embedding OPERATOR" not in query
            return type("Rows", (), {"fetchall": lambda self: []})()
    assert search(Connection(), "no lexical match", None, mode="lexical") == []
    with pytest.raises(SearchError, match="invalid_search_mode"):
        search(Connection(), "query", None, mode="unknown")


def test_operator_semantic_mode_excludes_lexical_fallback(monkeypatch):
    from app import private_search
    monkeypatch.setattr(private_search, "ensure_index", lambda *args, **kwargs: None)
    class Model:
        def embed(self, texts):
            return [[1.0] + [0.0] * 383]
    class Connection:
        def execute(self, query, params):
            assert "embedding OPERATOR" in query and "ts_rank_cd" not in query
            row = ("synthetic-source", "2026-10-01", "a" * 64,
                   "characters:0:20", "synthetic reviewed text", 0.8)
            return type("Rows", (), {"fetchall": lambda self: [row]})()
    assert search(Connection(), "paraphrase", Model(), mode="semantic")[0]["source_id"] == "synthetic-source"


def test_private_qa_checks_expected_passage_and_requested_mode(monkeypatch, tmp_path):
    from app import private_search
    source = "source_12345678901234567890"
    digest = "a" * 64
    case = {"query": "reviewed paraphrase", "source_id": source,
            "snapshot_sha256": digest, "locator": "characters:10:40", "mode": "semantic"}
    path = tmp_path / "qa.json"
    path.write_text(json.dumps({"schema_version": 1, "cases": [case]}), encoding="utf-8")
    monkeypatch.setattr(private_search, "PRIVATE_ROOT", tmp_path)
    cases = load_qa_cases(path)
    def result(*args, **kwargs):
        assert kwargs["mode"] == "semantic"
        return [{"source_id": source, "snapshot_sha256": digest, "locator": "characters:41:80"}]
    monkeypatch.setattr(private_search, "search", result)
    with pytest.raises(SearchError, match="private_retrieval_qa_failed"):
        verify_retrieval(None, cases, object())
    monkeypatch.setattr(private_search, "search", lambda *args, **kwargs: [case])
    assert verify_retrieval(None, cases, object()) == {"cases_passed": 1}
    for invalid in ({"locator": "characters:40:10"}, {"mode": "unknown"}, {"mode": []}, {"locator": "line:4"}):
        path.write_text(json.dumps({"schema_version": 1, "cases": [{**case, **invalid}]}), encoding="utf-8")
        with pytest.raises(SearchError, match="invalid_private_qa_cases"):
            load_qa_cases(path)
