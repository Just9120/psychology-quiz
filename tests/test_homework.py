"""Homework grading and ownership over durable shared quiz attempts."""
from contextlib import closing
import json
from pathlib import Path

from app.db import create_or_load_user, get_connection, upsert_approved_questions
from app.homework import catalog_for_actor, load_catalog, outcome_for_session, passed, start_homework, validate_bank
from app.homework_schema import migrate_homework_schema
from app.quiz_service import answer_quiz
from app.identity_schema import migrate_identity_schema
from app.learning_schema import migrate_learning_schema
from app.miniapp_api import build_homework_response
from tests.test_miniapp_api import _make_init_data


def _bank(path):
    with closing(get_connection(str(path))) as conn, conn:
        conn.executescript(Path("sql/schema.sql").read_text(encoding="utf-8"))
        migrate_identity_schema(conn)
        migrate_learning_schema(conn)
        migrate_homework_schema(conn)
        questions = []
        for source in Path("content/questions").rglob("*.json"):
            questions.extend(item for item in json.loads(Path(source).read_text(encoding="utf-8"))
                             if item["status"] == "approved")
        upsert_approved_questions(conn, questions, authoritative=True)
        owner = create_or_load_user(conn, 10001, None, "Student A", None)
        other = create_or_load_user(conn, 10002, None, "Student B", None)
        return int(owner["id"]), int(other["id"])


def _finish(conn, actor, state, correct_count):
    session = int(state["session"]["session_id"])
    rows = conn.execute("""SELECT question_id FROM quiz_session_questions
        WHERE session_id=? ORDER BY order_index""", (session,)).fetchall()
    for index, row in enumerate(rows):
        options = conn.execute("""SELECT option_index,is_correct FROM question_options
            WHERE question_id=? ORDER BY option_index""", (row[0],)).fetchall()
        chosen = next(option[0] for option in options if bool(option[1]) == (index < correct_count))
        result = answer_quiz(conn, actor_user_id=actor, session_id=session,
                             question_id=int(row[0]), selected_option_index=int(chosen))
        assert result["submission_status"] == "accepted"
    return session


def _entry(conn, actor, key="first_consultation"):
    return next(item for item in catalog_for_actor(conn, actor)["assignments"] if item["id"] == key)


def test_single_attempt_threshold_retry_and_actor_isolation(tmp_path):
    path = tmp_path / "homework.sqlite3"
    actor, other = _bank(path)
    assert not passed(79, 100)
    assert passed(80, 100)
    assert passed(5, 5)
    with closing(get_connection(str(path))) as conn, conn:
        first = start_homework(conn, actor_user_id=actor, assignment_id="first_consultation",
                               payload={"replace_active": False})
        session = int(first["runner_state"]["session"]["session_id"])
        assert _entry(conn, actor)["active_session_id"] == session
        assert not _entry(conn, actor)["completed"]
        _finish(conn, actor, first["runner_state"], 3)
        assert not outcome_for_session(conn, actor_user_id=actor, session_id=session)["passed"]
        assert not _entry(conn, actor)["completed"]
        second = start_homework(conn, actor_user_id=actor, assignment_id="first_consultation",
                                payload={"replace_active": False})
        passed_session = _finish(conn, actor, second["runner_state"], 4)
        assert outcome_for_session(conn, actor_user_id=actor, session_id=passed_session)["passed"]
        assert _entry(conn, actor)["completed"]
        assert _entry(conn, actor)["finished_attempts"] == 2
        assert not _entry(conn, other)["completed"]
        assert outcome_for_session(conn, actor_user_id=other, session_id=passed_session) is None
    with closing(get_connection(str(path))) as reopened:
        assert _entry(reopened, actor)["completed"]
        assert not _entry(reopened, other)["completed"]


def test_incomplete_attempt_and_duplicate_answer_do_not_earn_credit(tmp_path):
    path = tmp_path / "incomplete.sqlite3"
    actor, _ = _bank(path)
    with closing(get_connection(str(path))) as conn, conn:
        started = start_homework(conn, actor_user_id=actor, assignment_id="professional_diary",
                                 payload={"replace_active": False})
        state = started["runner_state"]
        question = state["current_question"]
        right = next(option[0] for option in conn.execute(
            "SELECT option_index,is_correct FROM question_options WHERE question_id=?",
            (question["question_id"],)) if option[1])
        first = answer_quiz(conn, actor_user_id=actor, session_id=question["session_id"],
                            question_id=question["question_id"], selected_option_index=right)
        duplicate = answer_quiz(conn, actor_user_id=actor, session_id=question["session_id"],
                                question_id=question["question_id"], selected_option_index=right)
        assert first["submission_status"] == "accepted"
        assert duplicate["submission_status"] == "duplicate"
        assert not _entry(conn, actor, "professional_diary")["completed"]
        assert not outcome_for_session(conn, actor_user_id=actor, session_id=question["session_id"])["attempt_finished"]


