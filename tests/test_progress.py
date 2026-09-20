from contextlib import closing
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db import get_connection, create_or_load_user, start_quiz_session, store_session_questions, upsert_approved_questions, finalize_quiz_session
from app.attempt_content import capture_question
from app.quiz_service import answer_quiz
from app import progress_service as progress
from app import learning_reset
from tests.test_attempt_content import bank, OLD, OTHER, NEW


def record(conn, actor=1, qids=(1,), choices=(1,)):
    sid = start_quiz_session(conn, actor, None)
    store_session_questions(conn, sid, list(qids))
    for qid, choice in zip(qids, choices):
        answer_quiz(conn, actor_user_id=actor, session_id=sid, question_id=qid, selected_option_index=choice)
    return sid


def reset_payload(preview):
    return {"scope": preview["scope"], "topic": preview["topic"], "confirm": True,
            "expected_revision": preview["revision"]}


def test_reset_topic_preserves_mixed_answers_snapshots_foreign_and_literature(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        completed = record(conn, qids=(1, 2), choices=(0, 1))
        active = record(conn, qids=(2, 1), choices=(0,))
        stranger = create_or_load_user(conn, 98, None, None, None)['id']
        foreign = record(conn, actor=stranger)
        kept = [tuple(row) for row in conn.execute('SELECT * FROM quiz_answers WHERE question_id=2 OR session_id=? ORDER BY id', (foreign,))]
        snapshots = [tuple(row) for row in conn.execute('SELECT * FROM quiz_session_questions WHERE question_id=2 ORDER BY id')]
        literature = [tuple(row) for row in conn.execute('SELECT * FROM user_literature_progress')]
        users = [tuple(row) for row in conn.execute('SELECT * FROM users ORDER BY id')]
        upsert_approved_questions(conn, [{**NEW, 'category': 'New category'}])
        bank_rows = [tuple(row) for row in conn.execute('SELECT * FROM questions ORDER BY id')]
        preview = learning_reset.preview(conn, 1, {'scope': 'topic', 'topic': OLD['category']})
        assert (preview['answers'], preview['questions'], preview['attempts'], preview['active_attempts']) == (1, 2, 2, 1)
        assert progress.overview(conn, 1)['summary']['answered'] == 3  # preview/cancel is read-only
        assert learning_reset.confirm(conn, 1, reset_payload(preview))['deleted_answers'] == 1
        assert [tuple(row) for row in conn.execute('SELECT * FROM quiz_answers ORDER BY id')] == kept
        assert [tuple(row) for row in conn.execute('SELECT * FROM quiz_session_questions WHERE question_id=2 ORDER BY id')] == snapshots
        assert [tuple(row) for row in conn.execute('SELECT * FROM user_literature_progress')] == literature
        assert [tuple(row) for row in conn.execute('SELECT * FROM users ORDER BY id')] == users
        assert [tuple(row) for row in conn.execute('SELECT * FROM questions ORDER BY id')] == bank_rows
        assert tuple(conn.execute('SELECT status,score,total_questions FROM quiz_sessions WHERE id=?', (completed,)).fetchone()) == ('finished', 0, 1)
        assert conn.execute('SELECT status FROM quiz_sessions WHERE id=?', (active,)).fetchone()[0] == 'abandoned'
        late = answer_quiz(conn, actor_user_id=1, session_id=active, question_id=1, selected_option_index=0)
        assert late['submission_status'] != 'accepted'
        assert finalize_quiz_session(conn, active) is None
        assert conn.execute('SELECT status FROM quiz_sessions WHERE id=?', (active,)).fetchone()[0] == 'abandoned'
        assert progress.overview(conn, 1)['summary']['answered'] == 2
        assert progress.attempt(conn, 1, completed)['items'][0]['topic'] == OTHER['category']


def test_reset_all_and_old_confirmation_cannot_remove_new_learning(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = record(conn)
        preview = learning_reset.preview(conn, 1, {'scope': 'all'})
        for confirm in (False, 'true', 1, None):
            with pytest.raises(progress.ProgressError, match='reset_confirmation_required'):
                learning_reset.confirm(conn, 1, {**reset_payload(preview), 'confirm': confirm})
        with pytest.raises(progress.ProgressError, match='reset_confirmation_required'):
            learning_reset.confirm(conn, 1, {**reset_payload(preview), 'expected_revision': 'я' * 64})
        assert len(progress.history(conn, 1)['items']) == 1
        learning_reset.confirm(conn, 1, reset_payload(preview))
        assert progress.history(conn, 1)['items'] == []
        assert progress.errors(conn, 1)['total'] == 0
        for table in ('quiz_answers', 'quiz_session_questions', 'quiz_session_selected_categories'):
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE session_id=?', (sid,)).fetchone()[0] == 0
        assert conn.execute('SELECT private_note FROM user_literature_progress WHERE user_id=1').fetchone()[0] == 'Private note'
        new_sid = record(conn)
        assert new_sid > sid
        with pytest.raises(progress.ProgressError, match='reset_changed'):
            learning_reset.confirm(conn, 1, reset_payload(preview))
        assert progress.history(conn, 1)['items'][0]['session_id'] == new_sid


def test_reset_confirmation_rejects_changed_answer_and_other_actor(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = record(conn, qids=(1, 2), choices=(1,))
        preview = learning_reset.preview(conn, 1, {'scope': 'all'})
        answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=2, selected_option_index=0)
        with pytest.raises(progress.ProgressError, match='reset_changed'):
            learning_reset.confirm(conn, 1, reset_payload(preview))
        stranger = create_or_load_user(conn, 98, None, None, None)['id']
        with pytest.raises(progress.ProgressError, match='reset_changed'):
            learning_reset.confirm(conn, stranger, reset_payload(preview))
        assert progress.overview(conn, 1)['summary']['answered'] == 2
        for payload in ({}, {'scope': 'all', 'topic': OLD['category']}, {'scope': 'topic', 'topic': []}):
            with pytest.raises(progress.ProgressError, match='invalid_reset_scope'):
                learning_reset.preview(conn, 1, payload)


def test_reset_transaction_failure_rolls_back_all_learning(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = record(conn, qids=(1, 2), choices=(0, 1))
    with closing(get_connection(str(bank))) as conn:
        with pytest.raises(RuntimeError, match='interrupted'):
            with conn:
                preview = learning_reset.preview(conn, 1, {'scope': 'all'})
                learning_reset.confirm(conn, 1, reset_payload(preview))
                raise RuntimeError('interrupted')
        assert progress.attempt(conn, 1, sid)['attempt']['answered'] == 2


def test_concurrent_resets_commit_once(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        record(conn)
        preview = learning_reset.preview(conn, 1, {'scope': 'all'})
    def reset():
        try:
            with closing(get_connection(str(bank))) as conn, conn:
                learning_reset.confirm(conn, 1, reset_payload(preview))
                return 'reset'
        except progress.ProgressError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(lambda _: reset(), range(2))) == ['reset', 'reset_changed']


def test_empty_counts_and_partial_history_isolation(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        assert progress.overview(conn, 1)['summary'] == {'answered': 0, 'correct': 0, 'accuracy': None, 'attempts': 0, 'finished': 0}
        assert progress.history(conn, 1)['items'] == []
        assert progress.errors(conn, 1)['trainable_count'] == 0
        sid = record(conn, qids=(1, 2), choices=(1,))
        stranger = create_or_load_user(conn, 99, None, None, None)['id']
        foreign = record(conn, actor=stranger, choices=(0,))
        summary = progress.overview(conn, 1)['summary']
        assert summary == {'answered': 1, 'correct': 0, 'accuracy': 0, 'attempts': 1, 'finished': 0}
        item = progress.history(conn, 1)['items'][0]
        assert item['session_id'] == sid and item['status'] == 'in_progress' and item['total_questions'] == 2
        detail = progress.attempt(conn, 1, sid)
        assert [item['question_id'] for item in detail['items']] == [1]  # No unanswered correct choices.
        for inaccessible in (foreign, 99999):
            with pytest.raises(progress.ProgressError, match='attempt_not_found'):
                progress.attempt(conn, 1, inaccessible)
        assert progress.errors(conn, stranger)['total'] == 0


def test_history_pagination_and_historical_topic_daily_aggregates(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sessions = [record(conn, choices=(i % 2,)) for i in range(23)]
        first = progress.history(conn, 1)
        second = progress.history(conn, 1, first['next_before'])
        assert [item['session_id'] for item in first['items'] + second['items']] == list(reversed(sessions))
        assert second['next_before'] is None
        conn.execute("UPDATE quiz_answers SET answered_at='2026-09-18 12:00:00' WHERE session_id<?", (sessions[-1],))
        conn.execute("UPDATE quiz_answers SET answered_at='2026-09-20 12:00:00' WHERE session_id=?", (sessions[-1],))
        upsert_approved_questions(conn, [{**NEW, 'category': 'Renamed topic'}])
        stats = progress.overview(conn, 1)
        assert stats['summary']['answered'] == 23 and stats['summary']['correct'] == 12
        assert stats['summary']['finished'] == 23
        assert stats['topics'][0]['topic'] == OLD['category']
        assert [item['day'] for item in stats['days']] == ['2026-09-18', '2026-09-20']
        assert stats['days'][0]['answered'] == 22 and stats['days'][0]['correct'] == 11
        assert stats['topics'][0]['days'] == stats['days']
        old = progress.attempt(conn, 1, sessions[1])['items'][0]
        assert old['question_text'] == OLD['question'] and old['correct_option_text'] == OLD['options'][0]


def test_last_answer_per_edition_and_retired_content(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        old = record(conn)
        errors = progress.errors(conn, 1)
        assert errors['trainable_count'] == 1 and errors['total'] == 1
        # A correct repeat resolves this edition but does not erase past answers.
        record(conn, choices=(0,))
        assert progress.errors(conn, 1)['total'] == 0
        assert progress.attempt(conn, 1, old)['items'][0]['is_correct'] is False
        # Wrong again; the bank changes. The old error trains the NEW content.
        last = record(conn)
        upsert_approved_questions(conn, [NEW])
        errors = progress.errors(conn, 1)
        assert errors['items'][0]['edition_state'] == 'changed'
        assert errors['items'][0]['explanation'] == OLD['explanation']
        trained = progress.train_errors(conn, 1, {'expected_session_id': last, 'replace_active': False, 'question_count': 5})
        question = trained['runner_state']['current_question']
        assert question['question_text'] == NEW['question'] and question['total_questions'] == 1
        answer_quiz(conn, actor_user_id=1, session_id=question['session_id'], question_id=1, selected_option_index=1)
        errors = progress.errors(conn, 1)
        assert errors['total'] == 1 and errors['trainable_count'] == 0
        assert errors['items'][0]['trainable'] is False  # Historical edition remains readable.
        upsert_approved_questions(conn, [{**NEW, 'status': 'retired'}])
        assert progress.errors(conn, 1)['items'][0]['edition_state'] == 'retired'


def test_training_cas_preserves_active_and_replay_and_uses_only_own_errors(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = record(conn, qids=(1, 2), choices=(1,))
        payload = {'expected_session_id': sid, 'replace_active': False, 'question_count': None}
        with pytest.raises(progress.ProgressError, match='active_attempt'):
            progress.train_errors(conn, 1, payload)
        assert conn.execute('SELECT status FROM quiz_sessions WHERE id=?', (sid,)).fetchone()[0] == 'in_progress'
        payload['replace_active'] = True
        result = progress.train_errors(conn, 1, payload)
        new_sid = result['runner_state']['session']['session_id']
        assert new_sid != sid
        assert result['runner_state']['progress']['total_questions'] == 1
        with pytest.raises(progress.ProgressError, match='practice_changed'):
            progress.train_errors(conn, 1, payload)
        assert conn.execute('SELECT count(*) FROM quiz_sessions WHERE user_id=1').fetchone()[0] == 2
        assert progress.history(conn, 1)['items'][1]['status'] == 'abandoned'
        stranger = create_or_load_user(conn, 98, None, None, None)['id']
        with pytest.raises(progress.ProgressError, match='no_errors'):
            progress.train_errors(conn, stranger, {'expected_session_id': None, 'replace_active': False})


@pytest.mark.parametrize('value', [True, -1, 0, 2**63, '1', [], {}])
def test_pagination_and_detail_reject_non_ids(bank, value):
    with closing(get_connection(str(bank))) as conn:
        for action in (lambda: progress.history(conn, 1, value), lambda: progress.errors(conn, 1, value),
                       lambda: progress.attempt(conn, 1, value)):
            with pytest.raises(progress.ProgressError, match='invalid_payload'):
                action()


def test_detail_and_error_pagination(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        upsert_approved_questions(conn, [{**OLD, 'id': f'extra-{i}'} for i in range(24)])
        qids = [row[0] for row in conn.execute('SELECT id FROM questions ORDER BY id')]
        sid = record(conn, qids=qids, choices=[1] * len(qids))
        first = progress.attempt(conn, 1, sid)
        second = progress.attempt(conn, 1, sid, first['next_after'])
        assert [item['question_id'] for item in first['items'] + second['items']] == qids
        e1 = progress.errors(conn, 1)
        e2 = progress.errors(conn, 1, e1['next_before'])
        assert len({item['answer_id'] for item in e1['items'] + e2['items']}) == len(qids)
        assert e2['next_before'] is None


def test_legacy_backfill_is_not_proof_of_current_correctness(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = start_quiz_session(conn, 1, None)
        snapshot, digest = capture_question(conn, 1)
        conn.execute('''INSERT INTO quiz_session_questions
            (session_id,question_id,order_index,content_snapshot,content_sha256,snapshot_provenance)
            VALUES (?,1,1,?,?,'legacy_backfill_current')''', (sid, snapshot, digest))
        answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=1, selected_option_index=1)
        item = progress.errors(conn, 1)['items'][0]
        assert item['snapshot_provenance'] == 'legacy_backfill_current' and item['trainable'] is True
        record(conn, choices=(0,))
        assert progress.errors(conn, 1)['trainable_count'] == 0
        assert progress.attempt(conn, 1, sid)['items'][0]['is_correct'] is False


def test_concurrent_training_retries_create_one_attempt(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        sid = record(conn)
    def start():
        try:
            with closing(get_connection(str(bank))) as conn, conn:
                return progress.train_errors(conn, 1, {'expected_session_id': sid, 'replace_active': False})['ok']
        except progress.ProgressError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(), range(2)))
    assert results.count(True) == 1 and results.count('practice_changed') == 1
    with closing(get_connection(str(bank))) as conn:
        assert conn.execute("SELECT count(*) FROM quiz_sessions WHERE user_id=1 AND status='in_progress'").fetchone()[0] == 1


def test_daily_window_does_not_truncate_totals(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        for day in range(1, 19):
            sid = record(conn, choices=(0,))
            conn.execute('UPDATE quiz_answers SET answered_at=? WHERE session_id=?', (f'2026-09-{day:02} 12:00:00', sid))
        stats = progress.overview(conn, 1)
        assert stats['summary']['answered'] == 18 and stats['topics'][0]['answered'] == 18
        assert len(stats['days']) == len(stats['topics'][0]['days']) == 14
        assert stats['days'][0]['day'] == '2026-09-05'


def test_legacy_correct_answer_cannot_resolve_captured_mistake(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        record(conn)
        sid = start_quiz_session(conn, 1, None)
        snapshot, digest = capture_question(conn, 1)
        conn.execute('''INSERT INTO quiz_session_questions
            (session_id,question_id,order_index,content_snapshot,content_sha256,snapshot_provenance)
            VALUES (?,1,1,?,?,'legacy_backfill_current')''', (sid, snapshot, digest))
        answer_quiz(conn, actor_user_id=1, session_id=sid, question_id=1, selected_option_index=0)
        errors = progress.errors(conn, 1)
        assert errors['total'] == errors['trainable_count'] == 1
        assert errors['items'][0]['snapshot_provenance'] == 'captured'
