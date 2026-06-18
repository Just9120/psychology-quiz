from __future__ import annotations

from html import escape
import random
import json
import logging
import re
import urllib.parse
import threading
import asyncio
import time

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from app.config import load_settings
from app.logging_config import configure_app_logging
from app.handler_latency import HandlerLatency as _HandlerLatency
from app.miniapp_entrypoint_handlers import (
    MINI_APP_BUTTON_ALIASES,
    MINI_APP_BUTTON_TEXT,
    build_miniapp_launch_inline_keyboard,
    mini_app_menu_button_handler,
    ui_command,
)
from app.glossary_handlers import (
    glossary_button_handler,
    glossary_callback,
    glossary_command,
    glossary_reply_text_answer_handler,
    glossary_reply_text_next_handler,
)
from app.db import (
    abandon_in_progress_sessions_for_user,
    create_or_load_user,
    get_user_reading_mode,
    finalize_quiz_session,
    get_active_categories,
    get_answered_questions_count,
    get_connection,
    get_current_unanswered_question,
    get_question_options,
    get_quiz_session,
    get_selected_categories_for_session,
    get_owner_stats,
    init_db_connection,
    select_random_approved_question_ids_across_active_categories,
    select_random_approved_question_ids_by_category,
    select_random_approved_question_ids_by_categories,
    set_user_reading_mode,
    set_selected_categories_for_session,
    start_quiz_session,
    store_session_questions,
)

from app.miniapp_runner import build_miniapp_runner_state, get_current_miniapp_question_snapshot, submit_miniapp_answer_event
from app.miniapp_api import start_miniapp_api_server
from app.miniapp_context import (
    build_miniapp_setup_context,
    build_miniapp_url,
    build_miniapp_url_with_fallback,
)
from app.glossary import GLOSSARY_QUIZ_SESSION_KEY
from app.classic_quiz_handlers import (
    build_quiz_mode_keyboard,
    build_difficulty_keyboard,
    build_category_keyboard,
    build_quiz_finished_text,
    build_selected_mix_keyboard,
    build_question_count_keyboard,
    _classic_reply_mode_enabled,
    _safe_classic_text_log_fields,
    _classic_text_latency_bucket,
    _load_classic_text_next_state,
    _load_classic_text_answer_context,
    _handle_classic_text_answer_db,
    answer_callback,
    build_classic_answer_reply_keyboard,
    build_classic_reply_feedback_text,
    start_mix_quiz,
    show_finished_quiz_message,
    send_quiz_result_with_main_menu,
    send_current_question_to_message,
    send_current_question_to_chat,
    send_current_question,
    restore_main_menu_after_quiz,
    remove_main_menu_for_active_quiz,
    build_question_text_with_options,
    build_classic_next_reply_keyboard,
    category_callback,
    classic_reply_text_answer_handler,
    classic_reply_text_next_handler,
    difficulty_mode_all_callback,
    difficulty_mode_callback,
    difficulty_mode_selected_mix_callback,
    mix_selection_callback,
    next_callback,
    parse_classic_reply_answer_number,
    question_count_callback,
    question_count_mix_callback,
    question_count_selected_mix_callback,
    quiz_command,
    quiz_mode_callback,
    start_quiz_button_handler,
)



logger = logging.getLogger(__name__)

