"""Private Telegram chat adapter for the shared reading catalog and state."""
from __future__ import annotations

import asyncio
from contextlib import closing
from hashlib import sha256
from html import escape
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.database import DATABASE_ERRORS
from app.db import create_or_load_user, get_connection
from app.literature import list_literature_topic_payloads, load_literature_items
from app import literature_service

logger = logging.getLogger(__name__)
PAGE_SIZE = 5
CALLBACK_PATTERN = re.compile(r"^lit:(?:topics|t:[0-9a-f]{12}:\d{1,3}|i:[0-9a-f]{12}|s:[0-9a-f]{12}:[npdrs])$")
STATUS_CODES = {
    "n": ("Не начато", "not_started"),
    "p": ("Читаю", "in_progress"),
    "d": ("Прочитано", "read"),
    "r": ("Вернуться позже", "revisit"),
    "s": ("Пропущено", "skipped"),
}
STATUS_LABELS = {value: label for label, value in STATUS_CODES.values()}


def _token(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def _find(items: list[dict], token: str, key: str) -> dict | None:
    matches = [item for item in items if isinstance(item.get(key), str) and _token(item[key]) == token]
    return matches[0] if len(matches) == 1 else None


def _private(update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type == "private")


def _catalog(db_path: str, telegram_user) -> tuple[list[dict], dict]:
    with closing(get_connection(db_path)) as conn, conn:
        actor = create_or_load_user(conn, telegram_user.id, telegram_user.username,
                                    telegram_user.first_name, telegram_user.last_name)
        return load_literature_items(), literature_service.load_progress(conn, int(actor["id"]))


def _save(db_path: str, telegram_user, literature_id: str, status: str) -> dict:
    with closing(get_connection(db_path)) as conn, conn:
        actor = create_or_load_user(conn, telegram_user.id, telegram_user.username,
                                    telegram_user.first_name, telegram_user.last_name)
        return literature_service.save_progress(conn, int(actor["id"]), literature_id, status, None)


def _topics() -> tuple[str, InlineKeyboardMarkup | None]:
    topics = list_literature_topic_payloads()
    if not topics:
        return "Сейчас нет опубликованной литературы.", None
    rows = [[InlineKeyboardButton(f"{topic['title']} · {topic['item_count']}",
             callback_data=f"lit:t:{_token(topic['topic_id'])}:0")]
            for topic in topics]
    return "<b>Литература по темам</b>\nВыберите тему, чтобы открыть список чтения.", InlineKeyboardMarkup(rows)


def _topic_view(items: list[dict], states: dict, token: str, page: int) -> tuple[str, InlineKeyboardMarkup] | None:
    topics = list_literature_topic_payloads()
    topic = _find(topics, token, "topic_id")
    if topic is None:
        return None
    selected = [item for item in items if item["topic_id"] == topic["topic_id"]]
    pages = max(1, (len(selected) + PAGE_SIZE - 1) // PAGE_SIZE)
    if page >= pages:
        return None
    rows = []
    for item in selected[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        state = states.get(item["id"], {})
        label = STATUS_LABELS.get(state.get("reading_status"), "Не начато")
        rows.append([InlineKeyboardButton(f"{item['title'][:45]} · {label}",
                    callback_data=f"lit:i:{_token(item['id'])}")])
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton("←", callback_data=f"lit:t:{token}:{page - 1}"))
    if page + 1 < pages:
        navigation.append(InlineKeyboardButton("→", callback_data=f"lit:t:{token}:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("К темам", callback_data="lit:topics")])
    return (f"<b>{escape(topic['title'])}</b>\nМатериалы {page + 1}/{pages}. Личный статус показан рядом с названием.",
            InlineKeyboardMarkup(rows))


def _item_view(item: dict, state: dict | None) -> tuple[str, InlineKeyboardMarkup]:
    status = STATUS_LABELS.get((state or {}).get("reading_status"), "Не начато")
    authors = ", ".join(item.get("authors") or [])
    text = f"<b>{escape(item['title'])}</b>\n{escape(authors)}\nСтатус: {status}"
    if state and state.get("progress_percent") is not None:
        text += f" · {state['progress_percent']}%"
    text += "\n\nОтметьте чтение. Процент можно уточнить в Mini App или PWA."
    token = _token(item["id"])
    rows = [[InlineKeyboardButton(label, callback_data=f"lit:s:{token}:{code}")]
            for code, (label, _) in STATUS_CODES.items()]
    rows.append([InlineKeyboardButton("К теме", callback_data=f"lit:t:{_token(item['topic_id'])}:0")])
    return text, InlineKeyboardMarkup(rows)


async def literature_command(update, context) -> None:
    message = update.effective_message
    if message is None:
        return
    if not _private(update):
        await message.reply_text("Личный список чтения доступен только в чате с ботом.")
        return
    text, keyboard = await asyncio.to_thread(_topics)
    await message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


async def literature_callback(update, context) -> None:
    query = update.callback_query
    if query is None or query.message is None:
        return
    await query.answer(cache_time=0)
    if not _private(update) or update.effective_user is None:
        await query.message.reply_text("Личный список чтения доступен только в чате с ботом.")
        return
    data = query.data or ""
    if CALLBACK_PATTERN.fullmatch(data) is None:
        await query.message.reply_text("Кнопка устарела. Откройте /literature снова.")
        return
    if data == "lit:topics":
        await literature_command(update, context)
        return
    settings = context.application.bot_data["settings"]
    try:
        items, states = await asyncio.to_thread(_catalog, settings.db_path, update.effective_user)
        _, action, *parts = data.split(":")
        if action == "t":
            view = await asyncio.to_thread(_topic_view, items, states, parts[0], int(parts[1]))
        else:
            item = _find(items, parts[0], "id")
            if item is None:
                view = None
            else:
                if action == "s":
                    status = STATUS_CODES[parts[1]][1]
                    states[item["id"]] = await asyncio.to_thread(
                        _save, settings.db_path, update.effective_user, item["id"], status)
                view = _item_view(item, states.get(item["id"]))
    except DATABASE_ERRORS as error:
        logger.warning("literature_chat_database_unavailable type=%s", type(error).__name__)
        await query.message.reply_text("Не удалось открыть список чтения. Попробуйте ещё раз позже.")
        return
    if view is None:
        await query.message.reply_text("Материал изменился или больше недоступен. Откройте /literature снова.")
        return
    text, keyboard = view
    await query.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
