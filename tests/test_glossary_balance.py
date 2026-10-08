"""Finite mixed attempts cover selected topics and preserve captured choices."""
from collections import Counter
from contextlib import closing
import json
import random

import pytest

from app import glossary_service as glossary
from app.db import get_connection
from tests.test_attempt_content import bank
from tests.test_glossary_retries import call
from tests.test_glossary_runtime import make_glossary_entry


@pytest.mark.parametrize('sizes,count', [([11, 10, 10], 5), ([4, 20], 10),
                                        ([4] * 8, 5), ([4, 7, 12], 'all')])
def test_balanced_mixed_snapshot_and_resume(bank, monkeypatch, sizes, count):
    topics = [f'topic_{i}' for i in range(len(sizes))]
    buckets = {topic: [make_glossary_entry(f'{topic}_{j}', f'Meaning {topic}_{j}', topic_id=topic)
                       for j in range(size)] for topic, size in zip(topics, sizes)}
    monkeypatch.setattr(glossary, 'GLOSSARY_TOPICS', [(topic, topic) for topic in topics])
    monkeypatch.setattr(glossary, 'load_glossary_entries', buckets.get)
    # Different draws must preserve balance, rather than occasionally passing
    # a probabilistic coverage assertion on one fortunate seed.
    for seed in range(5):
        monkeypatch.setattr(glossary, 'random', random.Random(seed))
        previous = call(bank, glossary.state)
        active = previous.get('session_id') if previous['state'] != 'idle' else None
        started = call(bank, glossary.start, topics, count,
                       expected_session_id=active, replace_active=bool(active))
        sid = started['session_id']
        with closing(get_connection(str(bank))) as conn:
            captured = json.loads(conn.execute('SELECT snapshot FROM glossary_sessions WHERE id=?', (sid,)).fetchone()[0])
        entries = [item['entry'] for item in captured['questions']]
        limit = sum(sizes) if count == 'all' else count
        assert len(entries) == len({entry['id'] for entry in entries}) == limit
        counts = Counter(entry['topic_id'] for entry in entries)
        if count == 'all':
            assert counts == dict(zip(topics, sizes))
        else:
            assert len(counts) == min(len(topics), limit)
            unsaturated = [counts[topic] for topic, size in zip(topics, sizes) if counts[topic] < size]
            assert max(unsaturated) - min(unsaturated) <= 1
        assert call(bank, glossary.state, sid) == started
        first = started['current_question']
        response = call(bank, glossary.answer, sid, -1, first['step_id'])
        assert call(bank, glossary.answer, sid, -1, first['step_id']) == response
        following = call(bank, glossary.advance, sid, first['step_id'])
        assert call(bank, glossary.advance, sid, first['step_id']) == following
        assert call(bank, glossary.state, sid) == following
        with closing(get_connection(str(bank))) as conn:
            assert json.loads(conn.execute('SELECT snapshot FROM glossary_sessions WHERE id=?', (sid,)).fetchone()[0]) == captured
