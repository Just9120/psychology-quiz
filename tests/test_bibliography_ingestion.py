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
