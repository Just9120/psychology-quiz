"""A fixed, stateless public sample of reviewed derivatives only."""
from __future__ import annotations

import json
from pathlib import Path

from app.content_publication import load_policy

ROOT = Path(__file__).resolve().parent.parent / "content"
QUESTIONS = (
    ("theory", "questions/module1/vvedenie_v_professiyu.json", "m1_intro_001"),
    ("case", "questions/module3/cases.json", "case_first_consultation_001"),
)
GLOSSARY = "glossary/vvedenie_v_professiyu.json"
TERM_ID = "psychologist_consultant_role"


class DemoUnavailable(ValueError):
    pass


def _approved(path: str, kind: str, item_id: str):
    items = json.loads((ROOT / path).read_text(encoding="utf-8"))
    selected = next((item for item in items if item.get("id") == item_id), None)
    if selected is None or not load_policy().can_publish(kind, selected):
        raise DemoUnavailable("demo_unavailable")
    return selected


def _items():
    theory = _approved(QUESTIONS[0][1], "questions", QUESTIONS[0][2])
    case = _approved(QUESTIONS[1][1], "questions", QUESTIONS[1][2])
    terms = json.loads((ROOT / GLOSSARY).read_text(encoding="utf-8"))
    glossary = [item for item in terms if load_policy().can_publish("glossary", item)]
    selected = next((item for item in glossary if item["id"] == TERM_ID), None)
    distractors = [item for item in glossary if item["id"] != TERM_ID][:3]
    if selected is None or len(distractors) != 3:
        raise DemoUnavailable("demo_unavailable")
    return theory, selected, distractors, case


def list_items():
    theory, term, distractors, case = _items()
    return {"ok": True, "items": [
        {"id": "theory", "kind": "theory", "prompt": theory["question"], "options": theory["options"]},
        {"id": "term", "kind": "glossary", "prompt": f"Что означает «{term['term']}»?",
         "options": [term["short_definition"], *[item["short_definition"] for item in distractors]]},
        {"id": "case", "kind": "case", "prompt": f"{case['case']['situation']}\n\n{case['question']}", "options": case["options"]},
    ]}


def answer(item_id: object, option_index: object):
    if type(item_id) is not str or item_id not in {"theory", "term", "case"} or type(option_index) is not int or not 0 <= option_index < 4:
        raise ValueError("invalid_payload")
    theory, term, _, case = _items()
    if item_id == "term":
        correct, explanation, review = 0, term["definition"], None
    else:
        item = theory if item_id == "theory" else case
        correct, explanation = item["correct_option_index"], item["explanation"]
        review = {key: case["case"][key] for key in ("approach", "conditions", "ambiguity", "option_rationales")} if item_id == "case" else None
    result = {"ok": True, "is_correct": option_index == correct, "correct_option_index": correct,
              "explanation": explanation}
    if review is not None:
        result["case_review"] = review
    return result
