"""Homework hierarchy preserves the actor-scoped catalogue and attempt actions."""
from app import homework_chat


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
    assert "Первое" in root and "Второе" in root
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "hw:resume:12" in callbacks
    for depth in (1, 2, 3):
        path = ("Модуль 1", "Психология", "Память")[:depth]
        text, markup = homework_chat._list(None, 42, navigation=homework_chat._path_token(path))
        assert "Первое" in text and "Второе" not in text
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        assert "hw:start:one" in callbacks and "hw:start:two" not in callbacks
        assert "hw:resume:12" in callbacks
        assert all(len(value.encode()) <= 64 for value in callbacks)
    text, markup = homework_chat._list(None, 42, navigation="old-token")
    assert "Раздел изменился" in text
    assert all(button.callback_data == "hw:list:all" for row in markup.inline_keyboard for button in row)
    assert actors == [42] * 5


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
