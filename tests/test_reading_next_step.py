from app.literature_service import reading_next_step


def test_continue_is_personal_recency_not_bibliography_priority():
    items = [{"id": "a", "title": "Earlier", "topic_order": 1},
             {"id": "b", "title": "Later", "topic_order": 100}]
    states = {"a": {"reading_status": "in_progress", "updated_at": "2026-09-01T12:00:00Z"},
              "b": {"reading_status": "in_progress", "updated_at": "2026-09-29T12:00:00Z"}}
    result = reading_next_step(items, states)
    assert result["item"]["id"] == "b"
    assert result["basis"] == "personal_reading_state"
    assert reading_next_step(items[:1], states)["item"]["id"] == "a"
    assert reading_next_step(items, {}) is None
    assert states["b"]["reading_status"] == "in_progress"


def test_conflicting_work_and_invalid_date_do_not_gain_priority():
    items = [{"id": "a", "work_id": "conflict"}, {"id": "b", "work_id": "conflict"},
             {"id": "c"}, {"id": "d"}]
    states = {"a": {"reading_status": "in_progress", "updated_at": "2026-09-30T12:00:00Z"},
              "b": {"reading_status": "read"},
              "c": {"reading_status": "in_progress", "updated_at": "2026-02-30T12:00:00Z"},
              "d": {"reading_status": "in_progress", "updated_at": "2026-09-01T12:00:00Z"}}
    assert reading_next_step(items, states)["item"]["id"] == "d"
    assert reading_next_step(items[:2], states) is None
    # Restricting the scope does not borrow a status from another association.
    assert reading_next_step(items[:1], states)["item"]["id"] == "a"
    states["d"]["updated_at"] = None
    assert reading_next_step(items[2:], states)["item"]["id"] == "c"


def test_telegram_continuation_opens_exact_association_and_escapes_title(monkeypatch):
    from app import literature_chat
    monkeypatch.setattr(literature_chat, "list_literature_topic_payloads",
                        lambda: [{"topic_id": "one", "title": "Topic"}])
    items = [{"id": "book", "topic_id": "one", "title": "<Book>"}]
    text, keyboard = literature_chat._topic_view(
        items, {"book": {"reading_status": "in_progress"}}, literature_chat._token("one"), 0)
    assert "&lt;Book&gt;" in text and "<Book>" not in text
    assert "Следующий шаг" in text
    assert keyboard.inline_keyboard[0][0].callback_data == "lit:i:" + literature_chat._token("book")
