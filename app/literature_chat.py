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
from app.literature import list_literature_topic_payloads, load_literature_items, literature_access_label, literature_format_label
from app import literature_service
from app.literature import list_reading_topic_payloads
from app.literature_reading import reading_order
from app.literature_navigation import reading_paths, reading_nodes, path_token, select_reading_scope, node_order

logger = logging.getLogger(__name__)
PAGE_SIZE = 5
CALLBACK_PATTERN = re.compile(r"^lit:(?:topics(?::\d{1,3})?|(?:r|cr):[0-9a-f]{12}:\d{1,3}|n:(?:root|[0-9a-f]{12}):\d{1,3}|m:[0-9a-f]{12}|(?:t|c):[0-9a-f]{12}:\d{1,3}(?::[anpdf](?::[0-9a-f]{12})?)?|i:[0-9a-f]{12}|ci:[0-9a-f]{12}:[cr]:[0-9a-f]{12}:\d{1,3}:[anpdf]|s:[0-9a-f]{12}:[npdf]|cs:[0-9a-f]{12}:[npdf]:[cr]:[0-9a-f]{12}:\d{1,3}:[anpdf])$")
STATUS_CODES = {
    "n": ("Не начато", "not_started"),
    "p": ("Читаю", "in_progress"),
    "d": ("Прочитано", "read"),
    "f": ("Отложено", "deferred"),
}
STATUS_LABELS = {value: label for label, value in STATUS_CODES.values()}
IMPORTANCE_LABELS = {"basic": "Базовая", "important": "Важная",
                     "additional": "Дополнительная", "advanced": "Углублённая"}
IMPORTANCE_SOURCES = {"teacher": "приоритет преподавателя", "agent": "рекомендация агента"}