def test_miniapp_homework_requires_verified_actor_and_shares_attempts(tmp_path):
    path = tmp_path / "homework-api.sqlite3"
    actor, _ = _bank(path)
    token = "123:homework-test"
    owner_data = _make_init_data(token, {"id": 10001, "first_name": "Student A"})
    other_data = _make_init_data(token, {"id": 10002, "first_name": "Student B"})
    status, _, body = build_homework_response(str(path), token, "catalog", "invalid")
    assert status == 401
    assert not json.loads(body)["ok"]
    status, _, body = build_homework_response(str(path), token, "start", owner_data,
        json.dumps({"assignment_id": "first_consultation", "replace_active": False}).encode())
    assert status == 200
    state = json.loads(body)["runner_state"]
    with closing(get_connection(str(path))) as conn, conn:
        _finish(conn, actor, state, 4)
    status, _, body = build_homework_response(str(path), token, "catalog", owner_data)
    assert status == 200
    assert next(a for a in json.loads(body)["assignments"] if a["id"] == "first_consultation")["completed"]
    status, _, body = build_homework_response(str(path), token, "catalog", other_data)
    assert status == 200
    assert not next(a for a in json.loads(body)["assignments"] if a["id"] == "first_consultation")["completed"]


def test_homework_runner_and_feedback_do_not_project_private_provenance(tmp_path):
    path = tmp_path / 'homework-projection.sqlite3'
    actor, _ = _bank(path)
    private_ref = 'drive:private-homework-source-0123456789#characters:1:20'
    forbidden_fields = {'source_ref', 'source_refs', 'source_title', 'external_id',
                        'publication_review', 'quality_review', 'content_snapshot', 'review_sha256'}

    def assert_public(value):
        if isinstance(value, dict):
            assert not forbidden_fields.intersection(value)
            for child in value.values():
                assert_public(child)
        elif isinstance(value, list):
            for child in value:
                assert_public(child)
        elif isinstance(value, str):
            assert private_ref not in value and 'drive:' not in value

    with closing(get_connection(str(path))) as conn, conn:
        # Private DB provenance remains available for review; clients receive
        # only the presentation projection even for immutable attempt snapshots.
        conn.execute('UPDATE questions SET source_ref=?', (private_ref,))
        result = start_homework(conn, actor_user_id=actor, assignment_id='first_consultation',
                                payload={'replace_active': False})
        assert_public(result)
        state = result['runner_state']
        session = state['session']['session_id']
        for row in conn.execute('SELECT question_id FROM quiz_session_questions WHERE session_id=? ORDER BY order_index', (session,)).fetchall():
            feedback = answer_quiz(conn, actor_user_id=actor, session_id=session,
                                   question_id=int(row[0]), selected_option_index=0)
            assert_public(feedback)
            assert feedback['submission_status'] == 'accepted'
        assert_public(catalog_for_actor(conn, actor))
        snapshots = conn.execute('SELECT content_snapshot FROM quiz_session_questions WHERE session_id=?', (session,)).fetchall()
        assert snapshots and all(private_ref in row[0] for row in snapshots)

def test_all_published_tasks_start_with_reviewed_questions_and_preserve_old_credit(tmp_path):
    path = tmp_path / 'expanded-homework.sqlite3'
    actor, other = _bank(path)
    original = {'professional_reflection', 'professional_diary', 'observation_and_listening', 'first_consultation'}
    with closing(get_connection(str(path))) as conn, conn:
        validate_bank(conn)
        catalog = load_catalog()
        assert original.issubset({item['id'] for item in catalog})
        old = start_homework(conn, actor_user_id=actor, assignment_id='first_consultation',
                             payload={'replace_active': False})
        old_session = _finish(conn, actor, old['runner_state'], 4)
        for assignment in catalog:
            started = start_homework(conn, actor_user_id=actor, assignment_id=assignment['id'],
                                     payload={'replace_active': False})
            session_id = started['runner_state']['session']['session_id']
            selected = {row[0] for row in conn.execute('''SELECT q.external_id FROM quiz_session_questions sq
                JOIN questions q ON q.id=sq.question_id WHERE sq.session_id=?''', (session_id,))}
            assert selected == set(assignment['question_ids'])
            _finish(conn, actor, started['runner_state'], len(selected))
            assert _entry(conn, actor)['completed']
            assert outcome_for_session(conn, actor_user_id=other, session_id=session_id) is None
        assert outcome_for_session(conn, actor_user_id=actor, session_id=old_session)['passed']
        assert not any(item['completed'] for item in catalog_for_actor(conn, other)['assignments'])