START_QUIZ_BUTTON_TEXT = "🎯 Начать"
READING_MODE_BUTTON_TEXT = "👁 Чтение"
GLOSSARY_BUTTON_TEXT = "📚 Глоссарий"
LEGACY_START_QUIZ_BUTTON_TEXT = "🎯 Начать викторину"
LEGACY_READING_MODE_BUTTON_TEXT = "👁 Режим чтения"
START_QUIZ_BUTTON_ALIASES = (START_QUIZ_BUTTON_TEXT, LEGACY_START_QUIZ_BUTTON_TEXT)
READING_MODE_BUTTON_ALIASES = (READING_MODE_BUTTON_TEXT, LEGACY_READING_MODE_BUTTON_TEXT)
GLOSSARY_BUTTON_ALIASES = (GLOSSARY_BUTTON_TEXT, "Глоссарий")
HELP_TEXT = (
    "Что можно сделать:\n"
    "\n"
    f"{START_QUIZ_BUTTON_TEXT} — пройти викторину прямо в чате.\n"
    f"{MINI_APP_BUTTON_TEXT} — открыть удобный режим внутри Telegram.\n"
    f"{READING_MODE_BUTTON_TEXT} — выбрать обычный или бионический режим.\n"
    f"{GLOSSARY_BUTTON_TEXT} — пройти тест по терминам.\n"
    "🙈 Скрыть меню — убрать нижнюю клавиатуру.\n"
    "\n"
    "/start — вернуть меню\n"
    "/quiz — начать викторину в чате\n"
    "/ui — открыть викторину в окне\n"
    "/glossary — открыть глоссарий-тест\n"
    "\n"
    "Если меню скрыто, нажмите кнопку «Меню» рядом со строкой ввода или отправьте /start."
)
HIDE_MENU_BUTTON_TEXT = "🙈 Скрыть меню"
CLASSIC_REPLY_NEXT_TEXT = "Далее"
CLASSIC_REPLY_STATE_KEY = "classic_reply_keyboard_state"
READING_MODE_LABELS = {
    "normal": "Обычный",
    "bionic": "Бионическое чтение",
}
WORD_RE = re.compile(r"([0-9A-Za-zА-Яа-яЁё]+|[^0-9A-Za-zА-Яа-яЁё]+)")
MAX_WEBAPP_DATA_BYTES = 4096
UPDATE_INGRESS_LOG_PREFIX = "bot_update_ingress"
UPDATE_INGRESS_HANDLER_GROUP = -100
HANDLER_START_LOG_PREFIX = "bot_handler_start"
LATENCY_LOG_PREFIX = "bot_latency"
SLOW_LATENCY_LOG_PREFIX = "bot_latency_slow"
SLOW_HANDLER_THRESHOLD_MS = 1000



def _safe_callback_prefix(data: object) -> str | None:
    if not isinstance(data, str) or not data:
        return None
    prefix = data.split(":", 1)[0]
    if re.fullmatch(r"[A-Za-z0-9_]{1,32}", prefix):
        return prefix
    return None


def _safe_message_kind(message: object | None) -> str | None:
    if message is None:
        return None
    if getattr(message, "web_app_data", None) is not None:
        return "web_app_data"

    text = getattr(message, "text", None)
    if not isinstance(text, str):
        return None
    if text.startswith("/"):
        return "command"
    if text in {
        *START_QUIZ_BUTTON_ALIASES,
        *MINI_APP_BUTTON_ALIASES,
        "ℹ️ Помощь",
        *READING_MODE_BUTTON_ALIASES,
        *GLOSSARY_BUTTON_ALIASES,
        HIDE_MENU_BUTTON_TEXT,
    }:
        return "text_button"
    return None


def _safe_update_type(update: Update) -> str:
    if getattr(update, "callback_query", None) is not None:
        return "callback_query"
    message = getattr(update, "message", None)
    if message is not None:
        if getattr(message, "web_app_data", None) is not None:
            return "web_app_data"
        return "message"
    return "unknown"


def _safe_update_user_id(update: Update) -> int | None:
    effective_user = getattr(update, "effective_user", None)
    user_id = getattr(effective_user, "id", None)
    if user_id is not None:
        return user_id
    callback_query = getattr(update, "callback_query", None)
    callback_user = getattr(callback_query, "from_user", None)
    return getattr(callback_user, "id", None)


async def update_ingress_logger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    fields = [
        f"update_id={getattr(update, 'update_id', None)}",
        f"update_type={_safe_update_type(update)}",
    ]

    callback_query = getattr(update, "callback_query", None)
    callback_prefix = _safe_callback_prefix(getattr(callback_query, "data", None))
    if callback_prefix:
        fields.append(f"callback_prefix={callback_prefix}")

    telegram_user_id = _safe_update_user_id(update)
    if telegram_user_id is not None:
        fields.append(f"telegram_user_id={telegram_user_id}")

    message_kind = _safe_message_kind(getattr(update, "message", None))
    if message_kind:
        fields.append(f"message_kind={message_kind}")

    logger.info("%s %s", UPDATE_INGRESS_LOG_PREFIX, " ".join(fields))


def register_update_ingress_handler(application: Application) -> None:
    application.add_handler(
        TypeHandler(Update, update_ingress_logger),
        group=UPDATE_INGRESS_HANDLER_GROUP,
    )


def _safe_callback_session_id(data: str, expected_prefix: str) -> int | None:
    parts = data.split(":", 2)
    if len(parts) < 2 or parts[0] != expected_prefix:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None

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


