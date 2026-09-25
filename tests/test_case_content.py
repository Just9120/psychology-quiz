from app.case_content import case_error
from app.content_publication import PublicationPolicy
from app.attempt_content import get_attempt_content
from app.db import get_connection, start_quiz_session, store_session_questions, upsert_approved_questions
from contextlib import closing
from tests.test_attempt_content import bank
from scripts.seed_questions import validate_question


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


def test_existing_theory_content_remains_compatible():
    assert case_error({"status": "approved"}) is None
    assert case_error({"kind": "unsupported", "status": "approved"}) == "invalid_question_kind"


def test_case_context_is_immutable_with_each_attempt_edition(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        upsert_approved_questions(conn, [CASE])
        question_id = conn.execute("SELECT id FROM questions WHERE external_id=?", (CASE["id"],)).fetchone()[0]
        first = start_quiz_session(conn, 1, None)
        store_session_questions(conn, first, [question_id])
        original = get_attempt_content(conn, first, question_id)
        assert original["case"] == CASE["case"]
        assert original["kind"] == "case"
        revised = {**CASE, "case": {**CASE["case"], "conditions": ["Изменённое условие"]}}
        upsert_approved_questions(conn, [revised])
        second = start_quiz_session(conn, 1, None)
        store_session_questions(conn, second, [question_id])
        assert get_attempt_content(conn, first, question_id) == original
        assert get_attempt_content(conn, second, question_id)["case"] == revised["case"]
        assert get_attempt_content(conn, second, question_id)["content_sha256"] != original["content_sha256"]
