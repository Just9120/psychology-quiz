from app.case_content import case_error
from app.content_publication import PublicationPolicy
from app.attempt_content import get_attempt_content
from app.db import get_connection, start_quiz_session, store_session_questions, upsert_approved_questions
from app.quiz_service import build_answer_feedback, prepare_quiz, quiz_setup_options
from app.quiz_runner import get_current_question_snapshot
from contextlib import closing
import json
from pathlib import Path
from types import SimpleNamespace
from tests.test_attempt_content import bank
from scripts.seed_questions import validate_question
from app.classic_quiz_handlers import _handle_classic_text_answer_db, build_classic_reply_feedback_text, format_case_review_html


CASE = {
    "id": "case:test", "category": "Психологическое консультирование",
    "kind": "case", "status": "approved", "question": "Какой первый шаг уместен при этих условиях?",
    "options": ["Уточнить запрос", "Сразу предложить технику", "Прервать встречу", "Дать диагноз"],
    "correct_option_index": 0, "explanation": "При описанной неопределённости сначала уточняют запрос.",
    "case": {"situation": "Вымышленный клиент описывает неопределённый запрос.",
             "approach": "Первичная консультация", "conditions": ["Нет признаков срочной опасности"],
             "ambiguity": "При иной срочности порядок действий меняется.",
             "option_rationales": ["Уточнение помогает выбрать дальнейший путь.",
                                   "Техника может понадобиться позже.",
                                   "Прерывание здесь не обосновано.",
                                   "Одного описания недостаточно."]},
}


def test_case_requires_context_and_alternative_review_before_publication():
    assert case_error(CASE) is None
    assert validate_question(CASE, 1, "case.json") == (True, None)
    assert PublicationPolicy({}, {}, {}).error("questions", CASE) == "repository_review_required"
    assert case_error({**CASE, "case": {**CASE["case"], "ambiguity": ""}}) == "case_ambiguity_required"
    assert case_error({**CASE, "case": {**CASE["case"], "option_rationales": ["only one"]}}) == "case_alternative_rationales_required"
    assert case_error({**CASE, "correct_option_index": 9}) == "case_contextual_choice_required"


def test_approved_case_has_its_own_topic_and_participates_in_mixed_quiz(bank):
    item = json.loads(Path("content/questions/module3/cases.json").read_text(encoding="utf-8"))[0]
    registry = json.loads(Path("content/topics.json").read_text(encoding="utf-8"))
    topic = next(topic for topic in registry if topic["id"] == "cases")
    assert topic["title"] == item["category"] == "Кейсы"
    assert topic["question_file"] == "content/questions/module3/cases.json"
    assert item["kind"] == "case"
    with closing(get_connection(str(bank))) as conn, conn:
        upsert_approved_questions(conn, [item])
        case_id = conn.execute("SELECT id FROM questions WHERE external_id=?", (item["id"],)).fetchone()[0]
        categories = quiz_setup_options(conn)["categories"]
        cases_category = next(category for category in categories if category["name"] == "Кейсы")
        other_category = next(category for category in categories if category["name"] == "Original category")
        setup = {"question_count": 5, "difficulty": "any", "content_kinds": ["case"]}
        single = prepare_quiz(conn, {**setup, "quiz_mode": "single",
                                     "category_ids": [cases_category["id"]]})
        assert single.question_ids == (case_id,)
        mixed = prepare_quiz(conn, {**setup, "quiz_mode": "selected_mix",
                                    "category_ids": [cases_category["id"], other_category["id"]]})
        assert mixed.question_ids == (case_id,)
        session = start_quiz_session(conn, 1, cases_category["id"])
        store_session_questions(conn, session, [case_id])
        feedback = build_answer_feedback(conn, session, case_id, 0, True)
        assert len(feedback["case_review"]["option_rationales"]) == 4
        assert "source_ref" not in feedback
        assert "drive:" not in json.dumps(feedback, ensure_ascii=False)


def test_existing_theory_content_remains_compatible():
    assert case_error({"status": "approved"}) is None
    assert case_error({"kind": "unsupported", "status": "approved"}) == "invalid_question_kind"


def test_case_context_is_immutable_with_each_attempt_edition(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        upsert_approved_questions(conn, [CASE])
        question_id = conn.execute("SELECT id FROM questions WHERE external_id=?", (CASE["id"],)).fetchone()[0]
        setup = {"quiz_mode": "all", "question_count": 5, "difficulty": "any", "category_ids": []}
        assert prepare_quiz(conn, {**setup, "content_kinds": ["case"]}).question_ids == (question_id,)
        assert question_id not in prepare_quiz(conn, {**setup, "content_kinds": ["theory"]}).question_ids
        assert question_id in prepare_quiz(conn, {**setup, "content_kinds": ["theory", "case"]}).question_ids
        first = start_quiz_session(conn, 1, None)
        store_session_questions(conn, first, [question_id])
        original = get_attempt_content(conn, first, question_id)
        assert original["case"] == CASE["case"]
        assert original["kind"] == "case"
        shown = get_current_question_snapshot(conn, actor_user_id=1, session_id=first)
        assert CASE["case"]["situation"] in shown.question_text
        assert CASE["question"] in shown.question_text
        review = build_answer_feedback(conn, first, question_id, 0, True)["case_review"]
        assert review["option_rationales"] == CASE["case"]["option_rationales"]
        revised = {**CASE, "case": {**CASE["case"], "conditions": ["Изменённое условие"]}}
        upsert_approved_questions(conn, [revised])
        second = start_quiz_session(conn, 1, None)
        store_session_questions(conn, second, [question_id])
        assert get_attempt_content(conn, first, question_id) == original
        assert get_attempt_content(conn, second, question_id)["case"] == revised["case"]
        assert get_attempt_content(conn, second, question_id)["content_sha256"] != original["content_sha256"]


def test_classic_quiz_returns_case_alternative_rationales_without_source_refs(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        upsert_approved_questions(conn, [{**CASE, "source_ref": "drive:synthetic-private-id#page-1"}])
        question_id = conn.execute("SELECT id FROM questions WHERE external_id=?", (CASE["id"],)).fetchone()[0]
        sid = start_quiz_session(conn, 1, None)
        store_session_questions(conn, sid, [question_id])
    actor = SimpleNamespace(id=42, username=None, first_name="Owner", last_name=None)
    result = _handle_classic_text_answer_db(SimpleNamespace(db_path=str(bank)), actor,
                                            session_id=sid, question_id=question_id, selected_option_index=0)
    assert result["case_review"] == CASE["case"]
    html = build_classic_reply_feedback_text(result)
    assert "Разбор кейса" in html and "Техника может понадобиться позже" in html
    assert "Неоднозначность" in html and "synthetic-private-id" not in html
    assert "&lt;script&gt;" in format_case_review_html({**CASE["case"],
        "ambiguity": "<script>"}, "normal")
