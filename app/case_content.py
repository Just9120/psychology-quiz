"""Minimum editorial contract for contextual case questions.

The case is a reviewed derivative, never a runtime-generated diagnosis or
unconditional rule. The stated situation and conditions constrain the best
answer; each alternative must receive its own rationale.
"""
from __future__ import annotations


KINDS = {"theory", "glossary", "case"}


def case_error(question: dict) -> str | None:
    kind = question.get("kind", "theory")
    if kind not in KINDS:
        return "invalid_question_kind"
    if kind != "case" or question.get("status") != "approved":
        return None
    case = question.get("case")
    if not isinstance(case, dict):
        return "case_review_required"
    for field in ("situation", "approach", "ambiguity"):
        if not isinstance(case.get(field), str) or not case[field].strip():
            return f"case_{field}_required"
    conditions = case.get("conditions")
    if not isinstance(conditions, list) or not conditions or any(
            not isinstance(value, str) or not value.strip() for value in conditions):
        return "case_conditions_required"
    options, rationales = question.get("options"), case.get("option_rationales")
    if (not isinstance(options, list) or not isinstance(rationales, list)
            or len(options) != len(rationales) or len(rationales) < 2
            or any(not isinstance(value, str) or not value.strip() for value in rationales)):
        return "case_alternative_rationales_required"
    selected = question.get("correct_option_index")
    if type(selected) is not int or not 0 <= selected < len(rationales):
        return "case_contextual_choice_required"
    if not isinstance(question.get("explanation"), str) or not question["explanation"].strip():
        return "case_explanation_required"
    return None
