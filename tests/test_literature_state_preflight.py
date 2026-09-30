from app.literature_state_preflight import summarize


def test_preview_counts_conflicts_per_actor_without_disclosing_identity():
    items = [{'id': 'a', 'work_id': 'one'}, {'id': 'b', 'work_id': 'one'}]
    rows = [
        {'user_id': 42, 'literature_id': 'a', 'reading_status': 'read', 'progress_percent': 100},
        {'user_id': 42, 'literature_id': 'b', 'reading_status': 'in_progress', 'progress_percent': None},
        {'user_id': 99, 'literature_id': 'a', 'reading_status': 'read', 'progress_percent': None},
        {'user_id': 99, 'literature_id': 'missing', 'reading_status': 'read', 'progress_percent': None},
    ]
    result = summarize(rows, items)
    assert result == {'ok': True, 'reading_rows': 4, 'actor_work_pairs': 2,
                      'multiple_associations': 1, 'conflicting_statuses': 1,
                      'legacy_progress_rows': 1, 'unknown_association_rows': 1}
    assert '42' not in str(result) and '99' not in str(result)
    assert rows[0]['reading_status'] == 'read'
