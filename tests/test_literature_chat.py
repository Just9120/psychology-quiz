import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import literature_chat


def test_additional_course_has_other_section_without_inventing_a_numbered_module(monkeypatch):
    monkeypatch.setattr(literature_chat, "list_literature_topic_payloads", lambda: [
        {"topic_id": "turning_point", "title": "Точка поворота", "module": "other", "item_count": 2},
        {"topic_id": "regular", "title": "Психология", "module": "module1", "item_count": 1}])
    _, keyboard = literature_chat._topics()
    assert any(button.text == "Другое" for row in keyboard.inline_keyboard for button in row)
    text, keyboard = literature_chat._topics(literature_chat._token("other"))
    assert "Другое" in text and "other" not in text
    assert keyboard.inline_keyboard[0][0].callback_data == "lit:t:" + literature_chat._token("turning_point") + ":0"


def test_cross_module_discipline_is_available_from_both_module_buttons(monkeypatch):
    monkeypatch.setattr(literature_chat, "list_literature_topic_payloads", lambda: [
        {"topic_id": "shared", "title": "Shared discipline", "module": "module2",
         "modules": ["module2", "module3"], "item_count": 2}])
    for module in ("module2", "module3"):
        text, keyboard = literature_chat._topics(literature_chat._token(module))
        assert module.replace("module", "Модуль ") in text
        assert keyboard.inline_keyboard[0][0].callback_data == "lit:t:" + literature_chat._token("shared") + ":0"
from app.literature import load_literature_items
from tests.test_attempt_content import TOKEN, bank
from tests.test_miniapp_api import _make_init_data
from tests.test_web_auth import web
from tests.test_web_literature import linked


def _context(web):
    return SimpleNamespace(application=SimpleNamespace(bot_data={
        "settings": SimpleNamespace(db_path=str(web.db)),
    }))


def _update(user_id=42, *, data=None, chat_type="private"):
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(message=message, data=data, answer=AsyncMock()) if data else None
    return SimpleNamespace(effective_message=message, callback_query=query,
                           effective_chat=SimpleNamespace(type=chat_type),
                           effective_user=SimpleNamespace(id=user_id, username=None,
                                                          first_name="Synthetic", last_name=None))


def _click(web, user_id, data, *, chat_type="private"):
    update = _update(user_id, data=data, chat_type=chat_type)
    asyncio.run(literature_chat.literature_callback(update, _context(web)))
    return update.effective_message.reply_text.call_args


def test_chat_literature_write_is_shared_with_linked_pwa_and_miniapp_but_not_other_actor(web):
    csrf = linked(web)
    command = _update()
    asyncio.run(literature_chat.literature_command(command, _context(web)))
    topic_button = command.effective_message.reply_text.call_args.kwargs["reply_markup"].inline_keyboard[0][0]
    assert topic_button.callback_data.startswith("lit:t:")
    topic = _click(web, 42, topic_button.callback_data)
    item_button = topic.kwargs["reply_markup"].inline_keyboard[0][0]
    item = _click(web, 42, item_button.callback_data)
    read_button = next(row[0] for row in item.kwargs["reply_markup"].inline_keyboard
                       if row[0].text == "Прочитано")
    saved = _click(web, 42, read_button.callback_data)
    assert "Статус: Прочитано" in saved.args[0]
    assert "%" not in saved.args[0]

    selected_id = next(item["id"] for item in load_literature_items()
                       if literature_chat._token(item["id"]) == item_button.callback_data.split(":")[2])
    catalog = web.client.get("/web/literature/catalog").json()
    entries = [entry for work in catalog["works"] for entry in work["entries"]]
    assert next(entry for entry in entries if entry["id"] == selected_id)["user_state"]["reading_status"] == "read"
    headers = {"Authorization": "tma " + _make_init_data(TOKEN, {"id": 42})}
    state = web.client.get("/miniapp/literature/state", headers=headers).json()["literature_state"]
    assert next(row for row in state if row["literature_id"] == selected_id)["reading_status"] == "read"

    other = _click(web, 99, item_button.callback_data)
    assert "Статус: Не начато" in other.args[0]
    assert web.client.get("/miniapp/literature/state", headers={
        "Authorization": "tma " + _make_init_data(TOKEN, {"id": 99})
    }).json()["literature_state"] == []
    topic_id = next(item["topic_id"] for item in load_literature_items() if item["id"] == selected_id)
    filtered = f"lit:t:{literature_chat._token(topic_id)}:0:d"
    own_filter = _click(web, 42, filtered)
    other_filter = _click(web, 99, filtered)
    assert "Фильтр: Прочитано" in own_filter.args[0]
    assert "По этому статусу книг пока нет" in other_filter.args[0]
    assert not any(b.callback_data == item_button.callback_data
                   for row in other_filter.kwargs["reply_markup"].inline_keyboard for b in row)
    assert csrf


def test_chat_literature_rejects_group_stale_item_and_unknown_callback(web, monkeypatch):
    group = _update(chat_type="group")
    asyncio.run(literature_chat.literature_command(group, _context(web)))
    assert "только в чате" in group.effective_message.reply_text.call_args.args[0]
    group_click = _click(web, 42, "lit:topics", chat_type="group")
    assert "только в чате" in group_click.args[0]

    invalid = _click(web, 42, "lit:s:ffffffffffff:d")
    assert "больше недоступен" in invalid.args[0]
    malformed = _click(web, 42, "lit:s:invalid:d")
    assert "устарела" in malformed.args[0]
    item = load_literature_items()[0]
    monkeypatch.setattr(literature_chat, "load_literature_items", lambda: [])
    stale = _click(web, 42, f"lit:s:{literature_chat._token(item['id'])}:d")
    assert "больше недоступен" in stale.args[0]


