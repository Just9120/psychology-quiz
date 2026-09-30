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


def test_start_recommendation_requires_reviewed_metadata_and_completed_prerequisites():
    item = {"id": "next", "title": "Next", "work_id": "next", "importance": "basic",
            "importance_source": "agent", "reading_level": "foundation",
            "why_read": "Начните с вводного курса.", "prerequisites": ["previous"]}
    previous = {"id": "previous", "work_id": "previous"}
    assert reading_next_step([item], {}, [item, previous]) is None
    states = {"previous": {"reading_status": "read"}}
    result = reading_next_step([item], states, [item, previous])
    assert result["kind"] == "start" and result["basis"] == "agent"
    assert result["reason"].startswith("Рекомендация агента.")
    assert states == {"previous": {"reading_status": "read"}}
    assert reading_next_step([item], states) is None
    assert reading_next_step([{**item, "reading_level": None}], states, [item, previous]) is None
    alias = {"id": "alias", "work_id": "previous"}
    assert reading_next_step([item], states, [item, previous, alias]) is None
    assert reading_next_step([item], {**states, "next": {"reading_status": "deferred"}}, [item, previous]) is None


def test_telegram_start_recommendation_labels_origin_and_escapes_reason(monkeypatch):
    from app import literature_chat
    monkeypatch.setattr(literature_chat, "list_literature_topic_payloads", lambda: [{"topic_id": "one", "title": "Topic"}])
    item = {"id": "new", "topic_id": "one", "title": "Book", "importance": "basic",
            "importance_source": "teacher", "reading_level": "foundation",
            "why_read": "<Reason>", "prerequisites": []}
    text, keyboard = literature_chat._topic_view([item], {}, literature_chat._token("one"), 0)
    assert "Рекомендация агента." in text and "Приоритет книги — из учебного списка." in text and "&lt;Reason&gt;" in text
    assert "начать" in text and keyboard.inline_keyboard[0][0].text == "Начать чтение"


def test_agent_sequence_is_distinct_from_teacher_book_priority():
    item = {"id": "classic", "importance": "additional", "importance_source": "teacher",
            "reading_level": "deepening", "why_read": "После вводного курса.", "prerequisites": []}
    result = reading_next_step([item], {})
    assert result["basis"] == "agent"
    assert result["priority_source"] == "teacher"
    assert result["reason"] == "Рекомендация агента. После вводного курса. Приоритет книги — из учебного списка."
