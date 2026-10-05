import pytest

from app import literature_service
from app.reading_schema import migrate_reading_schema
from tests.test_reading_work_migration import make_connection, legacy, add, ITEMS


@pytest.fixture
def runtime(monkeypatch):
    items = [{**item, "topic_id": item['id'], "title": "Book", "authors": [],
              "type": "book", "access_links": [], "book_search": {"query": "Book", "url": "https://www.google.com/search?q=Book"}, "module": "module1"} for item in ITEMS]
    monkeypatch.setattr(literature_service, 'load_literature_items', lambda: items)
    monkeypatch.setattr(literature_service, 'load_topic_registry', lambda: {
        item['id']: {'title': item['id'], 'module': 'module1', 'order': n} for n,item in enumerate(items)})
    conn = make_connection()
    yield conn
    conn.close()


def test_status_is_shared_across_associations_but_not_actors_and_history_is_untouched(runtime):
    conn = runtime
    add(conn, legacy(1, 'one', 'in_progress', '2026-09-01T12:00:00Z'))
    add(conn, legacy(1, 'two', 'revisit', '2026-09-29T12:00:00Z'))
    migrate_reading_schema(conn, ITEMS)
    before = [tuple(row) for row in conn.execute('SELECT * FROM user_literature_progress')]
    states = literature_service.load_progress(conn, 1)
    assert {state['reading_status'] for state in states.values()} == {'deferred'}
    saved = literature_service.save_progress(conn, 1, 'one', 'read', None)
    assert saved['work_id'] == 'book' and saved['progress_percent'] is None
    states = literature_service.load_item_states(conn, 1)
    assert {state['reading_status'] for state in states.values()} == {'read'}
    assert states['one']['literature_id'] == 'one' and states['two']['literature_id'] == 'two'
    assert literature_service.load_progress(conn, 2) == {}
    literature_service.save_progress(conn, 2, 'two', 'in_progress', None)
    assert literature_service.load_progress(conn, 1)['one']['reading_status'] == 'read'
    assert literature_service.load_progress(conn, 2)['one']['reading_status'] == 'in_progress'
    assert conn.execute('SELECT COUNT(*) FROM user_literature_work_progress').fetchone()[0] == 2
    assert [tuple(row) for row in conn.execute('SELECT * FROM user_literature_progress')] == before
    catalog = literature_service.catalog(conn, 1)
    assert len(catalog['works']) == 1
    assert {entry['user_state']['reading_status'] for entry in catalog['works'][0]['entries']} == {'read'}
    assert 'private retained history' not in str(catalog)


def test_four_statuses_and_progress_rejection_at_write_boundary(runtime):
    conn = runtime
    migrate_reading_schema(conn, ITEMS)
    for status in ('not_started', 'in_progress', 'read', 'deferred'):
        assert literature_service.validate_progress({'literature_id':'one','reading_status':status}) == ('one',status,None)
        assert literature_service.save_progress(conn, 1, 'one', status, None)['reading_status'] == status
    for status in ('revisit', 'skipped', 'invalid'):
        assert literature_service.validate_progress({'literature_id':'one','reading_status':status}) == 'invalid_reading_status'
        with pytest.raises(ValueError, match='invalid_reading_status'):
            literature_service.save_progress(conn, 1, 'one', status, None)
    with pytest.raises(ValueError, match='manual_progress_not_supported'):
        literature_service.save_progress(conn, 1, 'one', 'read', 100)
    with pytest.raises(ValueError, match='unknown_literature_id'):
        literature_service.save_progress(conn, 1, 'missing', 'read', None)


def test_completion_date_is_not_reset_by_repeated_read_and_write_can_roll_back(runtime, monkeypatch):
    conn = runtime
    migrate_reading_schema(conn, ITEMS)
    conn.commit()
    monkeypatch.setattr(literature_service, '_utc_timestamp', lambda: '2026-09-30T12:00:00Z')
    with conn:
        first = literature_service.save_progress(conn, 1, 'one', 'read', None)
    monkeypatch.setattr(literature_service, '_utc_timestamp', lambda: '2026-10-01T12:00:00Z')
    with conn:
        repeated = literature_service.save_progress(conn, 1, 'two', 'read', None)
    assert repeated['completed_at'] == first['completed_at']
    with pytest.raises(RuntimeError), conn:
        literature_service.save_progress(conn, 1, 'one', 'deferred', None)
        raise RuntimeError('rollback')
    assert literature_service.load_progress(conn, 1)['one']['reading_status'] == 'read'
    with conn:
        reset = literature_service.save_progress(conn, 1, 'two', 'not_started', None)
    assert reset['started_at'] is None and reset['completed_at'] is None
