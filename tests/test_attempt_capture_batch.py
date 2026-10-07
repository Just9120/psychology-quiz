"""Bank batches preserve captured byte identity without per-question queries."""
from contextlib import closing
import hashlib
import json

import pytest

from app.attempt_content import capture_questions, get_attempt_content
from app.db import get_connection, upsert_approved_questions, store_session_questions, start_quiz_session
from tests.test_attempt_content import bank, OLD, NEW


class MeasuredReads:
    def __init__(self, conn):
        self.conn, self.calls = conn, 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        return self.conn.execute(*args, **kwargs)


def test_current_bank_batches_preserve_old_attempt_bytes(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = start_quiz_session(conn, 1, 1)
        store_session_questions(conn, sid, [1])
        original = get_attempt_content(conn, sid, 1)
        upsert_approved_questions(conn, [NEW, *[{**OLD, 'id': f'batch-{i}'} for i in range(501)]])
        ids = [row[0] for row in conn.execute("SELECT id FROM questions ORDER BY id")]
        measured = MeasuredReads(conn)
        captures = capture_questions(measured, [*ids, ids[0]])
        assert set(captures) == set(ids)
        assert measured.calls <= 6  # Hundreds of questions must not cause N+1 reads.
        current = json.loads(captures[1][0])
        assert current['question_text'] == NEW['question']
        assert current['explanation'] == NEW['explanation']
        assert [item['option_text'] for item in current['options']] == NEW['options']
        assert [i['option_index'] for i in current['options'] if i['is_correct']] == [1]
        assert captures[1][1] == hashlib.sha256(captures[1][0].encode()).hexdigest()
        assert original['content_sha256'] != captures[1][1]
        assert get_attempt_content(conn, sid, 1) == original
        # Frozen v1 bytes remain identical for an unchanged theory edition.
        expected = ('{"category":"Original category","difficulty":"easy","explanation":"Original explanation",'
                    '"external_id":"batch-0","options":[{"is_correct":1,"option_index":0,"option_text":"Original correct"},'
                    '{"is_correct":0,"option_index":1,"option_text":"Old distractor"},'
                    '{"is_correct":0,"option_index":2,"option_text":"Third"},'
                    '{"is_correct":0,"option_index":3,"option_text":"Fourth"}],'
                    '"question_text":"Original question?","source_ref":"source-v1","version":1}')
        batch_zero = next(value[0] for value in captures.values() if json.loads(value[0])['external_id'] == 'batch-0')
        assert batch_zero == expected
        empty = MeasuredReads(conn)
        assert capture_questions(empty, []) == {} and empty.calls == 0
        with pytest.raises(ValueError, match='missing question'):
            capture_questions(conn, [ids[0], max(ids) + 1])