def _token(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def _find(items: list[dict], token: str, key: str) -> dict | None:
    matches = [item for item in items if isinstance(item.get(key), str) and _token(item[key]) == token]
    return matches[0] if len(matches) == 1 else None


def _navigation_topics() -> list[dict]:
    topics = {}
    for topic in list_reading_topic_payloads() + list_literature_topic_payloads():
        topics.setdefault(topic["topic_id"], topic)
    return list(topics.values())


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


def _topics(module_token: str | None = None, page: int = 0) -> tuple[str, InlineKeyboardMarkup | None] | None:
    topics = list_reading_topic_payloads()
    if not topics:
        return ("Сейчас нет опубликованной литературы.", None) if module_token is None else None
    modules = [{"module": value} for value in dict.fromkeys(value for topic in list_literature_topic_payloads()
               for value in topic.get("modules", [topic.get("module")]))
               if isinstance(value, str) and value]
    module = _find(modules, module_token, "module") if module_token is not None else None
    if module_token is not None and module is None:
        return None
    # Old module callbacks remain readable, but navigation now uses all topics.
    if page < 0 or page * PAGE_SIZE >= len(topics):
        return None
    visible = topics[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    rows = [[InlineKeyboardButton(f"{topic['title'] if len(topic['title']) <= 48 else topic['title'][:47] + '…'} · {topic['item_count']}",
             callback_data=f"lit:t:{_token(topic['topic_id'])}:0")]
            for topic in visible]
    arrows = []
    if page:
        arrows.append(InlineKeyboardButton("← Предыдущие темы", callback_data=f"lit:topics:{page - 1}"))
    if (page + 1) * PAGE_SIZE < len(topics):
        arrows.append(InlineKeyboardButton("Следующие темы →", callback_data=f"lit:topics:{page + 1}"))
    if arrows:
        rows.append(arrows)
    labels = [f"{page * PAGE_SIZE + index + 1}. {escape(topic['title'])} · {topic['item_count']}"
              for index, topic in enumerate(visible)]
    text = ["<b>Литература по темам</b>", "Выберите тему, чтобы открыть список чтения.",
            f"Темы {page * PAGE_SIZE + 1}–{min((page + 1) * PAGE_SIZE, len(topics))} из {len(topics)}.", *labels]
    return "\n".join(text), InlineKeyboardMarkup(rows)


def _course_navigation(items=None, token='root', page=0):
    records = reading_paths(load_literature_items() if items is None else items)
    nodes = reading_nodes(records)
    node = nodes.get(token) if token != 'root' else {'path': (), 'labels': ()}
    if node is None or len(node['path']) >= 3 or page < 0:
        return None
    depth, path = len(node['path']), node['path']
    children = sorted((value for value in nodes.values() if len(value['path']) == depth + 1
                       and value['path'][:depth] == path), key=node_order)
    if page and page * PAGE_SIZE >= len(children):
        return None
    text = ['<b>Литература по программе</b>', ' → '.join(escape(value) for value in node['labels'])]
    text.append(('Выберите модуль.', 'Выберите дисциплину.', 'Выберите тему курса.')[depth])
    rows = []
    if path:
        parent = path[:-1]
        siblings = sorted((value for value in nodes.values() if len(value['path']) == depth
                           and value['path'][:-1] == parent), key=node_order)
        parent_page = next(index for index, value in enumerate(siblings) if value['path'] == path) // PAGE_SIZE
        rows.append([InlineKeyboardButton('Назад', callback_data=f"lit:n:{path_token(parent) if parent else 'root'}:{parent_page}")])
    for child in children[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        title = child['labels'][-1]
        text.append(escape(title))
        key = path_token(child['path'])
        callback = f'lit:c:{key}:0' if depth == 2 else f'lit:n:{key}:0'
        rows.append([InlineKeyboardButton(title if len(title) <= 48 else title[:47] + '…', callback_data=callback)])
    arrows = []
    if page:
        arrows.append(InlineKeyboardButton('← Предыдущие', callback_data=f'lit:n:{token}:{page - 1}'))
    if (page + 1) * PAGE_SIZE < len(children):
        arrows.append(InlineKeyboardButton('Следующие →', callback_data=f'lit:n:{token}:{page + 1}'))
    if arrows:
        rows.append(arrows)
    if not path:
        rows.append([InlineKeyboardButton('Направления чтения', callback_data='lit:topics:0')])
    if not children:
        text.append('Материалов пока нет.')
    return '\n'.join(value for value in text if value), InlineKeyboardMarkup(rows)



def _topic_view(items: list[dict], states: dict, token: str, page: int, status_filter: str = "a", lesson_token: str | None = None, *, course=False) -> tuple[str, InlineKeyboardMarkup] | None:
    if course:
        scope = select_reading_scope(items, token)
        topic, selected = ({'title': ' → '.join(scope[0]['labels'])}, scope[1]) if scope else (None, [])
    else:
        topic = _find(_navigation_topics(), token, "topic_id")
        selected = [item for item in items if topic and (any(link["id"] == topic["topic_id"] for link in item.get("reading_topics", []))
                    or item["topic_id"] == topic["topic_id"])]
    if topic is None or status_filter not in {"a", *STATUS_CODES} or page < 0 or lesson_token:
        return None  # Retired lesson buttons request a fresh topic selection.
    prefix = 'lit:c' if course else 'lit:t'
    location = ('c', token, page, status_filter) if course else None
    works = {}
    for item in selected:
        works.setdefault(item.get("work_id", item["id"]), item)
    selected = list(works.values())
    suffix = ""
    visible = [item for item in selected if status_filter == "a"
               or (states.get(item["id"]) or {}).get("reading_status", "not_started") == STATUS_CODES[status_filter][1]]
    pages = max(1, (len(visible) + PAGE_SIZE - 1) // PAGE_SIZE)
    if page >= pages:
        return None
    summary = literature_service.reading_summary(selected, states, items)
    rows = []
    for item in visible[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        state = states.get(item["id"], {})
        label = STATUS_LABELS.get(state.get("reading_status"), "Не начато")
        rows.append([InlineKeyboardButton(f"{item['title'][:45]} · {label}",
                    callback_data=_book_callback(item, location))])
    navigation = []
    if page:
        navigation.append(InlineKeyboardButton("←", callback_data=f"{prefix}:{token}:{page - 1}:{status_filter}{suffix}"))
    if page + 1 < pages:
        navigation.append(InlineKeyboardButton("→", callback_data=f"{prefix}:{token}:{page + 1}:{status_filter}{suffix}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("Все статусы", callback_data=f"{prefix}:{token}:0:a{suffix}")])
    rows.extend([[InlineKeyboardButton(label, callback_data=f"{prefix}:{token}:0:{code}{suffix}")]
                 for code, (label, _) in STATUS_CODES.items()])
    rows.append([InlineKeyboardButton("Порядок чтения", callback_data=f"lit:{'cr' if course else 'r'}:{token}:0")])
    root_topics = list_reading_topic_payloads()
    if course:
        node = scope[0]
        records = reading_paths(items)
        siblings = sorted((value for value in reading_nodes(records).values()
                           if len(value['path']) == 3 and value['path'][:2] == node['path'][:2]), key=node_order)
        parent_page = next(index for index, value in enumerate(siblings) if value['path'] == node['path']) // PAGE_SIZE
        back = f"lit:n:{path_token(node['path'][:2])}:{parent_page}"
    else:
        root_index = next((index for index, entry in enumerate(root_topics) if entry["topic_id"] == topic["topic_id"]), 0)
        back = f"lit:topics:{root_index // PAGE_SIZE}"
    rows.append([InlineKeyboardButton("К темам", callback_data=back)])
    text = f"<b>{escape(topic['title'])}</b>\nПрочитано {summary['read']} из {summary['total']}"
    if summary['conflicts']:
        text += f"\nРазличаются отметки в списках: {summary['conflicts']} работ. Они не включены в число прочитанных."
    current = summary['current']
    text += "\nСейчас читаю: " + (", ".join(escape(item["title"][:80]) for item in current[:5]) if current else "нет текущих книг")
    if len(current) > 5:
        text += f"; ещё {len(current) - 5}"
    # Keep the filtered button list separate from recommendations for the full topic.
    next_step = literature_service.reading_next_step(selected, states, items) if status_filter == "a" else None
    if next_step:
        item = next_step["item"]
        action = "продолжить" if next_step["kind"] == "continue" else "начать"
        text += f"\n\nСледующий шаг: {action} «{escape(item['title'])}».\n{escape(next_step['reason'])}"
        activity = "просмотр" if item.get("type") == "video" else ("изучение" if item.get("type") in {"article", "chapter", "other"} else "чтение")
        verb = "Продолжить" if next_step["kind"] == "continue" else "Начать"
        rows.insert(0, [InlineKeyboardButton(f"{verb} {activity}",
                     callback_data=_book_callback(item, location))])
    filter_label = "Все статусы" if status_filter == "a" else STATUS_CODES[status_filter][0]
    text += f"\nФильтр: {filter_label}."
    if not visible:
        text += "\nПо этому статусу книг пока нет."
    text += f"\nМатериалы {page + 1}/{pages}. Личный статус показан рядом с названием."
    return (text,
            InlineKeyboardMarkup(rows))


def _book_callback(item, location=None):
    if location is None:
        return 'lit:i:' + _token(item['id'])
    kind, token, page, status = location
    return f"lit:ci:{_token(item['id'])}:{kind}:{token}:{page}:{status}"


def _item_view(item: dict, state: dict | None, location=None) -> tuple[str, InlineKeyboardMarkup]:
    status = STATUS_LABELS.get((state or {}).get("reading_status"), "Не начато")
    authors = ", ".join(item.get("authors") or [])
    text = f"<b>{escape(item['title'])}</b>\n{escape(authors)}\nСтатус: {status}"
    importance = IMPORTANCE_LABELS.get(item.get("importance"))
    if importance is None:
        text += "\nЗначимость: не определена"
    else:
        origin = IMPORTANCE_SOURCES.get(item.get("importance_source"), "источник оценки не указан")
        text += f"\nЗначимость: {importance} · {origin}"
    for warning in item.get("metadata_warnings") or []:
        text += f"\n\n{escape(warning)}"
    text += "\n\nОтметьте чтение личным статусом."
    token = _token(item["id"])
    suffix = ':' + ':'.join(map(str, location)) if location else ''
    rows = [[InlineKeyboardButton(label, callback_data=f"lit:cs:{token}:{code}{suffix}" if location else f"lit:s:{token}:{code}")]
            for code, (label, _) in STATUS_CODES.items()]
    links = item.get("access_links") or []
    if links:
        text += "\nВнешние версии: доступ и издание проверьте у провайдера."
        for link in links:
            text += f"\n{literature_format_label(link)} · {escape(link['provider'])}: {literature_access_label(link)} (проверка {escape(link['checked_at'])})"
        rows.extend([[InlineKeyboardButton(
            f"{literature_format_label(link)} · {link['provider']}",
            url=link["url"])] for link in links])
    search = item.get("book_search")
    if search:
        text += f"\n\nПоисковый запрос книги:\n<code>{escape(search['query'])}</code>"
        text += "\nРезультаты поиска не подтверждают доступность скачивания."
        rows.append([InlineKeyboardButton("Поиск книги в интернете", url=search["url"])])
    back = (f"lit:c:{location[1]}:{location[2]}:{location[3]}" if location and location[0] == 'c' else
            f"lit:cr:{location[1]}:{location[2]}" if location else
            f"lit:t:{_token(item.get('reading_topics', [{'id': item['topic_id']}])[0]['id'])}:0")
    rows.insert(0, [InlineKeyboardButton("К порядку чтения" if location and location[0] == 'r' else "К теме", callback_data=back)])
    return text, InlineKeyboardMarkup(rows)


def _reading_view(items: list[dict], token: str, page: int, *, course=False) -> tuple[str, InlineKeyboardMarkup] | None:
    if course:
        scope = select_reading_scope(items, token)
        topic, selected = ({'title': ' → '.join(scope[0]['labels'])}, scope[1]) if scope else (None, [])
    else:
        topic = _find(_navigation_topics(), token, "topic_id")
        selected = [item for item in items if topic and (any(link["id"] == topic["topic_id"] for link in item.get("reading_topics", []))
                    or item["topic_id"] == topic["topic_id"])]
    if topic is None or page < 0:
        return None
    prefix = 'lit:cr' if course else 'lit:r'
    order = reading_order(selected, items)
    pages = max(1, (len(order) + PAGE_SIZE - 1) // PAGE_SIZE)
    if page >= pages:
        return None
    text = (f"<b>{escape(topic['title'])}: порядок чтения</b>\nРекомендация агента: сначала подготовка, затем книги с учётом значимости и этапа чтения. "
            "На одном этапе книги без зависимостей можно выбирать по интересу.")
    rows = []
    for number, row in enumerate(order[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], page * PAGE_SIZE + 1):
        item = row["item"]
        text += f"\n\n{number}. <b>{escape(item['title'])}</b>\n{row['stage']}. {escape(item['why_read'][:250])}"
        if item["importance_source"] == "teacher":
            text += "\nПриоритет преподавателя."
        if row["prerequisites"]:
            text += "\nПодготовка: " + ", ".join(escape(entry["title"][:100]) for entry in row["prerequisites"])
        rows.append([InlineKeyboardButton(item["title"][:60], callback_data=_book_callback(item, ('r', token, page, 'a') if course else None))])
    if not order:
        text += "\nДля этой темы последовательность пока не определена."
    nav = []
    if page:
        nav.append(InlineKeyboardButton("←", callback_data=f"{prefix}:{token}:{page - 1}"))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton("→", callback_data=f"{prefix}:{token}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("К книгам темы", callback_data=f"lit:{'c' if course else 't'}:{token}:0")])
    return text, InlineKeyboardMarkup(rows)


async def literature_command(update, context) -> None:
    message = update.effective_message
    if message is None:
        return
    if not _private(update):
        await message.reply_text("Личный список чтения доступен только в чате с ботом.")
        return
    text, keyboard = await asyncio.to_thread(_course_navigation)
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
    if data == "lit:topics" or data.startswith("lit:topics:"):
        page = int(data.split(":")[2]) if data.count(":") == 2 else 0
        view = await asyncio.to_thread(_topics, None, page)
        if view is None:
            await query.message.reply_text("Список изменился. Откройте /literature снова.")
        else:
            await query.message.reply_text(view[0], reply_markup=view[1], parse_mode="HTML")
        return
    if data.startswith("lit:m:"):
        view = await asyncio.to_thread(_topics, data.split(":")[2])
        if view is None:
            await query.message.reply_text("Раздел изменился или больше недоступен. Откройте /literature снова.")
        else:
            await query.message.reply_text(view[0], reply_markup=view[1], parse_mode="HTML")
        return
    if data.startswith('lit:n:'):
        _, _, token, page = data.split(':')
        view = await asyncio.to_thread(_course_navigation, None, token, int(page))
        if view is None:
            await query.message.reply_text('Раздел изменился. Откройте /literature снова.')
        else:
            await query.message.reply_text(view[0], reply_markup=view[1], parse_mode='HTML')
        return
    settings = context.application.bot_data["settings"]
    try:
        items, states = await asyncio.to_thread(_catalog, settings.db_path, update.effective_user)
        _, action, *parts = data.split(":")
        if action in {"r", 'cr'}:
            view = await asyncio.to_thread(_reading_view, items, parts[0], int(parts[1]), course=action == 'cr')
        elif action in {"t", 'c'}:
            view = await asyncio.to_thread(_topic_view, items, states, parts[0], int(parts[1]), parts[2] if len(parts) > 2 else "a", parts[3] if len(parts) > 3 else None, course=action == 'c')
        else:
            item = _find(items, parts[0], "id")
            location = None
            if action in {'ci', 'cs'}:
                index = 1 if action == 'ci' else 2
                location = (parts[index], parts[index + 1], int(parts[index + 2]), parts[index + 3])
                scope = select_reading_scope(items, location[1])
                if item is None or scope is None or not any(value['id'] == item['id'] for value in scope[1]):
                    item = None
            if item is None:
                view = None
            else:
                if action in {"s", 'cs'}:
                    status = STATUS_CODES[parts[1]][1]
                    states[item["id"]] = await asyncio.to_thread(
                        _save, settings.db_path, update.effective_user, item["id"], status)
                view = _item_view(item, states.get(item["id"]), location)
    except DATABASE_ERRORS as error:
        logger.warning("literature_chat_database_unavailable type=%s", type(error).__name__)
        await query.message.reply_text("Не удалось открыть список чтения. Попробуйте ещё раз позже.")
        return
    if view is None:
        await query.message.reply_text("Материал изменился или больше недоступен. Откройте /literature снова.")
        return
    text, keyboard = view
    await query.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
