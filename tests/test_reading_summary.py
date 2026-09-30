from copy import deepcopy

from app.literature_service import reading_summary


def test_summary_counts_works_preserves_conflicts_and_reads_only_selected_scope():
    items = [{"id": "one", "work_id": "book", "title": "Book"},
             {"id": "two", "work_id": "book", "title": "Book"},
             {"id": "three", "work_id": "other", "title": "Other"}]
    states = {"one": {"reading_status": "read"}, "two": {"reading_status": "in_progress"}}
    before = deepcopy(states)
    result = reading_summary(items, states)
    assert result == {"read": 0, "total": 2, "conflicts": 1, "current": [items[1]]}
    assert reading_summary([items[0]], states) == {"read": 1, "total": 1, "conflicts": 0, "current": []}
    assert reading_summary([], states) == {"read": 0, "total": 0, "conflicts": 0, "current": []}
    assert states == before
