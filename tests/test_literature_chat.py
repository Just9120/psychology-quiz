import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import literature_chat
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
    assert "Статус: Прочитано · 100%" in saved.args[0]

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
    assert len(items) == 130
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
