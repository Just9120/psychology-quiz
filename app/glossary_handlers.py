from __future__ import annotations

import logging
import random
import time

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.handler_latency import HandlerLatency as _HandlerLatency
from app.miniapp_entrypoint_handlers import MINI_APP_BUTTON_TEXT
from app.glossary import (
    GLOSSARY_QUIZ_SESSION_KEY,
    GLOSSARY_UNAVAILABLE_TEXT,
    build_glossary_answer_keyboard,
    build_glossary_count_keyboard,
    build_glossary_feedback_keyboard,
    build_glossary_quiz_question,
    build_glossary_topics_keyboard,
    callback_token_to_topic_id,
    format_glossary_count_text,
    format_glossary_feedback_text,
    format_glossary_question_text,
    format_glossary_result_text,
    format_glossary_topics_text,
    load_glossary_entries,
    topic_title,
)

logger = logging.getLogger(__name__)

START_QUIZ_BUTTON_TEXT = "🎯 Начать"
READING_MODE_BUTTON_TEXT = "👁 Чтение"
GLOSSARY_BUTTON_TEXT = "📚 Глоссарий"
HIDE_MENU_BUTTON_TEXT = "🙈 Скрыть меню"
CLASSIC_REPLY_NEXT_TEXT = "Далее"
CLASSIC_REPLY_STATE_KEY = "classic_reply_keyboard_state"


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(START_QUIZ_BUTTON_TEXT), KeyboardButton(MINI_APP_BUTTON_TEXT)],
            [KeyboardButton(READING_MODE_BUTTON_TEXT), KeyboardButton(GLOSSARY_BUTTON_TEXT)],
            [KeyboardButton("ℹ️ Помощь")],
            [KeyboardButton(HIDE_MENU_BUTTON_TEXT)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _get_classic_reply_state(context: ContextTypes.DEFAULT_TYPE) -> dict:
    state = context.user_data.get(CLASSIC_REPLY_STATE_KEY)
    return state if isinstance(state, dict) else {}


async def _timed_telegram_api_call(latency: _HandlerLatency | None, call, api_kind: str | None = None):
    started_at = time.perf_counter()
    result = await call
    if latency is not None:
        latency.add_telegram_api(started_at, api_kind=api_kind)
    return result


def _mark_repeated_tap(latency: _HandlerLatency) -> None:
    latency.set_status("ignored_repeated_tap")
    latency.add_field("repeated_tap", True)


def _mark_stale_callback(latency: _HandlerLatency) -> None:
    latency.set_status("ignored_stale_callback")
    latency.add_field("stale_callback", True)


async def glossary_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await glossary_command(update, context)


async def glossary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
    if update.message is None:
        return
    await update.message.reply_text(
        format_glossary_topics_text(),
        reply_markup=build_glossary_topics_keyboard(),
        parse_mode="HTML",
    )


def _build_glossary_session(topic_id: str, entries, count_raw: str) -> dict | None:
    if entries is None or len(entries) < 4:
        return None
    requested_count = len(entries) if count_raw == "all" else int(count_raw)
    question_count = min(requested_count, len(entries))
    selected_entries = random.sample(entries, question_count)
    return {
        "topic_id": topic_id,
        "count_raw": count_raw,
        "entry_ids": [entry.id for entry in selected_entries],
        "current_index": 0,
        "score": 0,
        "answered": False,
        "status": "awaiting_answer",
        "last_question": None,
    }


def _current_glossary_question(session: dict, entries) -> object | None:
    current_index = int(session.get("current_index", 0))
    entry_ids = session.get("entry_ids")
    if not isinstance(entry_ids, list) or current_index < 0 or current_index >= len(entry_ids):
        return None
    current_entry_id = entry_ids[current_index]
    current_entry = next((entry for entry in entries if entry.id == current_entry_id), None)
    if current_entry is None:
        return None
    return build_glossary_quiz_question(entries, current_entry)


async def _send_current_glossary_question_to_chat(chat, latency: _HandlerLatency | None, context: ContextTypes.DEFAULT_TYPE, session: dict, entries) -> None:
    question = _current_glossary_question(session, entries)
    if question is None:
        context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
        await _timed_telegram_api_call(latency, chat.send_message(GLOSSARY_UNAVAILABLE_TEXT), api_kind="message_send")
        return
    session["answered"] = False
    session["status"] = "awaiting_answer"
    session["last_question"] = question
    total = len(session["entry_ids"])
    current_index = int(session["current_index"])
    await _timed_telegram_api_call(
        latency,
        chat.send_message(
            format_glossary_question_text(question, current_index + 1, total),
            reply_markup=build_glossary_answer_keyboard(question),
            parse_mode="HTML",
        ),
        api_kind="message_send",
    )


async def glossary_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(
        handler="glossary_callback",
        callback_prefix="gls",
        telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None),
    )
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    if not (data.startswith("gls:") or data.startswith("glsq:")):
        return
    latency.start()
    await _timed_telegram_api_call(latency, query.answer(cache_time=1), api_kind="callback_ack")

    if data == "gls:topics":
        context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
        await _timed_telegram_api_call(
            latency,
            query.edit_message_text(
                format_glossary_topics_text(),
                reply_markup=build_glossary_topics_keyboard(),
                parse_mode="HTML",
            ),
            api_kind="message_edit",
        )
        latency.summary()
        return

    if data == "gls:main":
        context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
        if query.message is not None:
            try:
                await _timed_telegram_api_call(latency, query.edit_message_reply_markup(reply_markup=None), api_kind="message_edit")
            except Exception:
                logger.debug("Не удалось отключить inline-кнопки глоссария перед возвратом в главное меню.")
            await _timed_telegram_api_call(
                latency,
                query.message.chat.send_message("Главное меню:", reply_markup=get_main_menu_keyboard()),
                api_kind="message_send",
            )
        latency.summary()
        return

    parts = data.split(":")
    if len(parts) == 3 and parts[0] == "gls" and parts[1] == "topic":
        topic_token = parts[2]
        selected_topic_id = callback_token_to_topic_id(topic_token)
        title = topic_title(selected_topic_id)
        entries = load_glossary_entries(selected_topic_id) if selected_topic_id is not None else None
        if selected_topic_id is None or title is None or entries is None:
            await _timed_telegram_api_call(latency, query.edit_message_text(GLOSSARY_UNAVAILABLE_TEXT), api_kind="message_edit")
            latency.summary()
            return
        await _timed_telegram_api_call(
            latency,
            query.edit_message_text(
                format_glossary_count_text(title, len(entries)),
                reply_markup=build_glossary_count_keyboard(selected_topic_id, len(entries)),
                parse_mode="HTML",
            ),
            api_kind="message_edit",
        )
        latency.summary()
        return

    if len(parts) == 4 and parts[0] == "glsq" and parts[1] == "count" and parts[3] in {"5", "10", "all"}:
        selected_topic_id = callback_token_to_topic_id(parts[2])
        entries = load_glossary_entries(selected_topic_id) if selected_topic_id is not None else None
        session = _build_glossary_session(selected_topic_id, entries, parts[3]) if selected_topic_id is not None else None
        if session is None:
            await _timed_telegram_api_call(latency, query.edit_message_text(GLOSSARY_UNAVAILABLE_TEXT), api_kind="message_edit")
            latency.summary()
            return
        context.user_data[GLOSSARY_QUIZ_SESSION_KEY] = session
        if query.message is not None:
            await _timed_telegram_api_call(latency, query.edit_message_reply_markup(reply_markup=None), api_kind="message_edit")
            await _send_current_glossary_question_to_chat(query.message.chat, latency, context, session, entries)
        latency.summary()
        return

    if len(parts) == 3 and parts[0] == "glsq" and parts[1] == "ans" and parts[2].isdigit():
        session = context.user_data.get(GLOSSARY_QUIZ_SESSION_KEY)
        if not isinstance(session, dict) or session.get("answered"):
            _mark_repeated_tap(latency)
            latency.summary()
            return
        selected_index = int(parts[2])
        question = session.get("last_question")
        if question is None or not 0 <= selected_index < len(question.options):
            await _timed_telegram_api_call(latency, query.edit_message_text(GLOSSARY_UNAVAILABLE_TEXT), api_kind="message_edit")
            latency.summary()
            return
        is_correct = selected_index == question.correct_option_index
        if is_correct:
            session["score"] = int(session.get("score", 0)) + 1
        session["answered"] = True
        total = len(session["entry_ids"])
        answered_count = int(session["current_index"]) + 1
        if answered_count >= total:
            feedback = format_glossary_feedback_text(question, selected_index, answered_count, total)
            result = format_glossary_result_text(int(session.get("score", 0)), total)
            context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
            await _timed_telegram_api_call(
                latency,
                query.message.chat.send_message(
                    f"{feedback}\n\n{result}",
                    reply_markup=get_main_menu_keyboard() if query.message.chat.type == "private" else None,
                    parse_mode="HTML",
                ),
                api_kind="message_send",
            )
        else:
            await _timed_telegram_api_call(
                latency,
                query.edit_message_text(
                    format_glossary_feedback_text(question, selected_index, answered_count, total),
                    reply_markup=build_glossary_feedback_keyboard(has_next=True),
                    parse_mode="HTML",
                ),
                api_kind="message_edit",
            )
        latency.summary()
        return

    if data == "glsq:next":
        session = context.user_data.get(GLOSSARY_QUIZ_SESSION_KEY)
        if not isinstance(session, dict) or not session.get("answered"):
            _mark_stale_callback(latency)
            latency.summary()
            return
        selected_topic_id = session.get("topic_id")
        entries = load_glossary_entries(selected_topic_id) if isinstance(selected_topic_id, str) else None
        if entries is None:
            await _timed_telegram_api_call(latency, query.edit_message_text(GLOSSARY_UNAVAILABLE_TEXT), api_kind="message_edit")
            latency.summary()
            return
        session["current_index"] = int(session.get("current_index", 0)) + 1
        if query.message is not None:
            await _send_current_glossary_question_to_chat(query.message.chat, latency, context, session, entries)
        latency.summary()
        return

    if data == "glsq:retry":
        session = context.user_data.get(GLOSSARY_QUIZ_SESSION_KEY)
        topic_id = session.get("topic_id") if isinstance(session, dict) else "kachestvennye_metody_issledovaniya"
        count_raw = session.get("count_raw") if isinstance(session, dict) else "5"
        entries = load_glossary_entries(topic_id) if isinstance(topic_id, str) else None
        new_session = _build_glossary_session(topic_id, entries, str(count_raw)) if isinstance(topic_id, str) else None
        if new_session is None:
            await _timed_telegram_api_call(latency, query.edit_message_text(GLOSSARY_UNAVAILABLE_TEXT), api_kind="message_edit")
            latency.summary()
            return
        context.user_data[GLOSSARY_QUIZ_SESSION_KEY] = new_session
        if query.message is not None:
            await _send_current_glossary_question_to_chat(query.message.chat, latency, context, new_session, entries)
        latency.summary()
        return

    await _timed_telegram_api_call(latency, query.edit_message_text(GLOSSARY_UNAVAILABLE_TEXT), api_kind="message_edit")
    latency.summary()



