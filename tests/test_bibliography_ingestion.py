import hashlib
from copy import deepcopy

import pytest

from app.bibliography_ingestion import discover_bibliography
from app.source_inventory import InventoryError


def test_adjacent_books_in_wrapped_list_keep_exact_offsets_without_later_dialogue():
    text = ('Автор книг «Первая книга»,\n«Вторая книга» и «Третья книга». '
            'Он сказал: «Спасибо за участие».')
    raw = text.encode("utf-8")
    revision = ["2026-10-03", "Slides", "application/pdf"]
    snapshot = {"files": {"source": dict(zip(("modified_time", "title", "mime_type"), revision))},
                "paths": {"source": [["Module", "Slides"]]}}
    result = discover_bibliography(snapshot, [{"source_id": "source", "content": raw,
        "revision": revision, "snapshot_sha256": hashlib.sha256(raw).hexdigest()}], [])
    assert [item["title_candidate"] for item in result["mentions"]] == [
        "Первая книга", "Вторая книга", "Третья книга"]
    for item in result["mentions"]:
        start, end = map(int, item["locator"].split(":")[1:])
        assert text[start:end] == item["title_candidate"]
        assert item["candidate_work_ids"] == [] and item["decision"] == "pending_review"
    assert result["publication_approval"] is False


