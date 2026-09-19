from concurrent.futures import ThreadPoolExecutor
import json

from fastapi.testclient import TestClient
import pytest

from app import miniapp_glossary as glossary
from app.miniapp_fastapi import create_app
from tests.test_glossary_runtime import make_glossary_entry
from tests.test_miniapp_api import _make_init_data


@pytest.fixture
def session(monkeypatch):
    entries = [make_glossary_entry(str(i), f"Meaning {i}") for i in range(5)]
    monkeypatch.setattr(glossary, "GLOSSARY_TOPICS", [("fixture_topic", "Fixture")])
    monkeypatch.setattr(glossary, "load_glossary_entries", lambda _: entries)
    monkeypatch.setattr(glossary, "_SESSIONS", {})
    state = glossary.start_glossary_session(42, "fixture_topic", 5)
    return state["current_question"]


def correct_index(question):
    expected = "Meaning " + question["term"].removeprefix("Term ")
    return next(option["option_index"] for option in question["options"] if option["option_text"] == expected)


def test_repeat_next_preserves_displayed_options_and_scoring(session):
    sid, step = session["session_id"], session["step_id"]
    for _ in range(20):
        assert glossary.next_glossary_session(42, sid, step)["current_question"] == session
    selected = correct_index(session)
    feedback = glossary.answer_glossary_session(42, sid, selected, step)
    assert feedback["feedback"]["is_correct"] is True
    # Returned JSON cannot mutate the committed cache.
    feedback["feedback"]["is_correct"] = False
    assert glossary.answer_glossary_session(42, sid, selected, step)["feedback"]["is_correct"] is True
    next_state = glossary.next_glossary_session(42, sid, step)
    assert next_state["current_question"]["step_id"] == 2
    assert glossary.next_glossary_session(42, sid, step) == next_state
    assert glossary.get_session(sid, 42).score == 1


def test_concurrent_answer_and_next_commit_only_once(session):
    sid, step = session["session_id"], session["step_id"]
    selected = correct_index(session)
    with ThreadPoolExecutor(max_workers=8) as pool:
        answers = list(pool.map(lambda _: glossary.answer_glossary_session(42, sid, selected, step), range(40)))
        advances = list(pool.map(lambda _: glossary.next_glossary_session(42, sid, step), range(40)))
    assert all(answer == answers[0] for answer in answers)
    assert all(state == advances[0] for state in advances)
    assert glossary.get_session(sid, 42).score == 1
    assert glossary.get_session(sid, 42).current_index == 1


def test_delayed_old_operations_do_not_change_another_answered_step(session):
    sid = session["session_id"]
    first = glossary.answer_glossary_session(42, sid, correct_index(session), 1)
    advance = glossary.next_glossary_session(42, sid, 1)
    second = advance["current_question"]
    glossary.answer_glossary_session(42, sid, correct_index(second), 2)
    assert glossary.answer_glossary_session(42, sid, correct_index(session), 1) == first
    assert glossary.next_glossary_session(42, sid, 1) == advance
    current = glossary.get_session(sid, 42)
    assert current.score == 2 and current.current_index == 1 and current.answered_current
    assert glossary.next_glossary_session(42, sid, 2)["current_question"]["step_id"] == 3


def test_conflicting_answer_wrong_owner_and_future_step_are_rejected(session):
    sid, selected = session["session_id"], correct_index(session)
    assert glossary.answer_glossary_session(43, sid, selected, 1) is None
    assert glossary.next_glossary_session(43, sid, 1) is None
    assert glossary.answer_glossary_session(42, sid, selected, 2) is None
    assert glossary.answer_glossary_session(42, sid, True, 1) is None
    assert glossary.next_glossary_session(42, sid, True) is None
    glossary.answer_glossary_session(42, sid, selected, 1)
    assert glossary.answer_glossary_session(42, sid, (selected + 1) % 4, 1) is None
    assert glossary.get_session(sid, 42).score == 1


def test_complete_result_and_restart_retries_are_stable(session):
    sid, question = session["session_id"], session
    for step in range(1, 6):
        glossary.answer_glossary_session(42, sid, correct_index(question), step)
        state = glossary.next_glossary_session(42, sid, step)
        question = state.get("current_question")
    assert state == {"state": "completed", "result": {"score": 5, "total_questions": 5}}
    assert glossary.next_glossary_session(42, sid, 5) == state
    with ThreadPoolExecutor(max_workers=8) as pool:
        restarted = list(pool.map(lambda _: glossary.restart_glossary_session(42, sid), range(20)))
    assert all(item == restarted[0] for item in restarted)
    assert len(glossary._SESSIONS) == 2
    assert glossary.restart_glossary_session(43, sid) is None


@pytest.mark.parametrize("dedicated", [False, True])
def test_api_retries_and_missing_step_are_consistent(session, dedicated):
    token = "123:synthetic"
    client = TestClient(create_app(db_path="unused.sqlite3", bot_token=token))
    headers = {"Authorization": "tma " + _make_init_data(token, {"id": 42})}
    sid = session["session_id"]
    def request(action, extra):
        path = f"/miniapp/glossary/{action}" if dedicated else "/miniapp/answer"
        return client.post(path, headers=headers, json={"mode": "glossary", "action": action, "session_id": sid, **extra})
    for action in ("answer", "next"):
        for step in (None, True, [], 0):
            response = request(action, {"selected_option_index": correct_index(session), "step_id": step})
            assert response.status_code == 400
            assert response.json()["error"] == "glossary_step_required"
    assert glossary.get_session(sid, 42).score == 0
    payload = {"step_id": 1, "selected_option_index": correct_index(session)}
    answer = request("answer", payload)
    assert answer.status_code == 200 and answer.json()["glossary_state"]["feedback"]["is_correct"]
    assert request("answer", payload).json() == answer.json()
    advanced = request("next", {"step_id": 1})
    assert advanced.status_code == 200
    assert request("next", {"step_id": 1}).json() == advanced.json()
    assert glossary.get_session(sid, 42).score == 1
