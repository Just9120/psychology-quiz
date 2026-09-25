import pytest

from app.source_inventory import InventoryError, link_lessons, processing_status, reconcile, scan


def item(file_id, parent, *, title="Lesson", changed="2026-09-25T00:00:00Z"):
    return {"id": file_id, "parent_ids": [parent], "file_or_folder": "file",
            "title": title, "mime_type": "application/pdf", "modified_time": changed}


def test_recursive_snapshot_requires_complete_children_and_detects_changes():
    root, child = "root", "nested"
    folder = {"id": child, "parent_ids": [root], "file_or_folder": "folder"}
    listings = {root: {"complete": True, "children": [folder, item("first", root)]},
                child: {"complete": True, "children": [item("second", child)]}}
    first = scan(root, listings)
    assert (first["folders"], len(first["files"])) == (2, 2)
    with pytest.raises(InventoryError, match="incomplete_folder_listing"):
        scan(root, {root: listings[root]})
    later = {**listings, child: {"complete": True, "children": [
        item("second", child, changed="2026-09-26T00:00:00Z"), item("third", child)]}}
    assert reconcile(first, scan(root, later)) == {
        "new": ["third"], "changed": ["second"], "unchanged": ["first"], "missing": []}


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


def test_processing_requires_same_revision_and_explicit_lesson_links():
    snapshot = scan("root", {"root": {"complete": True, "children": [
        item("lecture", "root"), item("slides", "root")]}})
    revision = ("2026-09-25T00:00:00Z", "Lesson", "application/pdf")
    states = processing_status(snapshot, {
        "lecture": {"revision": revision, "review_state": "processed"},
        "slides": {"revision": revision, "review_state": "conflict"}})
    assert states == {"lecture": "processed", "slides": "conflict_review"}
    assert processing_status(snapshot, {"lecture": {"revision": ("old", "Lesson", "application/pdf")}})["lecture"] == "changed_unprocessed"
    links = [{"source_id": "lecture", "lesson_id": "l1", "topic_id": "topic", "format": "transcript"},
             {"source_id": "slides", "lesson_id": "l1", "topic_id": "topic", "format": "slides"}]
    assert len(link_lessons(snapshot, links)["l1"]["sources"]) == 2
    with pytest.raises(InventoryError, match="conflicting_lesson_topic"):
        link_lessons(snapshot, [links[0], {**links[1], "topic_id": "other"}])
