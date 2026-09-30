"""Private-chat navigation for the shared homework test sessions."""
from __future__ import annotations

from contextlib import closing
from html import escape
import hashlib
import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.db import create_or_load_user, get_connection
from app.homework import HomeworkError, catalog_for_actor, start_homework
from app.classic_quiz_handlers import send_current_question

from app.bot_menu import HOMEWORK_BUTTON_TEXT as BUTTON_TEXT


def _actor(conn, tg_user) -> int:
    user = create_or_load_user(conn, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
    return int(user["id"])


def _path_token(path: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(path, ensure_ascii=False).encode()).hexdigest()[:16]


def _paths(catalog):
    paths = {}
    for item in catalog:
        full = (item["module"], item["discipline"], item["topic"])
        for depth in range(1, 4):
            path = full[:depth]
            token = _path_token(path)
            if token in paths and paths[token] != path:
                raise HomeworkError("navigation_collision")
            paths[token] = path
    return paths


def _list(conn, actor: int, *, navigation: str | None = None):
    catalog = catalog_for_actor(conn, actor)["assignments"]
    path = ()
    if navigation is not None:
        path = _paths(catalog).get(navigation)
        if path is None:
            return "Раздел изменился. Обновите список через /homework.", InlineKeyboardMarkup([
                [InlineKeyboardButton("Все домашние задания", callback_data="hw:list:all")]])
    catalog = [item for item in catalog
               if (item["module"], item["discipline"], item["topic"])[:len(path)] == path]
    lines = ["<b>Домашние задания</b>", "Тест проверяет знания, а не выполнение эссе или упражнения.",
             "Зачёт — 80% в одной завершённой попытке.\n"]
    keyboard = []
    if path:
        lines.append(" → ".join(escape(value) for value in path))
        back = "hw:nav:" + _path_token(path[:-1]) if len(path) > 1 else "hw:list:all"
        keyboard.append([InlineKeyboardButton("Назад", callback_data=back)])
    if len(path) < 3:
        field = ("module", "discipline", "topic")[len(path)]
        for title in sorted({item[field] for item in catalog}):
            keyboard.append([InlineKeyboardButton(title,
                callback_data="hw:nav:" + _path_token((*path, title)))])
    if not catalog:
        lines.append("Домашних заданий пока нет.")
    for item in catalog:
        mark = "✅" if item["completed"] else "○"
        lines.append(f"{mark} <b>{escape(item['title'])}</b> — {escape(item['module'])}, "
                     f"{escape(item['discipline'])}, {escape(item['topic'])}")
        keyboard.append([InlineKeyboardButton(item["title"], callback_data="hw:start:" + item["id"])])
        if item["active_session_id"]:
            keyboard.append([InlineKeyboardButton("Продолжить: " + item["title"],
                callback_data="hw:resume:" + str(item["active_session_id"]))])
    return "\n".join(lines), InlineKeyboardMarkup(keyboard)


async def homework_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, tg_user = update.message, update.effective_user
    if message is None or tg_user is None:
        return
    if message.chat.type != "private":
        await message.reply_text("Откройте домашние задания в личном чате с ботом.")
        return
    settings = context.application.bot_data["settings"]
    with closing(get_connection(settings.db_path)) as conn, conn:
        actor = _actor(conn, tg_user)
        text, markup = _list(conn, actor)
    await message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def homework_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query, tg_user = update.callback_query, update.effective_user
    if query is None or tg_user is None or query.data is None:
        return
    await query.answer()
    if query.message is None or query.message.chat.type != "private":
        await query.edit_message_text("Домашние задания доступны в личном чате.")
        return
    settings = context.application.bot_data["settings"]
    parts = query.data.split(":")
    if len(parts) not in {3, 4} or parts[0] != "hw":
        await query.edit_message_text("Обновите список через /homework.")
        return
    action, key = parts[1], parts[2]
    if action in {"list", "nav"}:
        if len(parts) != 3 or (action == "list" and key != "all"):
            await query.edit_message_text("Обновите список через /homework.")
            return
        with closing(get_connection(settings.db_path)) as conn, conn:
            text, markup = _list(conn, _actor(conn, tg_user),
                                 navigation=key if action == "nav" else None)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        return
    with closing(get_connection(settings.db_path)) as conn, conn:
        actor = _actor(conn, tg_user)
        if action == "resume":
            if not key.isdigit() or conn.execute("""SELECT 1 FROM homework_attempts h
                    JOIN quiz_sessions s ON s.id=h.session_id
                    WHERE s.id=? AND s.user_id=? AND s.status='in_progress'""",
                    (int(key), actor)).fetchone() is None:
                result = {"error": "attempt_changed"}
            else:
                result = {"session_id": int(key)}
        elif action in {"start", "replace"}:
            if action == "replace" and (len(parts) != 4 or not parts[3].isdigit()):
                result = {"error": "invalid_homework"}
            else:
                active = conn.execute("""SELECT id FROM quiz_sessions
                    WHERE user_id=? AND status='in_progress' ORDER BY id DESC LIMIT 1""", (actor,)).fetchone()
                if action == "start" and active is not None:
                    result = {"confirm": int(active[0])}
                else:
                    try:
                        started = start_homework(conn, actor_user_id=actor, assignment_id=key,
                            payload={"replace_active": action == "replace",
                                     "expected_session_id": int(parts[3]) if action == "replace" else None})
                        result = {"session_id": int(started["runner_state"]["session"]["session_id"])}
                    except HomeworkError as exc:
                        result = {"error": str(exc)}
        else:
            result = {"error": "invalid_homework"}
    if "confirm" in result:
        await query.edit_message_text("Есть незавершённый квиз. Заменить его новой попыткой?",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Заменить и начать",
                callback_data=f"hw:replace:{key}:{result['confirm']}")],
                [InlineKeyboardButton("Отмена", callback_data="hw:list:all")]]))
        return
    if "error" in result:
        await query.edit_message_text("Состояние изменилось или задание недоступно. Обновите /homework.")
        return
    await send_current_question(query, settings, result["session_id"], context=context)
