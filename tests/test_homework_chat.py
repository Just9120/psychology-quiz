"""Homework hierarchy preserves the actor-scoped catalogue and attempt actions."""
from app import homework_chat


def test_paged_hierarchy_keeps_all_long_topics_reachable_and_returns_to_parent_page(monkeypatch):
    catalog = [{"id": str(index), "title": "Полное длинное название задания " + str(index),
        "module": f"Модуль {index // 6 + 1}",
        "discipline": f"Дисциплина {index // 7:02}", "topic": "Подробное название темы без потери значимых слов " + str(index),
        "completed": index == 8, "active_session_id": None} for index in range(42)]
    monkeypatch.setattr(homework_chat, "catalog_for_actor", lambda conn, actor: {"assignments": catalog})
    seen = set()
    expected_paths = {(item['module'], item['discipline'], item['topic']) for item in catalog}
    for path in sorted(expected_paths):
        for depth in range(3):
            parent, child = path[:depth], path[:depth + 1]
            children = sorted({value[:depth + 1] for value in expected_paths if value[:depth] == parent})
            page = children.index(child) // homework_chat.PAGE_SIZE
            text, keyboard = homework_chat._list(None, 42,
                navigation=homework_chat._path_token(parent) if parent else None, page=page)
            buttons = [button for row in keyboard.inline_keyboard for button in row]
            assert len(buttons) <= 8 and child[-1] in text
            assert 'hw:nav:' + homework_chat._path_token(child) in [button.callback_data for button in buttons]
        preview, actions = homework_chat._list(None, 42, navigation=homework_chat._path_token(path))
        callbacks = [button.callback_data for row in actions.inline_keyboard for button in row]
        siblings = sorted({value for value in expected_paths if value[:2] == path[:2]})
        assert callbacks[0] == f"hw:nav:{homework_chat._path_token(path[:2])}:{siblings.index(path) // homework_chat.PAGE_SIZE}"
        seen.update(value[9:] for value in callbacks if value.startswith('hw:start:'))
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
    assert "Модуль 1" in root and "Модуль 2" in root
    assert len(markup.inline_keyboard) == 2
    text, markup = homework_chat._list(None, 42, navigation=homework_chat._path_token(("Модуль 1", "Психология", "Память")))
    assert "Первое" in text and "Второе" not in text
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "hw:start:one" in callbacks and "hw:start:two" not in callbacks
    assert "hw:resume:12" in callbacks
    assert all(len(value.encode()) <= 64 for value in callbacks)
    text, markup = homework_chat._list(None, 42, navigation=homework_chat._path_token(("Модуль 2", "Психология", "Память")))
    assert "Второе" in text and "Первое" not in text
    assert 'hw:resume:12' not in [button.callback_data for row in markup.inline_keyboard for button in row]
    for token in ("old-token", homework_chat._path_token(("Психология", "Память"))):
        text, markup = homework_chat._list(None, 42, navigation=token)
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


def test_real_new_topics_are_reachable_in_classic_quiz_glossary_homework_and_literature(tmp_path):
    from contextlib import closing
    from app.classic_quiz_view import build_category_keyboard
    from app.db import get_active_categories, get_connection
    from app.glossary import build_glossary_topics_keyboard, callback_token_to_topic_id
    from app.literature import load_literature_items, load_topic_registry
    from tests.test_homework import _bank

    path = tmp_path / "canonical-chat-topics.sqlite3"
    actor, _ = _bank(path)
    expected = {
        "cognitive_behavioral_therapy": ("Когнитивно-поведенческая терапия", {"cbt_belief_practice", "cbt_abc_observation"}),
        "counseling_supervision": ("Супервизия психологического консультирования", {"supervision_reflective_positions"}),
    }
    glossary = {button.text: button.callback_data for row in build_glossary_topics_keyboard().inline_keyboard for button in row}
    registry = load_topic_registry()
    with closing(get_connection(str(path))) as conn:
        quiz = {button.text for row in build_category_keyboard(get_active_categories(conn)).inline_keyboard for button in row}
        catalog = homework_chat.catalog_for_actor(conn, actor)["assignments"]
        modules = homework_chat._children(catalog, ())
        for identity, (title, expected_assignments) in expected.items():
            assert registry[identity]["title"] == title and title in quiz
            assert callback_token_to_topic_id(glossary[title].split(":")[-1]) == identity
            first = next(value for value in catalog if value['id'] in expected_assignments)
            root = (first['module'],)
            discipline = (*root, title)
            root_page = modules.index(root) // homework_chat.PAGE_SIZE
            text, buttons = homework_chat._list(conn, actor, page=root_page)
            assert first['module'] in text
            disciplines = homework_chat._children(catalog, root)
            text, buttons = homework_chat._list(conn, actor, navigation=homework_chat._path_token(root),
                                               page=disciplines.index(discipline) // homework_chat.PAGE_SIZE)
            token = homework_chat._path_token(discipline)
            assert title in text and any(b.callback_data == "hw:nav:" + token for row in buttons.inline_keyboard for b in row)
            children = homework_chat._children(catalog, discipline)
            for entry in (v for v in catalog if v["id"] in expected_assignments):
                leaf = (*discipline, entry['curriculum_topic']['title'])
                text, _ = homework_chat._list(conn, actor, navigation=token,
                                              page=children.index(leaf) // homework_chat.PAGE_SIZE)
                assert entry['curriculum_topic']['title'] in text
                text, actions = homework_chat._list(conn, actor, navigation=homework_chat._path_token(leaf))
                assert entry["title"] in text
                callbacks = [b.callback_data for row in actions.inline_keyboard for b in row]
                assert "hw:start:" + entry["id"] in callbacks
                assert all(len(value.encode()) <= 64 for value in callbacks)
            assert expected_assignments <= {v["id"] for v in catalog}
            assert load_literature_items(identity)