def test_all_published_literature_entries_have_stable_short_callbacks():
    items = load_literature_items()
    topics = literature_chat.list_literature_topic_payloads()
    assert len(items) == 241
    assert len({literature_chat._token(item["id"]) for item in items}) == len(items)
    seen = set()
    for topic in topics:
        token = literature_chat._token(topic["topic_id"])
        for page in range((topic["item_count"] + literature_chat.PAGE_SIZE - 1) // literature_chat.PAGE_SIZE):
            view = literature_chat._topic_view(items, {}, token, page)
            assert view is not None
            for row in view[1].inline_keyboard:
                for button in row:
                    assert len(button.callback_data.encode("utf-8")) <= 64
                    if button.callback_data.startswith("lit:i:"):
                        seen.add(button.callback_data)
    assert len(seen) == len(items)


def test_book_card_preserves_and_escapes_metadata_uncertainty():
    item = {"id": "synthetic-book", "topic_id": "synthetic-topic", "title": "Учебная книга",
            "authors": ["Указанный автор"], "metadata_warnings": ["Авторство <b>не уточнено</b>"],
            "source": {"id": "private-source-id", "locator": "private-page"}}
    text, keyboard = literature_chat._item_view(item, None)
    assert "Авторство &lt;b&gt;не уточнено&lt;/b&gt;" in text
    assert "<b>не уточнено</b>" not in text
    assert "private-source-id" not in text and "private-page" not in text
    assert "Статус: Не начато" in text
    assert keyboard.inline_keyboard[0][0].text == "Не начато"


@pytest.mark.parametrize("value,label,origin,origin_label", [
    ("basic", "Базовая", "teacher", "приоритет преподавателя"),
    ("important", "Важная", "agent", "рекомендация агента"),
    ("additional", "Дополнительная", "teacher", "приоритет преподавателя"),
    ("advanced", "Углублённая", "agent", "рекомендация агента"),
])
def test_chat_book_card_distinguishes_importance_and_provenance(value, label, origin, origin_label):
    item = {"id": "book", "topic_id": "topic", "title": "Учебная книга",
            "importance": value, "importance_source": origin}
    text, _ = literature_chat._item_view(item, None)
    assert f"Значимость: {label} · {origin_label}" in text
    unknown, _ = literature_chat._item_view({k: v for k, v in item.items() if not k.startswith("importance")}, None)
    assert "Значимость: не определена" in unknown
    assert "приоритет преподавателя" not in unknown and "рекомендация агента" not in unknown


def test_chat_reading_module_navigation_and_filter_keep_tally_and_pagination(monkeypatch):
    topics = [{"topic_id": "one", "title": "Первый список", "item_count": 12, "module": "module1"},
              {"topic_id": "two", "title": "Другой список", "item_count": 1, "module": "module2"}]
    monkeypatch.setattr(literature_chat, "list_literature_topic_payloads", lambda: topics)
    items = [{"id": f"book-{i}", "work_id": f"work-{i}", "title": f"Книга {i}", "topic_id": "one"}
             for i in range(12)]
    states = {item["id"]: {"reading_status": "read"} for item in items[:8]}
    token = literature_chat._token("one")
    root = literature_chat._topics()
    modules = [b for row in root[1].inline_keyboard for b in row if b.callback_data.startswith("lit:m:")]
    assert [b.text for b in modules] == ["Модуль 1", "Модуль 2"]
    module = literature_chat._topics(literature_chat._token("module1"))
    assert "Модуль 1" in module[0]
    assert [b.text for row in module[1].inline_keyboard for b in row if b.callback_data.startswith("lit:t:")] == ["Первый список · 12"]
    assert literature_chat._topics("f" * 12) is None
    for code, expected in (("a", 5), ("d", 5), ("n", 4), ("p", 0), ("f", 0)):
        text, keyboard = literature_chat._topic_view(items, states, token, 0, code)
        assert "Прочитано 8 из 12" in text
        buttons = [b for row in keyboard.inline_keyboard for b in row]
        assert len([b for b in buttons if b.callback_data.startswith("lit:i:")]) == expected
        assert all(literature_chat.CALLBACK_PATTERN.fullmatch(b.callback_data) for b in buttons)
        assert all(len(b.callback_data.encode()) <= 64 for b in buttons)
        if not expected:
            assert "По этому статусу книг пока нет" in text
    page = literature_chat._topic_view(items, states, token, 1, "d")
    buttons = [b for row in page[1].inline_keyboard for b in row]
    assert len([b for b in buttons if b.callback_data.startswith("lit:i:")]) == 3
    assert next(b for b in buttons if b.text == "←").callback_data == f"lit:t:{token}:0:d"
    assert literature_chat._topic_view(items, states, token, 2, "d") is None
    assert literature_chat._topic_view(items, states, token, 0, "invalid") is None
    assert literature_chat._topic_view(items, states, token, -1) is None
    assert literature_chat.CALLBACK_PATTERN.fullmatch(f"lit:t:{token}:0")  # Existing buttons still work.
    assert states == {item["id"]: {"reading_status": "read"} for item in items[:8]}