def option_index_to_label(option_index: int) -> str:
    if option_index < 0:
        raise ValueError("option_index must be non-negative")

    label = ""
    current_index = option_index
    while True:
        current_index, remainder = divmod(current_index, 26)
        label = chr(ord("A") + remainder) + label
        if current_index == 0:
            break
        current_index -= 1
    return label


def apply_bionic_reading(text: str) -> str:
    rendered_parts: list[str] = []
    for chunk in re.split(r"(\s+)", text):
        if not chunk:
            continue
        if chunk.isspace():
            rendered_parts.append(chunk)
            continue
        for part in WORD_RE.findall(chunk):
            if not part:
                continue
            if not re.fullmatch(r"[0-9A-Za-zА-Яа-яЁё]+", part):
                rendered_parts.append(escape(part))
                continue
            if len(part) <= 3:
                rendered_parts.append(escape(part))
                continue

            part_length = len(part)
            if part_length <= 5:
                bold_len = 1
            elif part_length <= 9:
                bold_len = 2
            else:
                bold_len = 3
            prefix = escape(part[:bold_len])
            suffix = escape(part[bold_len:])
            rendered_parts.append(f"<b>{prefix}</b>{suffix}")

    return "".join(rendered_parts)


def render_reading_mode_text(text: str, mode: str) -> str:
    if mode == "bionic":
        return apply_bionic_reading(text)
    return escape(text)


def format_reading_mode_screen(current_mode: str) -> str:
    mode_label = READING_MODE_LABELS.get(current_mode, READING_MODE_LABELS["normal"])
    return (
        "Режим чтения\n"
        "\n"
        f"Текущий режим: {mode_label}\n"
        "\n"
        "Режим влияет на отображение текста вопросов и пояснений.\n"
        "Бионическое чтение выделяет начало слов жирным, чтобы текст было легче читать."
    )


def build_reading_mode_keyboard(current_mode: str = "normal") -> InlineKeyboardMarkup:
    normalized_mode = current_mode if current_mode in READING_MODE_LABELS else "normal"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"{'✅ ' if normalized_mode == 'normal' else ''}{READING_MODE_LABELS['normal']}",
                    callback_data="readingmode:set:normal",
                )
            ],
            [
                InlineKeyboardButton(
                    f"{'✅ ' if normalized_mode == 'bionic' else ''}{READING_MODE_LABELS['bionic']}",
                    callback_data="readingmode:set:bionic",
                )
            ],
        ]
    )


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Запуск бота"),
            BotCommand("help", "Список команд"),
            BotCommand("ping", "Проверить, что бот на связи"),
            BotCommand("quiz", "Начать викторину"),
            BotCommand("ui", "Открыть викторину в окне"),
            BotCommand("glossary", "Открыть глоссарий"),
        ]
    )