def test_recursive_multiformat_mentions_are_private_pending_and_preserve_catalogue():
    catalogue = [{"id": "association", "work_id": "work", "title": "Учебная книга"}]
    before = deepcopy(catalogue)
    snapshot = {"files": {}, "paths": {}}
    captures = []
    for index, mime in enumerate(("application/pdf", "application/vnd.google-apps.document",
                                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document")):
        source_id = f"synthetic-{index}"
        raw = 'В лекции рекомендуют книгу «Учебная книга».'.encode("utf-8")
        revision = ["2026-10-01T00:00:00Z", "Synthetic", mime]
        snapshot["files"][source_id] = dict(zip(("modified_time", "title", "mime_type"), revision))
        snapshot["paths"][source_id] = [["Module", "Discipline", "Lesson", "Synthetic"]]
        captures.append({"source_id": source_id, "content": raw, "revision": revision,
                         "snapshot_sha256": hashlib.sha256(raw).hexdigest()})
    snapshot["files"]["unread"] = {}
    result = discover_bibliography(snapshot, captures, catalogue)
    assert result["captured_sources"] == 3 and result["unread_source_ids"] == ["unread"]
    assert len(result["mentions"]) == 3 and not result["publication_approval"]
    assert all(item["candidate_work_ids"] == ["work"] and item["decision"] == "pending_review"
               for item in result["mentions"])
    assert catalogue == before
    for item, capture in zip(result["mentions"], captures):
        start, end = map(int, item["locator"].split(":")[1:])
        assert capture["content"].decode("utf-8")[start:end] == item["title_candidate"]
    captures[0]["revision"][0] = "2026-10-02T00:00:00Z"
    with pytest.raises(InventoryError, match="stale_or_invalid"):
        discover_bibliography(snapshot, captures, catalogue)


def test_unknown_book_and_ambiguous_exact_title_never_merge_work_identities():
    text = 'Рекомендую книгу «Новая книга». Затем прочитайте «Общая психология».'
    raw = text.encode("utf-8")
    snapshot = {"files": {"source": {"modified_time": "2026-10-01", "title": "Lesson", "mime_type": "text/plain"}},
                "paths": {"source": [["Module", "Lesson"]]}}
    capture = {"source_id": "source", "content": raw, "revision": ["2026-10-01", "Lesson", "text/plain"],
               "snapshot_sha256": hashlib.sha256(raw).hexdigest()}
    catalogue = [{"id": f"entry{i}", "work_id": f"work{i}", "title": "Общая психология"}
                 for i in range(2)]
    result = discover_bibliography(snapshot, [capture], catalogue)
    assert [item["candidate_work_ids"] for item in result["mentions"]] == [[], ["work0", "work1"]]
    assert all(item["decision"] == "pending_review" for item in result["mentions"])
    capture["content"] += b"changed"
    with pytest.raises(InventoryError, match="stale_or_invalid"):
        discover_bibliography(snapshot, [capture], catalogue)


@pytest.mark.parametrize("raw", [b"", b" \n", b"\xef\xbb\xbf"])
def test_empty_extract_does_not_mark_source_as_read(raw):
    snapshot = {"files": {"source": {"modified_time": "2026-10-01", "title": "Scanned", "mime_type": "application/pdf"}},
                "paths": {"source": [["Module", "Scanned"]]}}
    capture = {"source_id": "source", "content": raw,
               "revision": ["2026-10-01", "Scanned", "application/pdf"],
               "snapshot_sha256": hashlib.sha256(raw).hexdigest()}
    with pytest.raises(InventoryError, match="empty_capture_not_read"):
        discover_bibliography(snapshot, [capture], [])


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_wrapped_unknown_titles_preserve_raw_spans_and_remain_pending(newline):
    title = f"Неизвестная учебная{newline}книга"
    second = f"Другое длинное{newline}название"
    text = (f"Рекомендую книги{newline}«{title}», «{second}». "
            'Он сказал: «Спасибо за участие». '
            f'Упоминание книги завершено.{newline}{newline}«Отдельная реплика».')
    raw = text.encode("utf-8")
    revision = ["2026-10-03", "Slides", "application/pdf"]
    snapshot = {"files": {"source": dict(zip(("modified_time", "title", "mime_type"), revision))},
                "paths": {"source": [["Module", "Slides"]]}}
    capture = {"source_id": "source", "content": raw, "revision": revision,
               "snapshot_sha256": hashlib.sha256(raw).hexdigest()}
    result = discover_bibliography(snapshot, [capture], [])
    assert [item["title_candidate"] for item in result["mentions"]] == [title, second]
    for item in result["mentions"]:
        start, end = map(int, item["locator"].split(":")[1:])
        assert text[start:end] == item["title_candidate"]
        assert item["snapshot_sha256"] == capture["snapshot_sha256"]
        assert item["revision"] == revision
        assert item["candidate_work_ids"] == []
        assert item["decision"] == "pending_review"
    assert result["publication_approval"] is False


def test_book_cue_inside_quoted_title_cannot_capture_following_dialogue():
    from app.bibliography_ingestion import _book_quotes

    text = 'Рекомендую книгу «Учебная книга». Он сказал: «Что ты видишь?»'
    candidates = list(_book_quotes(text))
    assert [title for _, title in candidates] == ["Учебная книга"]
    assert all(text[start:end] == title for (start, end), title in candidates)


def test_private_title_alias_locates_existing_work_without_merging_or_approval():
    text = 'В лекции упоминают «Принципы научного менеджмента».'
    raw = text.encode("utf-8")
    revision = ["2026-10-04", "Lesson", "text/plain"]
    snapshot = {"files": {"source": dict(zip(("modified_time", "title", "mime_type"), revision))},
                "paths": {"source": [["Module", "Lesson"]]}}
    capture = {"source_id": "source", "content": raw, "revision": revision,
               "snapshot_sha256": hashlib.sha256(raw).hexdigest()}
    catalogue = [{"id": "entry", "work_id": "taylor",
                  "title": "The Principles of Scientific Management"}]
    before = deepcopy(catalogue)
    aliases = [{"title": "Принципы научного менеджмента", "work_id": "taylor"}]
    result = discover_bibliography(snapshot, [capture], catalogue, aliases)
    assert len(result["mentions"]) == 1
    mention = result["mentions"][0]
    assert mention["candidate_work_ids"] == ["taylor"]
    assert mention["decision"] == "pending_review"
    start, end = map(int, mention["locator"].split(":")[1:])
    assert text[start:end] == aliases[0]["title"]
    assert catalogue == before and result["publication_approval"] is False
    with pytest.raises(InventoryError, match="invalid_bibliography_alias"):
        discover_bibliography(snapshot, [capture], catalogue,
                              [{"title": "Новая книга", "work_id": "missing"}])


@pytest.mark.parametrize("text, expected", [
    ("Психология изучает поведение. Качественные методы в психологии.", []),
    ('Литература к блоку «Психология».', []),
    ('Прочитайте книгу «Психология».', [("Психология", ["myers"])]),
    ('Майерс Д. Психология. Учебник.', [("Психология", ["myers"])]),
    ('Рекомендую книгу «Основы психологии».', [("Основы психологии", [])]),
    ('Майерс объясняет, что психология изучает поведение.', []),
])
def test_single_word_catalogue_title_needs_book_or_author_context(text, expected):
    raw = text.encode("utf-8")
    revision = ["2026-10-05", "Synthetic", "text/plain"]
    snapshot = {"files": {"source": dict(zip(("modified_time", "title", "mime_type"), revision))},
                "paths": {"source": [["Module", "Synthetic"]]}}
    capture = {"source_id": "source", "content": raw, "revision": revision,
               "snapshot_sha256": hashlib.sha256(raw).hexdigest()}
    catalogue = [{"id": "entry", "work_id": "myers", "title": "Психология",
                  "authors": ["Майерс Д."]}]
    result = discover_bibliography(snapshot, [capture], catalogue)
    assert [(item["title_candidate"], item["candidate_work_ids"])
            for item in result["mentions"]] == expected
    assert result["publication_approval"] is False
    for item in result["mentions"]:
        start, end = map(int, item["locator"].split(":")[1:])
        assert text[start:end] == item["title_candidate"]


@pytest.mark.parametrize("changed", [None, "original", "derived", "revision"])
def test_binary_bibliography_capture_binds_original_and_ocr_without_mutating_processing(
        tmp_path, monkeypatch, changed):
    from scripts import source_bibliography
    import json

    revision = ["2026-10-01", "Slides", "application/pdf"]
    snapshot = {"files": {"s": dict(zip(("modified_time", "title", "mime_type"), revision))},
                "paths": {"s": [["Module", "Slides"]]}}
    monkeypatch.setattr(source_bibliography, "_snapshot", lambda _: snapshot)
    monkeypatch.setattr(source_bibliography, "_private_content_path", lambda p: tmp_path / p)
    monkeypatch.setattr(source_bibliography, "_private_original_path", lambda p: tmp_path / p)
    original, text = b"synthetic original bytes", 'Книга «Учебная работа».'.encode("utf-8")
    (tmp_path / "original.pdf").write_bytes(original)
    (tmp_path / "ocr.txt").write_bytes(text)
    original_sha = hashlib.sha256(original).hexdigest()
    binding = {"schema_version": 1, "source_id": "s", "revision": revision,
               "original_sha256": original_sha,
               "derived_text_sha256": hashlib.sha256(text).hexdigest(),
               "extraction_profile": "synthetic-ocr-v1"}
    (tmp_path / "binding.json").write_text(json.dumps(binding), encoding="utf-8")
    processing = {"s": {"snapshot_kind": "file_bytes", "snapshot_sha256": original_sha,
                        "revision": revision, "review_state": "conflict"}}
    before = deepcopy(processing)
    manifest = {"schema_version": 1, "sources": [{"source_id": "s", "content": "ocr.txt",
                 "original": "original.pdf", "derivation_receipt": "binding.json"}]}
    if changed == "original":
        (tmp_path / "original.pdf").write_bytes(original + b"changed")
    elif changed == "derived":
        (tmp_path / "ocr.txt").write_bytes(text + b"changed")
    elif changed == "revision":
        binding["revision"] = ["different", "Slides", "application/pdf"]
        (tmp_path / "binding.json").write_text(json.dumps(binding), encoding="utf-8")
    if changed:
        with pytest.raises(InventoryError, match="invalid_derivation_binding"):
            source_bibliography.run({}, processing, manifest, [])
    else:
        result = source_bibliography.run({}, processing, manifest, [])
        mention = result["mentions"][0]
        assert mention["title_candidate"] == "Учебная работа"
        assert mention["original_snapshot_sha256"] == original_sha
        assert mention["snapshot_sha256"] == hashlib.sha256(text).hexdigest()
        assert mention["decision"] == "pending_review" and result["publication_approval"] is False
    assert processing == before


@pytest.mark.parametrize("relative", ["outside.pdf", "data/../outside.pdf", "data/input.txt"])
def test_binary_bibliography_original_rejects_paths_outside_private_pdf_storage(
        tmp_path, monkeypatch, relative):
    from scripts import source_bibliography
    monkeypatch.setattr(source_bibliography, "ROOT", tmp_path)
    with pytest.raises(InventoryError, match="original_requires_private_pdf"):
        source_bibliography._private_original_path(relative)


@pytest.mark.parametrize("citation", [
    "Льва Толстого Война и мир",
    "Бориса Пастернака Доктор Живаго",
    "Михаила Александровича Шолохова Тихий Дон",
])
def test_unquoted_novel_keeps_author_title_boundary_unparsed_and_private(citation):
    text = "\ufeffПример в романе " + citation + ", где герой принимает решение."
    raw = text.encode("utf-8")
    revision = ["2026-10-05", "Synthetic", "text/plain"]
    snapshot = {"files": {"s": dict(zip(("modified_time", "title", "mime_type"), revision))},
                "paths": {"s": [["Module", "Lesson"]]}}
    result = discover_bibliography(snapshot, [{"source_id": "s", "content": raw,
        "revision": revision, "snapshot_sha256": hashlib.sha256(raw).hexdigest()}], [])
    assert len(result["mentions"]) == 1
    mention = result["mentions"][0]
    assert mention["candidate_kind"] == "unparsed_author_title"
    assert mention["title_candidate"] == citation and mention["candidate_work_ids"] == []
    start, end = map(int, mention["locator"].split(":")[1:])
    assert text[start:end] == citation
    assert mention["decision"] == "pending_review" and result["publication_approval"] is False


def test_known_title_inside_unquoted_citation_does_not_duplicate_review_task():
    text = "В романе Льва Толстого Война и мир, герой ищет решение."
    raw = text.encode("utf-8")
    revision = ["2026-10-05", "Synthetic", "text/plain"]
    snapshot = {"files": {"s": dict(zip(("modified_time", "title", "mime_type"), revision))},
                "paths": {"s": [["Module", "Lesson"]]}}
    catalogue = [{"id": "entry", "work_id": "war-peace", "title": "Война и мир"}]
    before = deepcopy(catalogue)
    result = discover_bibliography(snapshot, [{"source_id": "s", "content": raw,
        "revision": revision, "snapshot_sha256": hashlib.sha256(raw).hexdigest()}], catalogue)
    assert [(m["title_candidate"], m["candidate_work_ids"]) for m in result["mentions"]] == [
        ("Война и мир", ["war-peace"])]
    assert catalogue == before and result["publication_approval"] is False


@pytest.mark.parametrize("text, expected", [
    ('Рекомендую роман «Неизвестная история». Он сказал: «Привет».', ["Неизвестная история"]),
    ('Повесть «Другая история». Он сказал: «Привет».', ["Другая история"]),
    ('У неё основной труд это «Патопсихология».', ["Патопсихология"]),
    ('Научный труд «Основы анализа» рекомендован на занятии.', ["Основы анализа"]),
    ('Фундаментальный труд\n«История метода». Он сказал: «Привет».', ["История метода"]),
    ('Это был огромный труд. Он сказал: «Привет».', []),
    ('У них начался роман. Он сказал: «Привет».', []),
    ('Обсуждаем роман Льва Толстого. Он сказал: «Привет».', []),
    ('Обсуждаем роман Льва Толстого и поведение героя.', []),
])
def test_book_cue_never_turns_following_dialogue_into_a_book(text, expected):
    raw = text.encode("utf-8")
    revision = ["2026-10-05", "Synthetic", "text/plain"]
    snapshot = {"files": {"s": dict(zip(("modified_time", "title", "mime_type"), revision))},
                "paths": {"s": [["Module", "Lesson"]]}}
    result = discover_bibliography(snapshot, [{"source_id": "s", "content": raw,
        "revision": revision, "snapshot_sha256": hashlib.sha256(raw).hexdigest()}], [])
    assert [m["title_candidate"] for m in result["mentions"]] == expected
    assert result["publication_approval"] is False
