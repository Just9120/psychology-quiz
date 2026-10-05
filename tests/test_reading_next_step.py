from app.literature_service import reading_next_step


def test_equal_priority_reading_follows_reviewed_stage_before_identifier():
    common = {"importance": "additional", "importance_source": "agent", "type": "book",
              "why_read": "Reviewed course reading stage", "prerequisites": []}
    advanced = {**common, "id": "a", "reading_level": "advanced"}
    foundation = {**common, "id": "z", "reading_level": "foundation"}
    assert reading_next_step([advanced, foundation], {})["item"]["id"] == "z"
    assert reading_next_step([advanced, foundation], {
        "a": {"reading_status": "in_progress"}})["item"]["id"] == "a"
    assert reading_next_step([advanced, foundation], {
        "z": {"reading_status": "read"}})["item"]["id"] == "a"
    blocked = {**foundation, "prerequisites": ["missing"]}
    assert reading_next_step([advanced, blocked], {})["item"]["id"] == "a"


def test_reviewed_priority_is_preserved_across_reading_stages():
    common = {"importance_source": "teacher", "type": "book",
              "why_read": "Explicit course priority", "prerequisites": []}
    foundation = {**common, "id": "z", "importance": "additional", "reading_level": "foundation"}
    required = {**common, "id": "a", "importance": "basic", "reading_level": "applied"}
    result = reading_next_step([foundation, required], {})
    assert result["item"]["id"] == "a" and result["priority_source"] == "teacher"


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


def test_telegram_video_continuation_preserves_association_and_viewing_language(monkeypatch):
    from app import literature_chat
    monkeypatch.setattr(literature_chat, "list_literature_topic_payloads",
                        lambda: [{"topic_id": "one", "title": "Topic"}])
    item = {"id": "film", "topic_id": "one", "type": "video", "title": "<Film>"}
    states = {"film": {"reading_status": "in_progress"}}
    text, keyboard = literature_chat._topic_view(
        [item], states, literature_chat._token("one"), 0)
    assert "Продолжите просмотр" in text and "Продолжите чтение" not in text
    assert "&lt;Film&gt;" in text and "<Film>" not in text
    assert keyboard.inline_keyboard[0][0].text == "Продолжить просмотр"
    assert keyboard.inline_keyboard[0][0].callback_data == "lit:i:" + literature_chat._token("film")
    assert states == {"film": {"reading_status": "in_progress"}}


def test_article_recommendation_keeps_teacher_priority_without_calling_it_a_book():
    item = {"id": "article", "type": "article", "importance": "additional",
            "importance_source": "teacher", "reading_level": "deepening",
            "why_read": "Сопоставьте методологические подходы.", "prerequisites": []}
    result = reading_next_step([item], {})
    assert result["priority_source"] == "teacher" and result["basis"] == "agent"
    assert result["reason"].endswith("Приоритет материала — из учебного списка.")
    states = {"article": {"reading_status": "in_progress"}}
    result = reading_next_step([item], states)
    assert "Продолжите работу с ним" in result["reason"] and "эту книгу" not in result["reason"]


def test_filtered_continuation_checks_other_associations_without_mutating_states():
    selected = {"id": "selected", "work_id": "shared"}
    alias = {"id": "other-topic", "work_id": "shared"}
    other = {"id": "other-work"}
    states = {"selected": {"reading_status": "in_progress"},
              "other-topic": {"reading_status": "read"},
              "other-work": {"reading_status": "in_progress"}}
    assert reading_next_step([selected], states, [selected, alias]) is None
    assert reading_next_step([selected, other], states, [selected, alias, other])["item"]["id"] == "other-work"
    assert states["other-topic"]["reading_status"] == "read"
    states["other-topic"]["reading_status"] = "in_progress"
    assert reading_next_step([selected], states, [selected, alias])["item"]["id"] == "selected"


def test_published_catalogue_reading_paths_cover_reviewed_works():
    """Exercise the shipped catalogue, including cross-topic work identities.

    An isolated scope assumes prerequisites outside it were completed. The
    whole-catalogue path starts empty, so cycles and unreachable dependencies
    cannot be hidden by that assumption. Unknown recommendations stay unknown.
    """
    from copy import deepcopy
    from app.literature import load_literature_items
    from app.literature_service import reading_summary

    items = load_literature_items()
    assert items, "Publication filtering must not silently empty the catalogue"
    original = deepcopy(items)
    groups = {}
    scopes = {"all": items}
    for item in items:
        work = item.get("work_id", item["id"])
        groups.setdefault(work, []).append(item)
        for key, value in (("module", item["module"]),
                           ("discipline", item["topic_id"])):
            scopes.setdefault(f"{key}:{value}", []).append(item)
        for lesson in item["curriculum_topics"]:
            scopes.setdefault("lesson:" + lesson["id"], []).append(item)

    def has_reviewed_recommendation(item):
        return (item.get("importance") in {"basic", "important", "additional", "advanced"}
                and item.get("importance_source") in {"teacher", "agent"}
                and item.get("reading_level") in
                    {"foundation", "core", "applied", "deepening", "advanced", "reference"}
                and bool(item.get("why_read", "").strip())
                and isinstance(item.get("prerequisites"), list))

    for name, selected in scopes.items():
        selected_ids = {item["id"] for item in selected}
        selected_works = {item.get("work_id", item["id"]) for item in selected}
        expected = {item.get("work_id", item["id"]) for item in selected
                    if has_reviewed_recommendation(item)}
        assert expected, f"No reviewed reading recommendations in {name}"
        states = {item["id"]: {"reading_status": "read"} for item in items
                  if item.get("work_id", item["id"]) not in selected_works}
        # Even unknown-priority works can be personally started; lack of an
        # agent recommendation must never strand an existing reading mark.
        for work in selected_works:
            personal = {alias["id"]: {"reading_status": "in_progress"}
                        for alias in groups[work]}
            before = deepcopy(personal)
            continuation = reading_next_step(selected, personal, items)
            assert continuation["kind"] == "continue"
            chosen = continuation["item"]
            assert chosen.get("work_id", chosen["id"]) == work
            assert personal == before
            if len(groups[work]) > 1:
                personal[groups[work][-1]["id"]] = {"reading_status": "read"}
                result = reading_next_step(selected, personal, items)
                assert result is None or result["item"].get(
                    "work_id", result["item"]["id"]) != work
        reached = set()
        for _ in range(len(expected) + 1):
            before = deepcopy(states)
            result = reading_next_step(selected, states, items)
            assert states == before, f"Recommendation mutated personal state in {name}"
            if result is None:
                break
            item = result["item"]
            work = item.get("work_id", item["id"])
            assert item["id"] in selected_ids and work in expected
            assert work not in reached, f"Repeated reading recommendation in {name}: {work}"
            assert result["kind"] == "start" and result["reason"].strip()
            reached.add(work)
            for alias in groups[work]:
                states[alias["id"]] = {"reading_status": "in_progress"}
            before = deepcopy(states)
            continuation = reading_next_step(selected, states, items)
            assert continuation["kind"] == "continue"
            assert continuation["item"].get("work_id", continuation["item"]["id"]) == work
            assert states == before
            for alias in groups[work]:
                states[alias["id"]] = {"reading_status": "read"}
        assert reached == expected, f"Unreachable reviewed works in {name}: {expected - reached}"
        assert reading_next_step(selected, states, items) is None
        summary = reading_summary(selected, states)
        assert summary["read"] == len(expected)
        assert summary["total"] == len(selected_works)
        assert summary["conflicts"] == 0 and summary["current"] == []
    assert items == original, "Reading paths must preserve catalogue metadata"
