import pytest

from app.source_inventory import (InventoryError, complete_listing, format_variant_candidates,
                                  link_lessons, processing_status, reconcile, scan)

REVIEW_EVIDENCE = {"reviewer": "editor", "review_note": "Reviewed exact source revision",
                   "reviewed_at": "2026-09-26T12:00:00Z"}


def item(file_id, parent, *, title="Lesson", changed="2026-09-25T00:00:00Z"):
    return {"id": file_id, "parent_ids": [parent], "file_or_folder": "file",
            "title": title, "mime_type": "application/pdf", "modified_time": changed}


def test_format_variants_are_private_candidates_not_cross_folder_merges():
    root, first, second = "root", "first-folder", "second-folder"
    folders = [{"id": folder, "title": folder, "parent_ids": [root],
                "file_or_folder": "folder"} for folder in (first, second)]
    native = {**item("doc", first, title="Лекция 1"),
              "mime_type": "application/vnd.google-apps.document"}
    snapshot = scan(root, {root: {"complete": True, "children": folders},
                           first: {"complete": True, "children": [
                               item("pdf", first, title="Лекция 1.PDF"), native]},
                           second: {"complete": True, "children": [
                               item("other", second, title="Лекция 1.pdf")]}})
    assert format_variant_candidates(snapshot) == [{
        "parent_path": [first], "normalized_stem": "лекция 1",
        "file_ids": ["doc", "pdf"],
        "mime_types": ["application/pdf", "application/vnd.google-apps.document"],
    }]


def test_recursive_snapshot_requires_complete_children_and_detects_changes():
    root, child = "root", "nested"
    folder = {"id": child, "title": "Nested", "parent_ids": [root], "file_or_folder": "folder"}
    listings = {root: {"complete": True, "children": [folder, item("first", root)]},
                child: {"complete": True, "children": [item("second", child)]}}
    first = scan(root, listings)
    assert (first["folders"], len(first["files"])) == (2, 2)
    with pytest.raises(InventoryError, match="incomplete_folder_listing"):
        scan(root, {root: listings[root]})
    later = {**listings, child: {"complete": True, "children": [
        item("second", child, changed="2026-09-26T00:00:00Z"), item("third", child)]}}
    assert reconcile(first, scan(root, later)) == {
        "new": ["third"], "changed": ["second"], "relocated": [],
        "unchanged": ["first"], "missing": []}


def test_page_chain_must_finish_before_recursive_inventory():
    pages = [
        {"page_token": None, "next_page_token": "cursor-2", "children": [item("first", "root")]},
        {"page_token": "cursor-2", "next_page_token": None, "children": [item("second", "root")]},
    ]
    assert len(scan("root", {"root": complete_listing(pages)})["files"]) == 2
    with pytest.raises(InventoryError, match="incomplete_folder_listing"):
        complete_listing(pages[:1])
    with pytest.raises(InventoryError, match="invalid_page_chain"):
        complete_listing([pages[0], {**pages[1], "page_token": "stale"}])
    with pytest.raises(InventoryError, match="invalid_page_chain"):
        complete_listing([*pages, pages[1]])
    with pytest.raises(InventoryError, match="duplicate_page_child"):
        complete_listing([pages[0], {**pages[1], "children": [item("first", "root")]}])
    with pytest.raises(InventoryError, match="invalid_child"):
        complete_listing([{**pages[1], "page_token": None, "children": [{"id": ["invalid"]}]}])


def test_missing_is_not_deletion_and_conflicting_metadata_fails_closed():
    original = scan("root", {"root": {"complete": True, "children": [item("one", "root")]}})
    empty = scan("root", {"root": {"complete": True, "children": []}})
    assert reconcile(original, empty)["missing"] == ["one"]
    with pytest.raises(InventoryError, match="conflicting_file_metadata"):
        scan("root", {"root": {"complete": True, "children": [
            item("one", "root"), item("one", "root", title="Conflicting")]}})
    with pytest.raises(InventoryError, match="parent_mismatch"):
        scan("root", {"root": {"complete": True, "children": [
            {**item("one", "root"), "parent_ids": None}]}})


def test_folder_move_requires_link_review_without_claiming_content_change():
    folder_a = {"id": "a", "title": "Lesson A", "parent_ids": ["root"],
                "file_or_folder": "folder"}
    folder_b = {**folder_a, "id": "b", "title": "Lesson B"}
    base = {"root": {"complete": True, "children": [folder_a, folder_b]},
            "a": {"complete": True, "children": [item("same", "a")]},
            "b": {"complete": True, "children": []}}
    before = scan("root", base)
    after = scan("root", {**base, "a": {"complete": True, "children": []},
                          "b": {"complete": True, "children": [item("same", "b")]}})
    assert before["paths"]["same"] == [["Lesson A", "Lesson"]]
    assert after["paths"]["same"] == [["Lesson B", "Lesson"]]
    assert reconcile(before, after) == {
        "new": [], "changed": [], "relocated": ["same"], "unchanged": [], "missing": []}
    assert processing_status(after, {"same": {"revision": (
        "2026-09-25T00:00:00Z", "Lesson", "application/pdf"),
        "review_state": "processed", "snapshot_kind": "file_bytes",
        "snapshot_sha256": "a" * 64, **REVIEW_EVIDENCE}}) == {"same": "processed"}


