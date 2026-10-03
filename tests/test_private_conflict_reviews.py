import copy

from app.source_inventory import private_conflict_reviews


def test_private_conflicts_keep_independent_issues_and_explicit_lesson_context():
    processing = {
        'transcript': {'revision': ['old-revision', 'Lecture', 'text/plain'],
                       'review_state': 'conflict', 'reason': 'Combined summary',
                       'issues': [
                           {'reason': 'Numeric disagreement', 'locator': 'characters:10:20',
                            'related_source_ids': ['slides'], 'reviewed_at': '2026-10-03'},
                           {'reason': 'Separate assertion', 'locator': 'characters:40:50',
                            'related_source_ids': [], 'reviewed_at': '2026-10-03'}]},
        'unreviewed': {'revision': ['current', 'Other', 'text/plain'], 'review_state': 'pending_review'},
        'prior-hold': {'revision': ['current', 'Changed source', 'text/plain'],
                      'review_state': 'pending_review',
                      'conflict_hold': {'reason': 'Still unresolved', 'locator': 'page:2',
                                        'related_source_ids': ['transcript']}},
    }
    original = copy.deepcopy(processing)
    lessons = {'transcript': {'lesson'}, 'slides': {'lesson'}, 'handout': {'lesson'},
               'similar-name': {'different-lesson'}}
    report = private_conflict_reviews(processing, lessons)
    assert processing == original
    assert len(report) == 2
    transcript = next(row for row in report if row['file_id'] == 'transcript')
    assert transcript['held_revision'][0] == 'old-revision'
    assert transcript['linked_lesson_ids'] == ['lesson']
    assert transcript['lesson_context_source_ids'] == ['handout', 'slides']
    assert [issue['locator'] for issue in transcript['issues']] == ['characters:10:20', 'characters:40:50']
    assert transcript['issues'][1]['related_source_ids'] == []
    assert next(row for row in report if row['file_id'] == 'prior-hold')['issues'][0]['reason'] == 'Still unresolved'


def test_legacy_conflict_without_locator_stays_explicitly_unknown():
    report = private_conflict_reviews({'source': {'revision': ['r', 't', 'm'],
                                                 'review_state': 'conflict', 'reason': 'Disagreement'}}, {})
    assert report[0]['issues'][0]['locator'] is None
    assert report[0]['lesson_context_source_ids'] == []