def _active_glossary_session(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    session = context.user_data.get(GLOSSARY_QUIZ_SESSION_KEY)
    return session if isinstance(session, dict) else None


def parse_glossary_reply_answer_number(text: str, option_count: int = 4) -> int | None:
    cleaned = text.strip()
    if not cleaned.isdigit():
        return None
    answer_number = int(cleaned)
    if not 1 <= answer_number <= option_count:
        return None
    return answer_number - 1


async def glossary_reply_text_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or message.text is None:
        return
    classic_state = _get_classic_reply_state(context)
    if classic_state.get("status") == "awaiting_answer":
        return
    session = _active_glossary_session(context)
    if session is None or session.get("status") != "awaiting_answer" or session.get("answered"):
        return
    question = session.get("last_question")
    if question is None:
        context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
        await message.reply_text(GLOSSARY_UNAVAILABLE_TEXT, reply_markup=get_main_menu_keyboard() if message.chat.type == "private" else None)
        return
    selected_index = parse_glossary_reply_answer_number(message.text, len(question.options))
    if selected_index is None:
        await message.reply_text(f"Выберите вариант числом от 1 до {len(question.options)}.", reply_markup=build_glossary_answer_keyboard(question))
        return

    is_correct = selected_index == question.correct_option_index
    if is_correct:
        session["score"] = int(session.get("score", 0)) + 1
    session["answered"] = True
    session["status"] = "awaiting_next"
    total = len(session["entry_ids"])
    answered_count = int(session["current_index"]) + 1
    feedback = format_glossary_feedback_text(question, selected_index, answered_count, total)
    if answered_count >= total:
        result = format_glossary_result_text(int(session.get("score", 0)), total)
        context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
        await message.reply_text(
            f"{feedback}\n\n{result}",
            reply_markup=get_main_menu_keyboard() if message.chat.type == "private" else None,
            parse_mode="HTML",
        )
        return
    await message.reply_text(
        feedback,
        reply_markup=build_glossary_feedback_keyboard(has_next=True),
        parse_mode="HTML",
    )


async def glossary_reply_text_next_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or message.text is None or message.text.strip().lower() != CLASSIC_REPLY_NEXT_TEXT.lower():
        return
    classic_state = _get_classic_reply_state(context)
    if classic_state.get("status") == "awaiting_next":
        return
    session = _active_glossary_session(context)
    if session is None or session.get("status") != "awaiting_next" or not session.get("answered"):
        return
    selected_topic_id = session.get("topic_id")
    entries = load_glossary_entries(selected_topic_id) if isinstance(selected_topic_id, str) else None
    if entries is None:
        context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
        await message.reply_text(GLOSSARY_UNAVAILABLE_TEXT, reply_markup=get_main_menu_keyboard() if message.chat.type == "private" else None)
        return
    session["current_index"] = int(session.get("current_index", 0)) + 1
    await _send_current_glossary_question_to_chat(message.chat, None, context, session, entries)
