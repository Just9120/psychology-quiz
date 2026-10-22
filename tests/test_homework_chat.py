"""Homework hierarchy preserves the actor-scoped catalogue and attempt actions."""
from app import homework_chat


def test_paged_hierarchy_keeps_all_long_topics_reachable_and_returns_to_parent_page(monkeypatch):
    catalog = [{"id": str(index), "title": "Полное длинное название задания " + str(index),
        "discipline": f"Дисциплина {index // 7:02}", "topic": "Подробное название темы без потери значимых слов " + str(index),
        "completed": index == 8, "active_session_id": None} for index in range(42)]
    monkeypatch.setattr(homework_chat, "catalog_for_actor", lambda conn, actor: {"assignments": catalog})
    seen = set()
    disciplines = homework_chat._children(catalog, ())
    for root_page in range(2):
        text, keyboard = homework_chat._list(None, 42, page=root_page)
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        assert len(buttons) <= 7
        for button in [b for b in buttons if b.callback_data.startswith("hw:nav:")]:
            discipline = next(path for path in disciplines if homework_chat._path_token(path) == button.callback_data.split(":")[2])
            for page in range(2):
                text, keyboard = homework_chat._list(None, 42, navigation=homework_chat._path_token(discipline), page=page)
                back = keyboard.inline_keyboard[0][0].callback_data
                assert back == f"hw:list:all:{disciplines.index(discipline) // homework_chat.PAGE_SIZE}"
                topics = homework_chat._children(catalog, discipline)
                for row in keyboard.inline_keyboard[1:]:
                    for child in row:
                        if not child.callback_data.startswith("hw:nav:") or len(child.callback_data.split(":")) != 3:
                            continue
                        path = next(path for path in topics if homework_chat._path_token(path) == child.callback_data.split(":")[2])
                        assert path[-1] in text  # Full title remains readable even when the button is shortened.
                        preview, actions = homework_chat._list(None, 42, navigation=homework_chat._path_token(path))
                        callbacks = [b.callback_data for r in actions.inline_keyboard for b in r]
                        assert callbacks[0] == f"hw:nav:{homework_chat._path_token(discipline)}:{topics.index(path) // homework_chat.PAGE_SIZE}"
                        seen.update(value[9:] for value in callbacks if value.startswith("hw:start:"))
                        assert all(len(value.encode()) <= 64 for value in callbacks)
    assert seen == {item["id"] for item in catalog}


def test_hierarchy_filters_exact_parent_and_keeps_attempt_callbacks(monkeypatch):
    catalog = [
        {"id": "one", "title": "Первое", "module": "Модуль 1", "discipline": "Психология", "topic": "Память", "completed": False, "active_session_id": 12},
        {"id": "two", "title": "Второе", "module": "Модуль 2", "discipline": "Психология", "topic": "Память", "completed": True, "active_session_id": None},
    ]
    actors = []
    def actor_catalog(conn, actor):
        actors.append(actor)
        return {"assignments": catalog}
    monkeypatch.setattr(homework_chat, "catalog_for_actor", actor_catalog)
    root, markup = homework_chat._list(None, 42)
    assert "Модуль" not in root
    assert all("Модуль" not in button.text for row in markup.inline_keyboard for button in row)
    assert len(markup.inline_keyboard) == 1  # Same topic across internal modules.
    text, markup = homework_chat._list(None, 42, navigation=homework_chat._path_token(("Психология", "Память")))
    assert "Первое" in text and "Второе" in text
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "hw:start:one" in callbacks and "hw:start:two" in callbacks
    assert "hw:resume:12" in callbacks
    assert all(len(value.encode()) <= 64 for value in callbacks)
    for token in ("old-token", homework_chat._path_token(("Модуль 1",))):
        text, markup = homework_chat._list(None, 42, navigation=token)
        assert "Раздел изменился" in text
        assert all(button.callback_data == "hw:list:all" for row in markup.inline_keyboard for button in row)
    assert actors == [42] * 4


def test_navigation_callback_does_not_start_attempt_and_refuses_group(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def close(self): pass
    opened = []
    def connection(path):
        opened.append(path)
        return Connection()
    monkeypatch.setattr(homework_chat, "get_connection", connection)
    monkeypatch.setattr(homework_chat, "_actor", lambda conn, user: 42)
    monkeypatch.setattr(homework_chat, "catalog_for_actor", lambda conn, actor: {"assignments": []})
    def forbidden(*args, **kwargs):
        raise AssertionError("Navigation must not start an attempt")
    monkeypatch.setattr(homework_chat, "start_homework", forbidden)
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"settings": SimpleNamespace(db_path="synthetic")}))
    query = SimpleNamespace(data="hw:nav:obsolete", message=SimpleNamespace(chat=SimpleNamespace(type="private")), answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=42))
    asyncio.run(homework_chat.homework_callback(update, context))
    assert "Раздел изменился" in query.edit_message_text.call_args.args[0]
    assert opened == ["synthetic"]
    query.message.chat.type = "group"
    asyncio.run(homework_chat.homework_callback(update, context))
    assert query.edit_message_text.call_args.args[0] == "Домашние задания доступны в личном чате."
    assert opened == ["synthetic"]
