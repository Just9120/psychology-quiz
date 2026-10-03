"""Lesson filtering cannot invent provenance or borrow another discipline."""
from copy import deepcopy

import pytest

from app import curriculum, literature_chat
from app.literature import literature_curriculum_topics
from app.content_publication import load_policy
from scripts import validate_literature
import json
from pathlib import Path


def test_literature_lesson_payload_is_source_free_and_parent_bound(monkeypatch):
    topic = {"title": "Memory", "discipline_id": "physiology",
             "source": {"source_id": "private-id", "snapshot_sha256": "private-hash"}}
    monkeypatch.setattr(curriculum, "load_catalog", lambda: {"topics": {"lesson": topic}})
    item = {"topic_id": "physiology", "curriculum_topic_ids": ["lesson"]}
    before = deepcopy(item)
    assert literature_curriculum_topics(item) == [{"id": "lesson", "title": "Memory"}]
    assert item == before
    assert literature_curriculum_topics({"topic_id": "physiology"}) == []
    for ids, discipline in ((["unknown"], "physiology"), (["lesson"], "other"),
                            (["lesson", "lesson"], "physiology"), (None, "physiology")):
        with pytest.raises(ValueError):
            literature_curriculum_topics({"topic_id": discipline, "curriculum_topic_ids": ids})


def test_bot_lesson_scope_keeps_status_pagination_and_personal_summary(monkeypatch):
    monkeypatch.setattr(literature_chat, "list_literature_topic_payloads", lambda: [{"topic_id": "physiology", "title": "Physiology"}])
    lesson = {"id": "lesson", "title": "Memory"}
    items = [{"id": f"book_{n}", "work_id": f"work_{n}", "topic_id": "physiology",
              "title": f"Book {n}", "curriculum_topics": [lesson] if n < 6 else []}
             for n in range(7)]
    states = {entry["id"]: {"reading_status": "read"} for entry in items}
    token, lesson_token = literature_chat._token("physiology"), literature_chat._token("lesson")
    text, keyboard = literature_chat._topic_view(items, states, token, 0, "d", lesson_token)
    assert "Прочитано 6 из 6" in text and "Учебная тема: Memory" in text
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    next_page = next(button for button in buttons if button.text == "→")
    assert next_page.callback_data == f"lit:t:{token}:1:d:{lesson_token}"
    assert literature_chat.CALLBACK_PATTERN.fullmatch(next_page.callback_data)
    text, keyboard = literature_chat._topic_view(items, states, token, 1, "d", lesson_token)
    assert any(button.callback_data == "lit:i:" + literature_chat._token("book_5")
               for row in keyboard.inline_keyboard for button in row)
    general = literature_chat._topic_view(items, states, token, 0, "a", literature_chat._token("general"))
    assert "Прочитано 1 из 1" in general[0]
    assert literature_chat._topic_view(items, states, token, 0, "a", "0" * 12) is None
    assert literature_chat._topic_view(items, {}, token, 0, "d", lesson_token)[0].find("Прочитано 0 из 6") >= 0


def test_signed_private_bibliography_binding_cannot_be_changed_without_review():
    entries = json.loads(Path("content/literature/psychological_consulting.json").read_text(encoding="utf-8"))
    item = next(entry for entry in entries if entry["id"] == "lit_consult_lecture_01")
    assert "source_refs" not in item and set(item["source"]) == {"citation"}
    assert load_policy().can_publish("literature", item)
    assert literature_curriculum_topics(item)[0]["id"] == "t_09efb9aedb46"
    changed = deepcopy(item)
    changed["curriculum_topic_ids"] = ["t_84bd9f531980"]
    assert not load_policy().can_publish("literature", changed)
    errors = []
    validate_literature.validate_entry(changed, "tampered", item["topic_id"], {item["topic_id"]}, {}, errors)
    assert any("source_refs" in error for error in errors)