def test_processing_requires_same_revision_and_explicit_lesson_links():
    snapshot = scan("root", {"root": {"complete": True, "children": [
        item("lecture", "root"), item("slides", "root")]}})
    revision = ("2026-09-25T00:00:00Z", "Lesson", "application/pdf")
    states = processing_status(snapshot, {
        "lecture": {"revision": revision, "review_state": "processed",
                    "snapshot_kind": "extracted_text", "snapshot_sha256": "a" * 64,
                    **REVIEW_EVIDENCE},
        "slides": {"revision": revision, "review_state": "conflict", "reason": "competing editions"}})
    assert states == {"lecture": "processed", "slides": "conflict_review"}
    assert processing_status(snapshot, {"lecture": {"revision": ("old", "Lesson", "application/pdf"),
        "review_state": "pending_review"}})["lecture"] == "changed_unprocessed"
    with pytest.raises(InventoryError, match="invalid_processing_record"):
        processing_status(snapshot, {"lecture": []})
    with pytest.raises(InventoryError, match="unverified_processing_record"):
        processing_status(snapshot, {"lecture": {"revision": revision, "review_state": "processed"}})
    with pytest.raises(InventoryError, match="unverified_processing_record"):
        processing_status(snapshot, {"lecture": {"revision": revision, "review_state": "processed",
            "snapshot_kind": "extracted_text", "snapshot_sha256": "not-a-sha256"}})
    with pytest.raises(InventoryError, match="unverified_processing_record"):
        processing_status(snapshot, {"lecture": {"revision": revision, "review_state": "processed",
            "snapshot_kind": "extracted_text", "snapshot_sha256": "a" * 64}})
    with pytest.raises(InventoryError, match="unverified_processing_record"):
        processing_status(snapshot, {"lecture": {"revision": revision, "review_state": "processed",
            "snapshot_kind": "extracted_text", "snapshot_sha256": "a" * 64,
            **REVIEW_EVIDENCE, "reviewed_at": "yesterday"}})
    with pytest.raises(InventoryError, match="invalid_processing_record"):
        processing_status(snapshot, {"lecture": {"revision": revision, "review_state": "conflict"}})
    assert processing_status(snapshot, {"lecture": {"revision": revision,
        "review_state": "pending_review"}})["lecture"] == "pending_review"
    valid_hold = {"reason": "Transcript and slides disagree", "locator": "slide 4",
                  "related_source_ids": ["slides"]}
    assert processing_status(snapshot, {"lecture": {"revision": revision,
        "review_state": "pending_review", "conflict_hold": valid_hold}})["lecture"] == "pending_review"
    for invalid in ({**valid_hold, "reason": ""}, {**valid_hold, "locator": None},
                    {**valid_hold, "related_source_ids": ["lecture"]},
                    {**valid_hold, "related_source_ids": ["slides", "slides"]}):
        with pytest.raises(InventoryError, match="invalid_conflict_hold"):
            processing_status(snapshot, {"lecture": {"revision": revision,
                "review_state": "pending_review", "conflict_hold": invalid}})
    with pytest.raises(InventoryError, match="invalid_conflict_hold"):
        processing_status(snapshot, {"lecture": {"revision": revision,
            "review_state": "processed", "snapshot_kind": "extracted_text",
            "snapshot_sha256": "a" * 64, **REVIEW_EVIDENCE, "conflict_hold": valid_hold}})
    evidence = {"revision": list(revision), "corpus_path": "Lesson", "reviewer": "editor",
                "review_note": "Compared the two lesson formats", "reviewed_at": "2026-09-26T10:32:54Z"}
    links = [{"source_id": "lecture", "lesson_id": "l1", "topic_id": "topic",
              "format": "transcript", **evidence},
             {"source_id": "slides", "lesson_id": "l1", "topic_id": "topic",
              "format": "slides", **evidence}]
    assert len(link_lessons(snapshot, links)["l1"]["sources"]) == 2
    with pytest.raises(InventoryError, match="duplicate_lesson_link"):
        link_lessons(snapshot, [links[0], {**links[0], "format": "slides"}])
    with pytest.raises(InventoryError, match="conflicting_lesson_topic"):
        link_lessons(snapshot, [links[0], {**links[1], "topic_id": "other"}])
    with pytest.raises(InventoryError, match="invalid_lesson_link"):
        link_lessons(snapshot, [{**links[0], "source_id": ["not-a-file"]}])
    with pytest.raises(InventoryError, match="stale_lesson_link"):
        link_lessons(snapshot, [{**links[0], "revision": ["old", *revision[1:]]}])
    with pytest.raises(InventoryError, match="stale_lesson_link"):
        link_lessons(snapshot, [{**links[0], "corpus_path": "Other/Lesson"}])
    with pytest.raises(InventoryError, match="invalid_lesson_link"):
        link_lessons(snapshot, [{**links[0], "reviewer": ""}])
