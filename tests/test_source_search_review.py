import pytest

from app.source_inventory import InventoryError
from scripts import source_capture, source_finalize, source_search_review
from tests.test_source_inventory_report import export


def test_search_approval_requires_current_processed_exact_extract_and_ranges(tmp_path):
    current = export(["private"])
    content = tmp_path / "private.txt"
    text = "Проверенный фрагмент. Непроверенный фрагмент."
    content.write_text(text, encoding="utf-8")
    pending = source_capture.capture(current, {}, "private", content, "extracted_text")
    processed = source_finalize.finalize(
        current, pending, "private", content, reviewer="editor",
        review_note="Первичный разбор", reviewed_at="2026-09-27T00:00:00Z")
    start, end = 0, len("Проверенный фрагмент.")
    kwargs = {"reviewer": "editor", "note": "Для поиска разрешён только первый тезис",
              "reviewed_at": "2026-09-27T01:00:00Z"}
    approved = source_search_review.approve_ranges(
        current, processed, "private", content, [[start, end]], **kwargs)
    assert approved["private"]["search_ranges"] == [[start, end]]
    assert approved["private"]["search_reviewer"] == "editor"
    assert "search_ranges" not in processed["private"]
    with pytest.raises(InventoryError, match="current_processed_source_required"):
        source_search_review.approve_ranges(
            current, {**processed, "other": {"review_state": "conflict",
                                                 "related_source_ids": ["private"]}},
            "private", content, [[start, end]], **kwargs)
    with pytest.raises(InventoryError, match="current_processed_source_required"):
        source_search_review.approve_ranges(
            current, pending, "private", content, [[start, end]], **kwargs)
    with pytest.raises(InventoryError, match="invalid_private_search_ranges"):
        source_search_review.approve_ranges(
            current, processed, "private", content, [[0, 30], [29, 40]], **kwargs)
    with pytest.raises(InventoryError, match="invalid_private_search_ranges"):
        source_search_review.approve_ranges(
            current, processed, "private", content, [[0, len(text) + 1]], **kwargs)
    content.write_text(text + " изменено", encoding="utf-8")
    with pytest.raises(InventoryError, match="captured_content_changed"):
        source_search_review.approve_ranges(
            current, processed, "private", content, [[start, end]], **kwargs)