async def _run_db_task(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def build_post_setup_miniapp_prompt(
    base_url: str,
    categories,
    runner_state: dict | None,
    *,
    api_base_url: str | None = None,
) -> tuple[str, InlineKeyboardMarkup | None]:
    miniapp_url, _ = build_miniapp_url_with_fallback(base_url, categories, runner_state, api_base_url=api_base_url)
    if not miniapp_url:
        return (
            "Викторина создана, но не удалось подготовить ссылку Mini App. "
            "Откройте /ui заново или используйте /quiz для прохождения в чате.",
            None,
        )
    return (
        "Викторина создана. Откройте её в окне, чтобы начать.",
        build_miniapp_launch_inline_keyboard(miniapp_url),
    )



async def safe_reply(update: Update, text: str) -> None:
    if update.message:
        await update.message.reply_text(text)


def is_private_chat(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type == "private")


def build_menu_button_regex(*labels: str) -> str:
    return rf"^({'|'.join(re.escape(label) for label in labels)})$"


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


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
    context.user_data.pop(CLASSIC_REPLY_STATE_KEY, None)
    message_text = (
        "Привет! Я учебный бот-викторина по психологии.\n"
        "\n"
        "Можно пройти викторину двумя способами:\n"
        "🎯 В чате — быстрый классический режим.\n"
        "🚀 В окне — удобный режим внутри Telegram.\n"
        "📚 Глоссарий — короткие определения по темам.\n"
        "\n"
        "Выберите действие ниже 👇"
    )
    await update.message.reply_text(
        message_text,
        reply_markup=get_main_menu_keyboard() if is_private_chat(update) else None,
    )


async def help_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await help_command(update, context)


async def reading_mode_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if tg_user is None or update.message is None:
        return

    settings = context.application.bot_data["settings"]

    def _load_mode():
        with get_connection(settings.db_path) as conn:
            user_row = create_or_load_user(
                conn,
                telegram_user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
            return get_user_reading_mode(conn, int(user_row["id"]))

    current_mode = await _run_db_task(_load_mode)

    await update.message.reply_text(
        format_reading_mode_screen(current_mode),
        reply_markup=build_reading_mode_keyboard(current_mode),
    )


async def hide_menu_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    removal_message = None
    try:
        removal_message = await message.reply_text(
            text="\u2060",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception:
        logger.exception("Не удалось скрыть меню для сообщения %s", message.message_id)

    if removal_message is not None:
        try:
            await removal_message.delete()
        except Exception:
            logger.debug(
                "Не удалось удалить техническое сообщение скрытия меню %s",
                removal_message.message_id,
            )

    try:
        await message.delete()
    except Exception:
        logger.debug("Не удалось удалить сообщение-триггер скрытия меню %s", message.message_id)



async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await safe_reply(update, HELP_TEXT)


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await safe_reply(update, "Бот на связи ✅")


def format_owner_stats_text(stats: dict) -> str:
    lines = [
        "📊 Статистика бота",
        "",
        f"Пользователи всего: {stats['total_users']}",
        (
            "Новые пользователи: "
            f"24ч — {stats['new_users_24h']}, "
            f"7д — {stats['new_users_7d']}, "
            f"30д — {stats['new_users_30d']}"
        ),
        (
            "Активные пользователи: "
            f"24ч — {stats['active_users_24h']}, "
            f"7д — {stats['active_users_7d']}, "
            f"30д — {stats['active_users_30d']}"
        ),
        "",
        f"Сессии всего: {stats['total_quiz_sessions']}",
        f"Сессии завершено: {stats['completed_quiz_sessions']}",
        f"Сессии в процессе: {stats['in_progress_quiz_sessions']}",
        f"Ответов всего: {stats['total_quiz_answers']}",
        "",
        f"Одобренных вопросов: {stats['total_approved_questions']}",
        f"Активных категорий: {stats['active_categories_count']}",
        "",
        "Вопросы по категориям:",
    ]

    questions_by_category = stats.get("questions_by_category", [])
    if questions_by_category:
        lines.extend(
            f"• {item['category_name']}: {item['question_count']}"
            for item in questions_by_category
        )
    else:
        lines.append("• Нет данных")

    lines.extend(["", "Топ-5 категорий по начатым сессиям (30 дней):"])
    top_categories = stats.get("top_categories_30d", [])
    if top_categories:
        lines.extend(
            f"• {item['category_name']}: {item['started_sessions']}"
            for item in top_categories
        )
    else:
        lines.append("• Нет данных")

    return "\n".join(lines)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_private_chat(update):
        return

    user = update.effective_user
    if user is None:
        return

    settings = context.application.bot_data["settings"]
    if not settings.admin_telegram_ids or user.id not in settings.admin_telegram_ids:
        await safe_reply(update, "Недоступно")
        return

    def _load_stats():
        with get_connection(settings.db_path) as conn:
            return get_owner_stats(conn)

    stats = await _run_db_task(_load_stats)
    await safe_reply(update, format_owner_stats_text(stats))


def _parse_miniapp_answer_payload(payload: dict) -> tuple[int, int, int] | None:
    if payload.get("type") != "quiz_answer":
        return None
    session_id = payload.get("session_id")
    question_id = payload.get("question_id")
    selected_option_index = payload.get("selected_option_index")
    if not all(type(v) is int for v in (session_id, question_id, selected_option_index)):
        return None
    if session_id <= 0 or question_id <= 0 or selected_option_index < 0:
        return None
    return session_id, question_id, selected_option_index
def _invalid_miniapp_payload_text() -> str:
    return (
        "Не удалось запустить викторину: некорректные параметры Mini App.\n"
        "Откройте настройку заново через /ui или запустите обычную викторину через /quiz."
    )


async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or message.web_app_data is None:
        return
    if not is_private_chat(update):
        await message.reply_text("Викторина в окне доступна только в личном чате с ботом.")
        return
    try:
        await message.delete()
    except Exception:
        logger.debug("Не удалось удалить service message web_app_data: %s", message.message_id)

    raw_data = message.web_app_data.data or ""
    if not raw_data or len(raw_data.encode("utf-8")) > MAX_WEBAPP_DATA_BYTES:
        await message.chat.send_message(_invalid_miniapp_payload_text())
        return
    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        await message.chat.send_message(_invalid_miniapp_payload_text())
        return
    if not isinstance(payload, dict):
        await message.chat.send_message(_invalid_miniapp_payload_text())
        return

    answer_payload = _parse_miniapp_answer_payload(payload)
    if answer_payload is not None:
        settings = context.application.bot_data["settings"]
        tg_user = update.effective_user
        if tg_user is None:
            await message.chat.send_message("Не удалось определить пользователя.")
            return

        session_id, question_id, selected_option_index = answer_payload
        def _handle_webapp_answer():
            with get_connection(settings.db_path) as conn:
                user_row = create_or_load_user(conn, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
                submission = submit_miniapp_answer_event(
                    conn,
                    session_id=session_id,
                    actor_user_id=int(user_row["id"]),
                    question_id=question_id,
                    selected_option_index=selected_option_index,
                )
                if submission.status != "accepted":
                    return {"status": submission.status}

                session = get_quiz_session(conn, session_id)
                if session is not None and str(session["status"]) == "in_progress":
                    current_unanswered = get_current_unanswered_question(conn, session_id)
                    if current_unanswered is None:
                        finalized = finalize_quiz_session(conn, session_id)
                        if finalized is None:
                            return {"status": "finalize_failed"}
                        result_url, _ = build_miniapp_url_with_fallback(
                            settings.mini_app_url,
                            get_active_categories(conn),
                            build_miniapp_runner_state(conn, actor_user_id=int(user_row["id"]), session_id=session_id),
                            api_base_url=settings.mini_app_api_base_url,
                        )
                        return {
                            "status": "accepted_finished",
                            "score": int(finalized["score"]),
                            "total_questions": int(finalized["total_questions"]),
                            "result_url": result_url,
                        }

                next_url, _ = build_miniapp_url_with_fallback(
                    settings.mini_app_url,
                    get_active_categories(conn),
                    build_miniapp_runner_state(conn, actor_user_id=int(user_row["id"])),
                    api_base_url=settings.mini_app_api_base_url,
                )
                return {"status": "accepted_next", "next_url": next_url}

        result = await _run_db_task(_handle_webapp_answer)
        if result["status"] == "accepted_finished":
            await message.chat.send_message(
                f"Ответ получен. Сессия завершена: {result['score']} из {result['total_questions']}.",
                reply_markup=build_miniapp_launch_inline_keyboard(result["result_url"], reopen_result=True) if result["result_url"] else None,
            )
            return
        if result["status"] == "accepted_next":
            await message.chat.send_message(
                "Ответ получен. Откройте Mini App для следующего шага.",
                reply_markup=build_miniapp_launch_inline_keyboard(result["next_url"]) if result["next_url"] else None,
            )
            return
        if result["status"] == "finalize_failed":
            await message.chat.send_message("Ответ получен. Обновите /ui для проверки состояния.")
            return
        if result["status"] == "duplicate":
            await message.chat.send_message("Ответ уже получен для этого шага. Откройте /ui снова, чтобы синхронизировать состояние.")
            return
        if result["status"] == "stale_question":
            await message.chat.send_message("Этот вопрос уже неактуален. Откройте /ui снова, чтобы продолжить с актуального вопроса.")
            return
        if result["status"] == "invalid_option":
            await message.chat.send_message("Некорректный вариант ответа. Откройте /ui снова и выберите вариант из текущего вопроса.")
            return
        if result["status"] in {"session_not_found", "invalid_question"}:
            await message.chat.send_message("Сессия не найдена или уже завершена. Запустите /ui для новой попытки или используйте /quiz.")
            return
        if result["status"] == "forbidden":
            await message.chat.send_message("Эта сессия вам не принадлежит.")
            return
        await message.chat.send_message("Не удалось обработать ответ. Откройте /ui заново.")
        return

    quiz_mode = payload.get("quiz_mode")
    question_count = payload.get("question_count")
    difficulty = payload.get("difficulty")
    category_ids = payload.get("category_ids")
    if (
        payload.get("type") != "quiz_setup"
        or quiz_mode not in {"single", "selected_mix", "all"}
        or question_count not in {5, 10, 15, None}
        or difficulty not in {"any", "easy", "medium", "hard"}
        or not isinstance(category_ids, list)
        or any(not isinstance(item, int) for item in category_ids)
    ):
        await message.chat.send_message(_invalid_miniapp_payload_text())
        return

    settings = context.application.bot_data["settings"]
    tg_user = update.effective_user
    if tg_user is None:
        await message.chat.send_message(_invalid_miniapp_payload_text())
        return
    def _handle_webapp_setup():
        with get_connection(settings.db_path) as conn:
            active_categories = get_active_categories(conn)
            active_ids = {int(row["id"]) for row in active_categories}
            difficulty_filter = None if difficulty == "any" else difficulty
            selected_ids: list[int] | None
            session_category_id: int | None
            if quiz_mode == "single":
                if len(category_ids) != 1:
                    return {"status": "invalid_payload"}
                category_id = int(category_ids[0])
                if category_id not in active_ids:
                    return {"status": "category_unavailable"}
                question_ids = select_random_approved_question_ids_by_category(conn, category_id, question_count, difficulty_filter)
                session_category_id = category_id
                selected_ids = None
            elif quiz_mode == "selected_mix":
                if not category_ids:
                    return {"status": "invalid_payload"}
                if any(category_id not in active_ids for category_id in category_ids):
                    return {"status": "selected_unavailable"}
                for category_id in category_ids:
                    category_probe = select_random_approved_question_ids_by_category(
                        conn,
                        category_id=category_id,
                        limit=1,
                        difficulty_mode=difficulty_filter,
                    )
                    if not category_probe:
                        return {"status": "questions_not_found"}
                question_ids = select_random_approved_question_ids_by_categories(conn, category_ids, question_count, difficulty_filter)
                session_category_id = None
                selected_ids = category_ids
            else:
                # Safer behavior: all mode ignores client category_ids completely.
                question_ids = select_random_approved_question_ids_across_active_categories(conn, question_count, difficulty_filter)
                session_category_id = None
                selected_ids = None
            if not question_ids:
                return {"status": "questions_not_found"}
            user_row = create_or_load_user(conn, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
            abandon_in_progress_sessions_for_user(conn, int(user_row["id"]))
            session_id = start_quiz_session(conn, int(user_row["id"]), session_category_id, difficulty_mode=difficulty_filter)
            if selected_ids:
                set_selected_categories_for_session(conn, session_id, selected_ids)
            store_session_questions(conn, session_id, question_ids)
            runner_state = build_miniapp_runner_state(conn, actor_user_id=int(user_row["id"]), session_id=session_id)
            refreshed_categories = get_active_categories(conn)
            return {"status": "ok", "runner_state": runner_state, "active_categories": refreshed_categories}

    setup_result = await _run_db_task(_handle_webapp_setup)
    if setup_result["status"] == "invalid_payload":
        await message.chat.send_message(_invalid_miniapp_payload_text())
        return
    if setup_result["status"] == "category_unavailable":
        await message.chat.send_message("Выбранная тема больше недоступна. Откройте настройку викторины заново.")
        return
    if setup_result["status"] == "selected_unavailable":
        await message.chat.send_message("Выбранные темы больше недоступны. Откройте настройку викторины заново.")
        return
    if setup_result["status"] == "questions_not_found":
        await message.chat.send_message(
            "Не удалось подобрать вопросы под выбранные параметры.\n"
            "Попробуйте изменить тему, количество вопросов или сложность."
        )
        return

    removal_message = None
    try:
        removal_message = await message.chat.send_message("\u2060", reply_markup=ReplyKeyboardRemove())
    except Exception:
        logger.debug("Не удалось скрыть главное меню после Mini App setup.")
    if removal_message is not None:
        try:
            await removal_message.delete()
        except Exception:
            logger.debug("Не удалось удалить техническое сообщение скрытия меню %s", removal_message.message_id)
    confirmation_text, confirmation_keyboard = build_post_setup_miniapp_prompt(
        settings.mini_app_url,
        setup_result["active_categories"],
        setup_result["runner_state"],
        api_base_url=settings.mini_app_api_base_url,
    )
    await message.chat.send_message(confirmation_text, reply_markup=confirmation_keyboard)


async def reading_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(handler="reading_mode_callback", callback_prefix="readingmode", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    if not data.startswith("readingmode:"):
        return
    latency.start()

    await _timed_telegram_api_call(latency, query.answer())

    if data == "readingmode:menu":
        tg_user = update.effective_user
        if tg_user is None:
            await _timed_telegram_api_call(latency, query.edit_message_text("Не удалось определить пользователя."), api_kind="message_edit")
            latency.summary()
            return

        settings = context.application.bot_data["settings"]
        def _load_current_mode():
            with get_connection(settings.db_path) as conn:
                user_row = create_or_load_user(
                    conn,
                    telegram_user_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                )
                return get_user_reading_mode(conn, int(user_row["id"]))
        db_started_at = time.perf_counter()
        current_mode = await _run_db_task(_load_current_mode)
        latency.add_db(db_started_at)

        await _timed_telegram_api_call(latency, query.edit_message_text(
            format_reading_mode_screen(current_mode),
            reply_markup=build_reading_mode_keyboard(current_mode),
        ))
        latency.summary()
        return

    if not data.startswith("readingmode:set:"):
        latency.summary()
        return

    mode = data.split(":")[-1]
    if mode not in READING_MODE_LABELS:
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректный режим чтения."))
        latency.summary()
        return

    tg_user = update.effective_user
    if tg_user is None:
        await _timed_telegram_api_call(latency, query.edit_message_text("Не удалось определить пользователя."), api_kind="message_edit")
        latency.summary()
        return

    settings = context.application.bot_data["settings"]
    def _save_mode():
        with get_connection(settings.db_path) as conn:
            user_row = create_or_load_user(
                conn,
                telegram_user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
            return set_user_reading_mode(conn, int(user_row["id"]), mode)
    db_started_at = time.perf_counter()
    saved_mode = await _run_db_task(_save_mode)
    latency.add_db(db_started_at)

    await _timed_telegram_api_call(latency, query.edit_message_text(
        f"Режим чтения обновлён: {READING_MODE_LABELS[saved_mode]}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Изменить режим", callback_data="readingmode:menu")]]
        ),
    ))
    latency.summary()



def configure_logging(log_level: str) -> None:
    configure_app_logging(log_level)


def should_start_miniapp_api(settings) -> bool:
    if not settings.miniapp_api_enabled:
        return False
    if not settings.mini_app_api_base_url:
        logger.warning("Mini App API explicitly enabled but MINI_APP_API_BASE_URL is missing; API server will not start.")
        return False
    if not settings.miniapp_api_allowed_origin:
        logger.warning("Mini App API enabled without MINIAPP_API_ALLOWED_ORIGIN; cross-origin Mini App fetch may be blocked.")
    return True


def _safe_webhook_host_for_log(settings) -> str:
    webhook_url = settings.telegram_webhook_url or ""
    parsed = urllib.parse.urlparse(webhook_url)
    return parsed.hostname or ""


def _safe_webhook_path_for_log(settings) -> str:
    webhook_url = settings.telegram_webhook_url or ""
    parsed = urllib.parse.urlparse(webhook_url)
    path = parsed.path or "/"
    for secret in (settings.bot_token, settings.telegram_webhook_secret_token):
        if secret:
            path = path.replace(secret, "<redacted>")
    return path


def _webhook_url_path(settings) -> str:
    webhook_url = settings.telegram_webhook_url or ""
    parsed = urllib.parse.urlparse(webhook_url)
    return parsed.path.lstrip("/")


def run_application(application: Application, settings) -> None:
    if settings.telegram_update_mode == "webhook":
        safe_host = _safe_webhook_host_for_log(settings)
        safe_path = _safe_webhook_path_for_log(settings)
        logger.info(
            "bot_update_mode mode=webhook webhook_host=%s listen=%s port=%s path=%s",
            safe_host,
            settings.telegram_webhook_listen,
            settings.telegram_webhook_port,
            safe_path,
        )
        application.run_webhook(
            listen=settings.telegram_webhook_listen,
            port=settings.telegram_webhook_port,
            url_path=_webhook_url_path(settings),
            webhook_url=settings.telegram_webhook_url,
            secret_token=settings.telegram_webhook_secret_token,
        )
        return

    logger.info("bot_update_mode mode=polling")
    application.run_polling()


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)

    logger.info("Запуск приложения в окружении '%s'", settings.app_env)
    logger.info("Проверка подключения к SQLite: %s", settings.db_path)
    init_db_connection(settings.db_path)
    logger.info("Подключение к SQLite успешно")

    application = Application.builder().token(settings.bot_token).post_init(post_init).build()
    application.bot_data["settings"] = settings

    register_update_ingress_handler(application)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("ui", ui_command))
    application.add_handler(CommandHandler("glossary", glossary_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.Regex(build_menu_button_regex(*START_QUIZ_BUTTON_ALIASES)),
            start_quiz_button_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.Regex(build_menu_button_regex(*MINI_APP_BUTTON_ALIASES)),
            mini_app_menu_button_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.Regex(r"^ℹ️ Помощь$"),
            help_button_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.Regex(build_menu_button_regex(*READING_MODE_BUTTON_ALIASES)),
            reading_mode_button_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.Regex(build_menu_button_regex(*GLOSSARY_BUTTON_ALIASES)),
            glossary_button_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.Regex(rf"^{re.escape(HIDE_MENU_BUTTON_TEXT)}$"),
            hide_menu_button_handler,
        )
    )
    if _classic_reply_mode_enabled(settings):
        application.add_handler(
            MessageHandler(
                filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND & filters.Regex(r"^\s*\d+\s*$"),
                classic_reply_text_answer_handler,
            )
        )
        application.add_handler(
            MessageHandler(
                filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND & filters.Regex(rf"^\s*{re.escape(CLASSIC_REPLY_NEXT_TEXT)}\s*$"),
                classic_reply_text_next_handler,
            )
        )
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND & filters.Regex(r"^\s*\d+\s*$"),
            glossary_reply_text_answer_handler,
        ),
        group=1,
    )
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND & filters.Regex(rf"^\s*{re.escape(CLASSIC_REPLY_NEXT_TEXT)}\s*$"),
            glossary_reply_text_next_handler,
        ),
        group=1,
    )
    application.add_handler(
        CallbackQueryHandler(
            reading_mode_callback,
            pattern=r"^readingmode:(menu|set:(normal|bionic))$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            glossary_callback,
            pattern=r"^(gls:(topics|main|topic:[a-z0-9_]+)|glsq:(count:[a-z0-9_]+:(5|10|all)|retry))$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(quiz_mode_callback, pattern=r"^qzmode:(single|selected_mix|all)$")
    )
    application.add_handler(CallbackQueryHandler(category_callback, pattern=r"^cat:\d+$"))
    application.add_handler(CallbackQueryHandler(question_count_callback, pattern=r"^qcnt:\d+:(5|10|15|all)$"))
    application.add_handler(
        CallbackQueryHandler(
            difficulty_mode_callback,
            pattern=r"^qmode:\d+:(5|10|15|all):(any|easy|medium|hard)$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(question_count_mix_callback, pattern=r"^qcntall:(5|10|15|all)$")
    )
    application.add_handler(
        CallbackQueryHandler(
            difficulty_mode_all_callback,
            pattern=r"^qmodeall:(5|10|15|all):(any|easy|medium|hard)$",
        )
    )
    application.add_handler(CallbackQueryHandler(mix_selection_callback, pattern=r"^mixsel:(toggle:\d+|done|reset)$"))
    application.add_handler(
        CallbackQueryHandler(question_count_selected_mix_callback, pattern=r"^qcntselmix:(5|10|15|all)$")
    )
    application.add_handler(
        CallbackQueryHandler(
            difficulty_mode_selected_mix_callback,
            pattern=r"^qmodeselmix:(5|10|15|all):(any|easy|medium|hard)$",
        )
    )
    application.add_handler(CallbackQueryHandler(answer_callback, pattern=r"^ans:\d+:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(next_callback, pattern=r"^next:\d+$"))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))

    api_server = None
    if settings.miniapp_legacy_api_enabled and should_start_miniapp_api(settings):
        api_server = start_miniapp_api_server(
            settings.miniapp_api_bind,
            settings.miniapp_api_port,
            db_path=settings.db_path,
            bot_token=settings.bot_token,
            initdata_ttl_seconds=settings.miniapp_api_initdata_ttl_seconds,
            allowed_origin=settings.miniapp_api_allowed_origin,
        )
        api_thread = threading.Thread(target=api_server.serve_forever, daemon=True)
        api_thread.start()
        logger.info("Mini App API server started on %s:%s", settings.miniapp_api_bind, settings.miniapp_api_port)
    elif not settings.miniapp_legacy_api_enabled:
        logger.info("Legacy Mini App API server is disabled by MINIAPP_LEGACY_API_ENABLED=false.")
    else:
        logger.info("Mini App API server is disabled. Mini App uses sendData fallback unless API is explicitly enabled/configured.")

    try:
        run_application(application, settings)
    finally:
        if api_server is not None:
            api_server.shutdown()
            api_server.server_close()


if __name__ == "__main__":
    main()
