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

QUESTION_COUNT_CHOICES = (
    (5, "5"),
    (10, "10"),
    (15, "15"),
    (None, "Все доступные"),
)

DIFFICULTY_CHOICES = (
    ("any", "Любые"),
    ("easy", "Лёгкие"),
    ("medium", "Средние"),
    ("hard", "Сложные"),
)

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


def build_question_count_keyboard(callback_prefix: str, category_id: int | None = None) -> InlineKeyboardMarkup:
    keyboard = []
    for count, label in QUESTION_COUNT_CHOICES:
        count_value = "all" if count is None else str(count)
        if category_id is None:
            callback_data = f"{callback_prefix}:{count_value}"
        else:
            callback_data = f"{callback_prefix}:{category_id}:{count_value}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    return InlineKeyboardMarkup(keyboard)


def build_difficulty_keyboard(
    callback_prefix: str,
    category_id: int | None = None,
    count_raw: str | None = None,
) -> InlineKeyboardMarkup:
    keyboard = []
    for mode, label in DIFFICULTY_CHOICES:
        if category_id is None:
            callback_data = f"{callback_prefix}:{count_raw}:{mode}"
        else:
            callback_data = f"{callback_prefix}:{category_id}:{count_raw}:{mode}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    return InlineKeyboardMarkup(keyboard)


def build_category_keyboard(categories) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(str(row["name"]), callback_data=f"cat:{int(row['id'])}")]
        for row in categories
    ]
    return InlineKeyboardMarkup(keyboard)


def build_quiz_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Конкретная тема", callback_data="qzmode:single")],
            [InlineKeyboardButton("Микс из выбранных тем", callback_data="qzmode:selected_mix")],
            [InlineKeyboardButton("Все темы", callback_data="qzmode:all")],
        ]
    )


def build_selected_mix_keyboard(categories, selected_ids: set[int]) -> InlineKeyboardMarkup:
    keyboard = []
    for row in categories:
        category_id = int(row["id"])
        marker = "✅" if category_id in selected_ids else "☑️"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{marker} {row['name']}",
                    callback_data=f"mixsel:toggle:{category_id}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("Готово", callback_data="mixsel:done")])
    keyboard.append([InlineKeyboardButton("Сбросить", callback_data="mixsel:reset")])
    return InlineKeyboardMarkup(keyboard)


def build_quiz_finished_text(score: int, total_questions: int) -> str:
    return (
        "<b>Викторина завершена 🎉</b>\n\n"
        f"<b>Результат:</b> {score} из {total_questions}\n\n"
        f"Чтобы начать новую викторину, нажмите {START_QUIZ_BUTTON_TEXT} или отправьте /quiz."
    )


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


def build_classic_answer_reply_keyboard(options) -> ReplyKeyboardMarkup:
    buttons = [str(position) for position, _ in enumerate(options, start=1)]
    keyboard = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


def build_classic_next_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[CLASSIC_REPLY_NEXT_TEXT]], resize_keyboard=True, one_time_keyboard=False)


def numeric_answer_label_for_option(options, option_index: int) -> str:
    for position, opt in enumerate(options, start=1):
        if int(opt["option_index"]) == option_index:
            return str(position)
    raise ValueError("option_index is not present in options")


def _find_option_by_index(options, option_index: int):
    for opt in options:
        if int(opt["option_index"]) == option_index:
            return opt
    return None


def build_classic_reply_answer_detail_line(
    label: str,
    *,
    option_position_label: str,
    option_text: str,
    reading_mode: str,
) -> str:
    rendered_option_text = render_reading_mode_text(option_text, reading_mode)
    return f"<b>{label}:</b> {option_position_label} — {rendered_option_text}"


def build_classic_reply_feedback_text(result: dict) -> str:
    result_line = "<b>Верно ✅</b>" if result["is_correct"] else "<b>Неверно ❌</b>"
    answer_lines = [
        build_classic_reply_answer_detail_line(
            "Ваш ответ",
            option_position_label=str(result["selected_option_label"]),
            option_text=str(result["selected_option_text"]),
            reading_mode=str(result["reading_mode"]),
        )
    ]
    if not result["is_correct"]:
        answer_lines.append(
            build_classic_reply_answer_detail_line(
                "Правильный ответ",
                option_position_label=str(result["correct_option_label"]),
                option_text=str(result["correct_option_text"]),
                reading_mode=str(result["reading_mode"]),
            )
        )
    rendered_explanation = render_reading_mode_text(result["explanation"], result["reading_mode"])
    answer_lines_text = "\n".join(answer_lines)
    return (
        f"{result_line}\n\n"
        f"{answer_lines_text}\n\n"
        f"<b>Пояснение:</b>\n{rendered_explanation}\n\n"
        f"<b>Прогресс:</b> {result['answered_questions']} из {result['total_questions']}"
    )


def _classic_reply_mode_enabled(settings) -> bool:
    return bool(getattr(settings, "classic_quiz_reply_keyboard_mode", False))


def _set_classic_reply_state(context: ContextTypes.DEFAULT_TYPE | None, state: dict | None) -> None:
    if context is None:
        return
    if state is None:
        context.user_data.pop(CLASSIC_REPLY_STATE_KEY, None)
        return
    context.user_data[CLASSIC_REPLY_STATE_KEY] = state


def parse_classic_reply_answer_number(text: str, option_count: int) -> int | None:
    cleaned = text.strip()
    if not cleaned.isdigit():
        return None
    answer_number = int(cleaned)
    if not 1 <= answer_number <= option_count:
        return None
    return answer_number - 1


def _classic_text_latency_bucket(elapsed_ms: int) -> str:
    if elapsed_ms < 100:
        return "lt_100ms"
    if elapsed_ms < 500:
        return "lt_500ms"
    if elapsed_ms < 1000:
        return "lt_1000ms"
    return "gte_1000ms"


def _safe_classic_text_log_fields(*, telegram_user_id: int | None, session_id: int | None = None, question_id: int | None = None, elapsed_ms: int | None = None, status: str = "ok") -> str:
    fields = []
    if telegram_user_id is not None:
        fields.append(f"telegram_user_id={telegram_user_id}")
    if session_id is not None:
        fields.append(f"session_id={session_id}")
    if question_id is not None:
        fields.append(f"question_id={question_id}")
    if elapsed_ms is not None:
        fields.append(f"elapsed_ms={elapsed_ms}")
        fields.append(f"latency_bucket={_classic_text_latency_bucket(elapsed_ms)}")
    fields.append(f"status={status if re.fullmatch(r'[A-Za-z0-9_]{1,32}', status) else 'unknown'}")
    return " ".join(fields)


def _log_classic_text_event(event_name: str, **fields) -> None:
    if event_name in {
        "classic_text_answer_ingress",
        "classic_text_answer_latency",
        "classic_text_next_ingress",
        "classic_text_next_latency",
    }:
        logger.info("%s %s", event_name, _safe_classic_text_log_fields(**fields))


def build_question_text_with_options(
    order_index: int,
    total_questions: int,
    question_text: str,
    options,
    reading_mode: str,
    *,
    numeric_labels: bool = False,
    show_answer_keyboard_hint: bool = False,
) -> str:
    formatted_options = "\n".join(
        f"{position if numeric_labels else option_index_to_label(int(opt['option_index']))}. "
        f"{render_reading_mode_text(str(opt['option_text']), reading_mode)}"
        for position, opt in enumerate(options, start=1)
    )
    hint = "\n\nОтветьте кнопкой с номером варианта внизу 👇" if show_answer_keyboard_hint else ""
    return (
        f"<b>Вопрос {order_index} из {total_questions}</b>\n\n"
        f"{render_reading_mode_text(question_text, reading_mode)}\n\n"
        f"{formatted_options}"
        f"{hint}"
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
    _set_classic_reply_state(context, None)
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


async def start_quiz_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await quiz_command(update, context)


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


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]
    latency = _HandlerLatency(handler="quiz_command", command="/quiz", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    latency.start()
    context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)

    def _load_categories():
        with get_connection(settings.db_path) as conn:
            return get_active_categories(conn)

    db_started_at = time.perf_counter()
    categories = await _run_db_task(_load_categories)
    latency.add_db(db_started_at)

    if not categories:
        api_started_at = time.perf_counter()
        await safe_reply(update, "Нет доступных категорий. Сначала загрузите вопросы в базу данных.")
        latency.add_telegram_api(api_started_at)
        latency.summary()
        return

    if update.message:
        context.user_data["selected_mix_categories"] = set()
        render_started_at = time.perf_counter()
        reply_markup = build_quiz_mode_keyboard()
        latency.add_render(render_started_at)
        api_started_at = time.perf_counter()
        await update.message.reply_text(
            "Выберите режим викторины:\n\n"
            "Конкретная тема — вопросы по одной выбранной теме.\n"
            "Микс из выбранных тем — вопросы из нескольких тем.\n"
            "Все темы — случайные вопросы из всего доступного банка.",
            reply_markup=reply_markup,
        )
        latency.add_telegram_api(api_started_at)
    latency.summary()



async def send_current_question_to_chat(chat, settings, session_id: int) -> bool:
    latency = _HandlerLatency(handler="send_current_question_to_chat", callback_prefix="sendq", session_id=session_id)
    def _load_current_question():
        with get_connection(settings.db_path) as conn:
            current = get_current_unanswered_question(conn, session_id)
            if current is None:
                return {"current": None}
            question_id = int(current["question_id"])
            options = get_question_options(conn, question_id)
            session = get_quiz_session(conn, session_id)
            reading_mode = "normal"
            if session is not None:
                reading_mode = get_user_reading_mode(conn, int(session["user_id"]))
            return {"current": current, "question_id": question_id, "options": options, "reading_mode": reading_mode}

    db_started_at = time.perf_counter()
    loaded = await _run_db_task(_load_current_question)
    latency.add_db(db_started_at)
    current = loaded["current"]
    if current is None:
        latency.summary()
        return False
    question_id = loaded["question_id"]
    options = loaded["options"]
    reading_mode = loaded["reading_mode"]
    if not options:
        api_started_at = time.perf_counter()
        await chat.send_message("Для вопроса не найдены варианты ответа. Сессия завершена.")
        latency.add_telegram_api(api_started_at)
        latency.summary()
        return False
    keyboard = [[InlineKeyboardButton(option_index_to_label(int(opt["option_index"])), callback_data=f"ans:{session_id}:{question_id}:{int(opt['option_index'])}")] for opt in options]
    render_started_at = time.perf_counter()
    message_text = build_question_text_with_options(
        order_index=int(current["order_index"]),
        total_questions=int(current["total_questions"]),
        question_text=str(current["question_text"]),
        options=options,
        reading_mode=reading_mode,
    )
    markup = InlineKeyboardMarkup(keyboard)
    latency.add_render(render_started_at)
    api_started_at = time.perf_counter()
    await chat.send_message(message_text, reply_markup=markup, parse_mode="HTML")
    latency.add_telegram_api(api_started_at)
    latency.summary()
    return True




async def send_current_question_to_message(message, settings, session_id: int, context: ContextTypes.DEFAULT_TYPE, latency: _HandlerLatency | None = None) -> bool:
    finalize_payload = None
    db_started_at = time.perf_counter()
    with get_connection(settings.db_path) as conn:
        current = get_current_unanswered_question(conn, session_id)
        if current is None:
            finalized = finalize_quiz_session(conn, session_id)
            if finalized is not None:
                finalize_payload = {
                    "score": int(finalized["score"]),
                    "total_questions": int(finalized["total_questions"]),
                }
            options = []
            reading_mode = "normal"
            question_id = None
        else:
            question_id = int(current["question_id"])
            options = get_question_options(conn, question_id)
            session = get_quiz_session(conn, session_id)
            reading_mode = "normal"
            if session is not None:
                reading_mode = get_user_reading_mode(conn, int(session["user_id"]))
    if latency is not None:
        latency.add_db(db_started_at)

    if current is None:
        _set_classic_reply_state(context, None)
        if finalize_payload is None:
            await _timed_telegram_api_call(latency, message.reply_text("Не удалось завершить сессию."), api_kind="message_send")
            return False
        await _timed_telegram_api_call(
            latency,
            message.reply_text(
                build_quiz_finished_text(finalize_payload['score'], finalize_payload['total_questions']),
                reply_markup=get_main_menu_keyboard() if message.chat.type == "private" else None,
                parse_mode="HTML",
            ),
            api_kind="message_send",
        )
        return False

    if not options:
        _set_classic_reply_state(context, None)
        await _timed_telegram_api_call(
            latency,
            message.reply_text(
                "Для текущего вопроса не найдены варианты ответа. Сессия завершена.",
                reply_markup=get_main_menu_keyboard() if message.chat.type == "private" else None,
            ),
            api_kind="message_send",
        )
        return False

    render_started_at = time.perf_counter()
    message_text = build_question_text_with_options(
        order_index=int(current["order_index"]),
        total_questions=int(current["total_questions"]),
        question_text=str(current["question_text"]),
        options=options,
        reading_mode=reading_mode,
        numeric_labels=True,
        show_answer_keyboard_hint=int(current["order_index"]) == 1,
    )
    markup = build_classic_answer_reply_keyboard(options)
    if latency is not None:
        latency.add_render(render_started_at)
    _set_classic_reply_state(
        context,
        {"status": "awaiting_answer", "session_id": session_id, "question_id": question_id},
    )
    await _timed_telegram_api_call(
        latency,
        message.reply_text(message_text, reply_markup=markup, parse_mode="HTML"),
        api_kind="message_send",
    )
    return True



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


async def remove_main_menu_for_active_quiz(query, latency: _HandlerLatency | None = None) -> None:
    if query.message is None or query.message.chat.type != "private":
        return

    del latency


async def restore_main_menu_after_quiz(query) -> None:
    if query.message is None or query.message.chat.type != "private":
        return

    await query.message.reply_text(
        "Главное меню снова доступно.",
        reply_markup=get_main_menu_keyboard(),
    )


async def send_quiz_result_with_main_menu(query, text: str, latency: _HandlerLatency | None = None) -> None:
    """Single completion sink: disable stale quiz inline controls, then send final result."""
    if query.message is None:
        return

    try:
        await _timed_telegram_api_call(latency, query.edit_message_reply_markup(reply_markup=None), api_kind="message_edit")
    except Exception:
        logger.debug("Не удалось отключить inline-кнопки у предыдущего сообщения перед показом результата.")

    await _timed_telegram_api_call(latency, query.message.chat.send_message(
        text,
        reply_markup=get_main_menu_keyboard() if query.message.chat.type == "private" else None,
        parse_mode="HTML",
    ), api_kind="message_send")


async def show_finished_quiz_message(query, session_id: int, score: int, total_questions: int, latency: _HandlerLatency | None = None) -> None:
    # Reuse the single completion sink so stale inline quiz controls are always disabled first.
    del session_id
    await send_quiz_result_with_main_menu(query, build_quiz_finished_text(score, total_questions), latency=latency)


async def quiz_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(
        handler="quiz_mode_callback",
        callback_prefix="qzmode",
        telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None),
    )
    query = update.callback_query
    if query is None or query.data is None:
        latency.summary()
        return

    data = query.data
    if not data.startswith("qzmode:"):
        latency.summary()
        return
    latency.start()

    await _timed_telegram_api_call(latency, query.answer())

    if data == "qzmode:single":
        settings = context.application.bot_data["settings"]
        def _load_categories():
            with get_connection(settings.db_path) as conn:
                return get_active_categories(conn)

        categories = await _run_db_task(_load_categories)
        if not categories:
            await _timed_telegram_api_call(latency, query.edit_message_text(
                "Нет доступных категорий. Сначала загрузите вопросы в базу данных."
            ))
            latency.summary()
            return
        await _timed_telegram_api_call(latency, query.edit_message_text(
            "Выберите категорию:",
            reply_markup=build_category_keyboard(categories),
        ))
        latency.summary()
        return

    if data == "qzmode:all":
        await _timed_telegram_api_call(latency, query.edit_message_text(
            "Выберите количество вопросов:",
            reply_markup=build_question_count_keyboard("qcntall"),
        ))
        latency.summary()
        return

    if data == "qzmode:selected_mix":
        settings = context.application.bot_data["settings"]
        def _load_categories():
            with get_connection(settings.db_path) as conn:
                return get_active_categories(conn)

        categories = await _run_db_task(_load_categories)
        if not categories:
            await _timed_telegram_api_call(latency, query.edit_message_text(
                "Нет доступных категорий. Сначала загрузите вопросы в базу данных."
            ))
            latency.summary()
            return

        context.user_data["selected_mix_categories"] = set()
        await _timed_telegram_api_call(latency, query.edit_message_text(
            "Выберите темы для микса:",
            reply_markup=build_selected_mix_keyboard(categories, set()),
        ))
        latency.summary()
        return

    latency.summary()


async def send_current_question(
    query,
    settings,
    session_id: int,
    latency: _HandlerLatency | None = None,
    *,
    send_as_new_message: bool = False,
    context: ContextTypes.DEFAULT_TYPE | None = None,
) -> bool:
    finalize_payload = None
    reading_mode = "normal"
    db_started_at = time.perf_counter()
    with get_connection(settings.db_path) as conn:
        current = get_current_unanswered_question(conn, session_id)
        if current is None:
            finalized = finalize_quiz_session(conn, session_id)
            if finalized is None:
                await _timed_telegram_api_call(latency, query.edit_message_text("Не удалось завершить сессию."), api_kind="message_edit")
                return False

            _set_classic_reply_state(context, None)
            await show_finished_quiz_message(
                query,
                session_id=session_id,
                score=int(finalized["score"]),
                total_questions=int(finalized["total_questions"]),
                latency=latency,
            )
            return False

        question_id = int(current["question_id"])
        order_index = int(current["order_index"])
        total_questions = int(current["total_questions"])
        session = get_quiz_session(conn, session_id)
        if session is not None:
            reading_mode = get_user_reading_mode(conn, int(session["user_id"]))
        options = get_question_options(conn, question_id)
        if not options:
            finalized = finalize_quiz_session(conn, session_id)
            if finalized is not None:
                finalize_payload = {
                    "score": int(finalized["score"]),
                    "total_questions": int(finalized["total_questions"]),
                }

    if latency is not None:
        latency.add_db(db_started_at)

    if not options:
        if finalize_payload is None:
            await _timed_telegram_api_call(latency, query.edit_message_text("Для вопроса не найдены варианты ответа. Сессия завершена."), api_kind="message_edit")
            return False
        await send_quiz_result_with_main_menu(
            query,
            "Для текущего вопроса не найдены варианты ответа.\n"
            "Сессия завершена досрочно.\n"
            f"{build_quiz_finished_text(finalize_payload['score'], finalize_payload['total_questions'])}",
            latency=latency,
        )
        return False

    keyboard = []
    for opt in options:
        option_index = int(opt["option_index"])
        keyboard.append(
            [
                InlineKeyboardButton(
                    option_index_to_label(option_index),
                    callback_data=f"ans:{session_id}:{question_id}:{option_index}",
                )
            ]
        )

    render_started_at = time.perf_counter()
    message_text = build_question_text_with_options(
            order_index=order_index,
            total_questions=total_questions,
            question_text=str(current["question_text"]),
            options=options,
            reading_mode=reading_mode,
            numeric_labels=_classic_reply_mode_enabled(settings),
            show_answer_keyboard_hint=_classic_reply_mode_enabled(settings) and order_index == 1,
    )
    if latency is not None:
        latency.add_render(render_started_at)
    if _classic_reply_mode_enabled(settings):
        markup = build_classic_answer_reply_keyboard(options)
        _set_classic_reply_state(
            context,
            {
                "status": "awaiting_answer",
                "session_id": session_id,
                "question_id": question_id,
            },
        )
        if query.message is not None:
            try:
                await _timed_telegram_api_call(
                    latency,
                    query.edit_message_reply_markup(reply_markup=None),
                    api_kind="message_edit",
                )
            except Exception:
                logger.debug("Не удалось отключить inline-кнопки перед reply-keyboard вопросом.")
            await _timed_telegram_api_call(
                latency,
                query.message.chat.send_message(
                    message_text,
                    reply_markup=markup,
                    parse_mode="HTML",
                ),
                api_kind="message_send",
            )
            return True

    markup = InlineKeyboardMarkup(keyboard)
    if send_as_new_message and query.message is not None:
        try:
            await _timed_telegram_api_call(
                latency,
                query.edit_message_reply_markup(reply_markup=None),
                api_kind="message_edit",
            )
        except Exception:
            logger.debug("Не удалось отключить inline-кнопки перед отправкой следующего вопроса новым сообщением.")
        await _timed_telegram_api_call(
            latency,
            query.message.chat.send_message(
                message_text,
                reply_markup=markup,
                parse_mode="HTML",
            ),
            api_kind="message_send",
        )
        return True

    await _timed_telegram_api_call(
        latency,
        query.edit_message_text(
            message_text,
            reply_markup=markup,
            parse_mode="HTML",
        ),
        api_kind="message_edit",
    )
    return True


async def restart_quiz_from_finished_session(query, settings, tg_user, session_id: int) -> None:
    with get_connection(settings.db_path) as conn:
        session = get_quiz_session(conn, session_id)
        if session is None:
            await query.edit_message_text("Сессия не найдена.")
            return
        if str(session["status"]) != "finished":
            await query.edit_message_text("Эту сессию пока нельзя повторить.")
            return

        user_row = create_or_load_user(
            conn,
            telegram_user_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )
        if int(session["user_id"]) != int(user_row["id"]):
            await query.edit_message_text("Эта сессия вам не принадлежит.")
            return

        category_id = session["category_id"]
        question_limit = int(session["total_questions"])
        difficulty_filter = session["difficulty_mode"]
        selected_categories = get_selected_categories_for_session(conn, session_id)
        if selected_categories:
            question_ids = select_random_approved_question_ids_by_categories(
                conn,
                category_ids=selected_categories,
                limit=question_limit,
                difficulty_mode=difficulty_filter,
            )
            new_category_id = None
        elif category_id is None:
            question_ids = select_random_approved_question_ids_across_active_categories(
                conn,
                limit=question_limit,
                difficulty_mode=difficulty_filter,
            )
            new_category_id = None
        else:
            question_ids = select_random_approved_question_ids_by_category(
                conn,
                category_id=int(category_id),
                limit=question_limit,
                difficulty_mode=difficulty_filter,
            )
            new_category_id = int(category_id)

        if not question_ids:
            await query.edit_message_text("Не удалось подобрать вопросы для повторной попытки.")
            return

        new_session_id = start_quiz_session(
            conn,
            int(user_row["id"]),
            new_category_id,
            difficulty_mode=difficulty_filter,
        )
        if selected_categories:
            set_selected_categories_for_session(conn, new_session_id, selected_categories)
        store_session_questions(conn, new_session_id, question_ids)

    await remove_main_menu_for_active_quiz(query, latency=latency)
    await send_current_question(query, settings, new_session_id, context=context)


async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(handler="category_callback", callback_prefix="cat", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    if not data.startswith("cat:"):
        return
    latency.start()

    await _timed_telegram_api_call(latency, query.answer())

    try:
        category_id = int(data.split(":", 1)[1])
    except ValueError:
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректный выбор категории."))
        latency.summary()
        return

    api_started_at = time.perf_counter()
    await query.edit_message_text(
        "Выберите количество вопросов:",
        reply_markup=build_question_count_keyboard("qcnt", category_id),
    )
    latency.add_telegram_api(api_started_at)
    latency.summary()


async def question_count_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(handler="question_count_callback", callback_prefix="qcnt", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    if not data.startswith("qcnt:"):
        return
    latency.start()

    await _timed_telegram_api_call(latency, query.answer())

    parts = data.split(":")
    if len(parts) != 3:
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректный выбор количества вопросов."))
        latency.summary()
        return

    _, category_raw, count_raw = parts
    try:
        category_id = int(category_raw)
    except ValueError:
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректная категория."))
        latency.summary()
        return

    if count_raw != "all":
        try:
            int(count_raw)
        except ValueError:
            await _timed_telegram_api_call(latency, query.edit_message_text("Некорректное количество вопросов."))
            latency.summary()
            return

    await _timed_telegram_api_call(
        latency,
        query.edit_message_text(
            "Выберите режим сложности:",
            reply_markup=build_difficulty_keyboard("qmode", category_id, count_raw),
        ),
    )
    latency.summary()


async def difficulty_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(handler="difficulty_mode_callback", callback_prefix="qmode", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    if not data.startswith("qmode:"):
        return
    latency.start()

    await _timed_telegram_api_call(latency, query.answer())

    parts = data.split(":")
    if len(parts) != 4:
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректный выбор режима."))
        latency.summary()
        return

    _, category_raw, count_raw, mode = parts
    try:
        category_id = int(category_raw)
    except ValueError:
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректная категория."))
        latency.summary()
        return

    if mode not in {"any", "easy", "medium", "hard"}:
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректный режим сложности."))
        latency.summary()
        return

    selected_limit: int | None
    if count_raw == "all":
        selected_limit = None
    else:
        try:
            selected_limit = int(count_raw)
        except ValueError:
            await _timed_telegram_api_call(latency, query.edit_message_text("Некорректное количество вопросов."))
            latency.summary()
            return

    settings = context.application.bot_data["settings"]
    tg_user = update.effective_user
    if tg_user is None:
        await _timed_telegram_api_call(latency, query.edit_message_text("Не удалось определить пользователя."), api_kind="message_edit")
        latency.summary()
        return

    def _start_single_category_quiz():
        with get_connection(settings.db_path) as conn:
            user_row = create_or_load_user(conn, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
            difficulty_filter = None if mode == "any" else mode
            question_ids = select_random_approved_question_ids_by_category(
                conn,
                category_id=category_id,
                limit=selected_limit,
                difficulty_mode=difficulty_filter,
            )
            if not question_ids:
                return {"status": "no_questions"}
            session_id = start_quiz_session(conn, int(user_row["id"]), category_id, difficulty_mode=difficulty_filter)
            store_session_questions(conn, session_id, question_ids)
            return {"status": "ok", "session_id": session_id}

    db_started_at = time.perf_counter()
    result = await _run_db_task(_start_single_category_quiz)
    latency.add_db(db_started_at)
    if result["status"] == "no_questions":
        await _timed_telegram_api_call(latency, query.edit_message_text("В этой категории пока нет одобренных вопросов."))
        latency.summary()
        return

    await remove_main_menu_for_active_quiz(query, latency=latency)
    await send_current_question(query, settings, result["session_id"], latency=latency, context=context)
    latency.session_id = result["session_id"]
    latency.summary()


async def question_count_mix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(handler="question_count_mix_callback", callback_prefix="qcntall", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    if not data.startswith("qcntall:"):
        return
    latency.start()

    await _timed_telegram_api_call(latency, query.answer())

    _, count_raw = data.split(":", 1)
    if count_raw != "all":
        try:
            int(count_raw)
        except ValueError:
            await _timed_telegram_api_call(latency, query.edit_message_text("Некорректное количество вопросов."))
            latency.summary()
            return

    await _timed_telegram_api_call(
        latency,
        query.edit_message_text(
            "Выберите режим сложности:",
            reply_markup=build_difficulty_keyboard("qmodeall", count_raw=count_raw),
        ),
    )
    latency.summary()


async def difficulty_mode_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(handler="difficulty_mode_all_callback", callback_prefix="qmodeall", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    if not data.startswith("qmodeall:"):
        return
    latency.start()

    await _timed_telegram_api_call(latency, query.answer())

    parts = data.split(":")
    if len(parts) != 3:
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректный выбор режима."))
        latency.summary()
        return

    _, count_raw, mode = parts
    await start_mix_quiz(
        query=query,
        context=context,
        tg_user=update.effective_user,
        count_raw=count_raw,
        mode=mode,
        selected_category_ids=None,
        latency=latency,
    )
    latency.summary()


async def mix_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(handler="mix_selection_callback", callback_prefix="mixsel", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    if not data.startswith("mixsel:"):
        return
    latency.start()

    await _timed_telegram_api_call(latency, query.answer())

    settings = context.application.bot_data["settings"]

    def _load_mix_categories():
        with get_connection(settings.db_path) as conn:
            return get_active_categories(conn)

    db_started_at = time.perf_counter()
    categories = await _run_db_task(_load_mix_categories)
    latency.add_db(db_started_at)
    if not categories:
        await query.edit_message_text("Нет доступных категорий.")
        return

    selected_ids = set(context.user_data.get("selected_mix_categories", set()))
    active_category_ids = {int(row["id"]) for row in categories}
    selected_ids = {category_id for category_id in selected_ids if category_id in active_category_ids}

    if data.startswith("mixsel:toggle:"):
        try:
            category_id = int(data.split(":")[-1])
        except ValueError:
            await query.edit_message_text("Некорректная категория.")
            return
        if category_id not in active_category_ids:
            await query.edit_message_text("Категория недоступна.")
            return
        if category_id in selected_ids:
            selected_ids.remove(category_id)
        else:
            selected_ids.add(category_id)
        context.user_data["selected_mix_categories"] = selected_ids
        await query.edit_message_text(
            "Выберите темы для микса:",
            reply_markup=build_selected_mix_keyboard(categories, selected_ids),
        )
        latency.summary()
        return

    if data == "mixsel:reset":
        context.user_data["selected_mix_categories"] = set()
        await query.edit_message_text(
            "Выберите темы для микса:",
            reply_markup=build_selected_mix_keyboard(categories, set()),
        )
        latency.summary()
        return

    if data == "mixsel:done":
        if not selected_ids:
            await query.answer("Выберите хотя бы одну тему.", show_alert=True)
            return
        context.user_data["selected_mix_categories"] = selected_ids
        await query.edit_message_text(
            "Выберите количество вопросов:",
            reply_markup=build_question_count_keyboard("qcntselmix"),
        )
        latency.summary()
        return


async def question_count_selected_mix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(handler="question_count_selected_mix_callback", callback_prefix="qcntselmix", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    if not data.startswith("qcntselmix:"):
        return
    latency.start()

    await _timed_telegram_api_call(latency, query.answer())

    parts = data.split(":")
    if len(parts) != 2:
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректный выбор количества вопросов."))
        latency.summary()
        return

    _, count_raw = parts
    if count_raw != "all":
        try:
            int(count_raw)
        except ValueError:
            await _timed_telegram_api_call(latency, query.edit_message_text("Некорректное количество вопросов."))
            latency.summary()
            return

    await _timed_telegram_api_call(
        latency,
        query.edit_message_text(
            "Выберите режим сложности:",
            reply_markup=build_difficulty_keyboard("qmodeselmix", count_raw=count_raw),
        ),
    )
    latency.summary()


async def difficulty_mode_selected_mix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(handler="difficulty_mode_selected_mix_callback", callback_prefix="qmodeselmix", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    if not data.startswith("qmodeselmix:"):
        return
    latency.start()

    await _timed_telegram_api_call(latency, query.answer())

    parts = data.split(":")
    if len(parts) != 3:
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректный выбор режима."))
        return

    _, count_raw, mode = parts
    selected_ids = set(context.user_data.get("selected_mix_categories", set()))
    if not selected_ids:
        await _timed_telegram_api_call(latency, query.edit_message_text("Сначала выберите темы для микса."))
        return

    await start_mix_quiz(
        query=query,
        context=context,
        tg_user=update.effective_user,
        count_raw=count_raw,
        mode=mode,
        selected_category_ids=sorted(selected_ids),
        latency=latency,
    )
    latency.summary()


async def start_mix_quiz(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    tg_user,
    count_raw: str,
    mode: str,
    selected_category_ids: list[int] | None,
    latency: _HandlerLatency | None = None,
) -> None:
    if mode not in {"any", "easy", "medium", "hard"}:
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректный режим сложности."))
        return

    selected_limit: int | None
    if count_raw == "all":
        selected_limit = None
    else:
        try:
            selected_limit = int(count_raw)
        except ValueError:
            await _timed_telegram_api_call(latency, query.edit_message_text("Некорректное количество вопросов."))
            return

    settings = context.application.bot_data["settings"]
    if tg_user is None:
        await _timed_telegram_api_call(latency, query.edit_message_text("Не удалось определить пользователя."), api_kind="message_edit")
        return

    def _start_mix_quiz_db():
        with get_connection(settings.db_path) as conn:
            user_row = create_or_load_user(conn, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
            difficulty_filter = None if mode == "any" else mode
            filtered_selected_ids = selected_category_ids
            if selected_category_ids:
                active_ids = {int(row["id"]) for row in get_active_categories(conn)}
                filtered_selected_ids = [category_id for category_id in selected_category_ids if category_id in active_ids]
                if not filtered_selected_ids:
                    return {"status": "selected_unavailable"}
                question_ids = select_random_approved_question_ids_by_categories(
                    conn,
                    category_ids=filtered_selected_ids,
                    limit=selected_limit,
                    difficulty_mode=difficulty_filter,
                )
            else:
                question_ids = select_random_approved_question_ids_across_active_categories(
                    conn,
                    limit=selected_limit,
                    difficulty_mode=difficulty_filter,
                )
            if not question_ids:
                return {"status": "no_questions"}
            session_id = start_quiz_session(conn, int(user_row["id"]), None, difficulty_mode=difficulty_filter)
            if filtered_selected_ids:
                set_selected_categories_for_session(conn, session_id, filtered_selected_ids)
            store_session_questions(conn, session_id, question_ids)
            return {"status": "ok", "session_id": session_id}

    result = await _run_db_task(_start_mix_quiz_db)
    if result["status"] == "selected_unavailable":
        await _timed_telegram_api_call(latency, query.edit_message_text("Выбранные темы больше недоступны."))
        return
    if result["status"] == "no_questions":
        await _timed_telegram_api_call(latency, query.edit_message_text("Пока нет одобренных вопросов в активных темах."))
        return

    await remove_main_menu_for_active_quiz(query, latency=latency)
    await send_current_question(query, settings, result["session_id"], latency=latency, context=context)




def _mark_callback_processing(context: ContextTypes.DEFAULT_TYPE, key: str) -> bool:
    in_progress = context.user_data.setdefault("_callback_in_progress", set())
    if key in in_progress:
        return False
    in_progress.add(key)
    return True


def _unmark_callback_processing(context: ContextTypes.DEFAULT_TYPE, key: str) -> None:
    in_progress = context.user_data.get("_callback_in_progress")
    if isinstance(in_progress, set):
        in_progress.discard(key)

def _get_classic_reply_state(context: ContextTypes.DEFAULT_TYPE) -> dict:
    state = context.user_data.get(CLASSIC_REPLY_STATE_KEY)
    return state if isinstance(state, dict) else {}


def _load_classic_text_answer_context(settings, tg_user, state: dict) -> dict:
    if tg_user is None:
        return {"status": "missing_user"}
    if not _classic_reply_mode_enabled(settings):
        return {"status": "disabled"}
    if state.get("status") != "awaiting_answer":
        return {"status": "not_awaiting_answer"}
    try:
        session_id = int(state.get("session_id"))
        expected_question_id = int(state.get("question_id"))
    except (TypeError, ValueError):
        return {"status": "not_awaiting_answer"}

    with get_connection(settings.db_path) as conn:
        session = get_quiz_session(conn, session_id)
        if session is None or str(session["status"]) != "in_progress":
            return {"status": "session_missing", "session_id": session_id, "question_id": expected_question_id}
        user_row = create_or_load_user(conn, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
        if int(session["user_id"]) != int(user_row["id"]):
            return {"status": "forbidden", "session_id": session_id, "question_id": expected_question_id}
        current = get_current_unanswered_question(conn, session_id)
        if current is None:
            return {"status": "no_current_question", "session_id": session_id, "question_id": expected_question_id}
        question_id = int(current["question_id"])
        if question_id != expected_question_id:
            return {"status": "stale_question", "session_id": session_id, "question_id": expected_question_id}
        options = get_question_options(conn, question_id)
        return {"status": "ok", "session_id": session_id, "question_id": question_id, "options": options}


def _handle_classic_text_answer_db(settings, tg_user, *, session_id: int, question_id: int, selected_option_index: int) -> dict:
    with get_connection(settings.db_path) as conn:
        session = get_quiz_session(conn, session_id)
        if session is None or str(session["status"]) != "in_progress":
            return {"status": "session_missing"}
        user_row = create_or_load_user(conn, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
        if int(session["user_id"]) != int(user_row["id"]):
            return {"status": "forbidden"}
        current = get_current_unanswered_question(conn, session_id)
        options = get_question_options(conn, question_id)
        submission = submit_miniapp_answer_event(
            conn,
            session_id=session_id,
            actor_user_id=int(user_row["id"]),
            question_id=question_id,
            selected_option_index=selected_option_index,
        )
        if submission.status == "stale_question" and submission.expected_question_id is None:
            finalized = finalize_quiz_session(conn, session_id)
            return {"status": "stale_finished", "finalized": finalized}
        if submission.status != "accepted":
            return {"status": submission.status}
        selected_option = _find_option_by_index(options, selected_option_index)
        correct_option = next((opt for opt in options if bool(int(opt["is_correct"]))), None)
        if selected_option is None or correct_option is None:
            return {"status": "invalid_option"}
        answered_questions = get_answered_questions_count(conn, session_id)
        total_questions = int(current["total_questions"])
        is_last_question = answered_questions >= total_questions
        finalized = finalize_quiz_session(conn, session_id) if is_last_question else None
        correct_option_index = int(correct_option["option_index"])
        return {
            "status": "accepted",
            "is_correct": bool(submission.is_correct),
            "selected_option_label": numeric_answer_label_for_option(options, selected_option_index),
            "selected_option_text": str(selected_option["option_text"]),
            "correct_option_label": numeric_answer_label_for_option(options, correct_option_index),
            "correct_option_text": str(correct_option["option_text"]),
            "explanation": str(current["explanation"] or ""),
            "answered_questions": answered_questions,
            "total_questions": total_questions,
            "reading_mode": get_user_reading_mode(conn, int(user_row["id"])),
            "is_last_question": is_last_question,
            "finalized": finalized,
        }


def _load_classic_text_next_state(settings, tg_user, state: dict) -> dict:
    if tg_user is None:
        return {"status": "missing_user"}
    if not _classic_reply_mode_enabled(settings):
        return {"status": "disabled"}
    if state.get("status") != "awaiting_next":
        return {"status": "not_awaiting_next"}
    try:
        session_id = int(state.get("session_id"))
    except (TypeError, ValueError):
        return {"status": "not_awaiting_next"}
    with get_connection(settings.db_path) as conn:
        session = get_quiz_session(conn, session_id)
        if session is None:
            return {"status": "missing", "session_id": session_id}
        if str(session["status"]) == "finished":
            return {"status": "finished", "session_id": session_id, "score": int(session["score"]), "total_questions": int(session["total_questions"])}
        user_row = create_or_load_user(conn, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
        if int(session["user_id"]) != int(user_row["id"]):
            return {"status": "forbidden", "session_id": session_id}
        return {"status": "ok", "session_id": session_id}


async def classic_reply_text_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    tg_user = update.effective_user
    if message is None or message.text is None or tg_user is None:
        return
    settings = context.application.bot_data["settings"]
    if not _classic_reply_mode_enabled(settings):
        return

    started_at = time.perf_counter()
    state = _get_classic_reply_state(context)
    context_result = await _run_db_task(lambda: _load_classic_text_answer_context(settings, tg_user, state))
    session_id = context_result.get("session_id")
    question_id = context_result.get("question_id")
    if context_result["status"] != "ok":
        return

    _log_classic_text_event(
        "classic_text_answer_ingress",
        telegram_user_id=tg_user.id,
        session_id=session_id,
        question_id=question_id,
        status="received",
    )

    options = context_result["options"]
    option_position = parse_classic_reply_answer_number(message.text, len(options))
    if option_position is None:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        await message.reply_text(f"Выберите вариант числом от 1 до {len(options)}.")
        _log_classic_text_event(
            "classic_text_answer_latency",
            telegram_user_id=tg_user.id,
            session_id=session_id,
            question_id=question_id,
            elapsed_ms=elapsed_ms,
            status="invalid_input",
        )
        return

    selected_option_index = int(options[option_position]["option_index"])
    processing_key = f"answer:{session_id}:{question_id}"
    if not _mark_callback_processing(context, processing_key):
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        await message.reply_text("Ответ уже обрабатывается…")
        _log_classic_text_event(
            "classic_text_answer_latency",
            telegram_user_id=tg_user.id,
            session_id=session_id,
            question_id=question_id,
            elapsed_ms=elapsed_ms,
            status="ignored_repeated_input",
        )
        return

    latency = _HandlerLatency(handler="classic_reply_text_answer", telegram_user_id=tg_user.id, session_id=session_id)
    latency.start()
    try:
        db_started_at = time.perf_counter()
        result = await _run_db_task(
            lambda: _handle_classic_text_answer_db(
                settings,
                tg_user,
                session_id=session_id,
                question_id=question_id,
                selected_option_index=selected_option_index,
            )
        )
        latency.add_db(db_started_at)

        status = result["status"]
        if status == "accepted":
            feedback_text = build_classic_reply_feedback_text(result)
            if result["is_last_question"]:
                finalized = result["finalized"]
                _set_classic_reply_state(context, None)
                await _timed_telegram_api_call(
                    latency,
                    message.reply_text(
                        f"{feedback_text}\n\n"
                        f"{build_quiz_finished_text(int(finalized['score']), int(finalized['total_questions']))}",
                        reply_markup=get_main_menu_keyboard() if message.chat.type == "private" else None,
                        parse_mode="HTML",
                    ),
                    api_kind="message_send",
                )
            else:
                _set_classic_reply_state(context, {"status": "awaiting_next", "session_id": session_id})
                await _timed_telegram_api_call(
                    latency,
                    message.reply_text(
                        feedback_text,
                        reply_markup=build_classic_next_reply_keyboard(),
                        parse_mode="HTML",
                    ),
                    api_kind="message_send",
                )
        elif status in {"stale_question", "duplicate"}:
            _set_classic_reply_state(context, {"status": "awaiting_next", "session_id": session_id})
            await _timed_telegram_api_call(
                latency,
                message.reply_text("На этот вопрос уже дан ответ. Нажмите «Далее».", reply_markup=build_classic_next_reply_keyboard()),
                api_kind="message_send",
            )
        else:
            await _timed_telegram_api_call(latency, message.reply_text("Не удалось обработать ответ. Используйте /quiz, чтобы начать заново."), api_kind="message_send")

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        _log_classic_text_event(
            "classic_text_answer_latency",
            telegram_user_id=tg_user.id,
            session_id=session_id,
            question_id=question_id,
            elapsed_ms=elapsed_ms,
            status=status,
        )
        latency.set_status(status)
        latency.summary()
    finally:
        _unmark_callback_processing(context, processing_key)


async def classic_reply_text_next_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    tg_user = update.effective_user
    if message is None or message.text is None or tg_user is None:
        return
    settings = context.application.bot_data["settings"]
    if not _classic_reply_mode_enabled(settings) or message.text.strip().lower() != CLASSIC_REPLY_NEXT_TEXT.lower():
        return

    started_at = time.perf_counter()
    state = _get_classic_reply_state(context)
    next_state = await _run_db_task(lambda: _load_classic_text_next_state(settings, tg_user, state))
    if next_state["status"] != "ok":
        return
    session_id = int(next_state["session_id"])
    _log_classic_text_event("classic_text_next_ingress", telegram_user_id=tg_user.id, session_id=session_id, status="received")

    processing_key = f"next:{session_id}"
    if not _mark_callback_processing(context, processing_key):
        await message.reply_text("Переход уже выполняется…")
        _log_classic_text_event(
            "classic_text_next_latency",
            telegram_user_id=tg_user.id,
            session_id=session_id,
            elapsed_ms=int((time.perf_counter() - started_at) * 1000),
            status="ignored_repeated_input",
        )
        return

    latency = _HandlerLatency(handler="classic_reply_text_next", telegram_user_id=tg_user.id, session_id=session_id)
    latency.start()
    try:
        await send_current_question_to_message(message, settings, session_id, context, latency=latency)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        _log_classic_text_event(
            "classic_text_next_latency",
            telegram_user_id=tg_user.id,
            session_id=session_id,
            elapsed_ms=elapsed_ms,
            status="ok",
        )
        latency.summary()
    finally:
        _unmark_callback_processing(context, processing_key)



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


async def answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(handler="answer_callback", callback_prefix="ans", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    if not data.startswith("ans:"):
        return
    latency.session_id = _safe_callback_session_id(data, "ans")
    latency.start()

    settings = context.application.bot_data["settings"]

    parts = data.split(":")
    if len(parts) != 4:
        await _timed_telegram_api_call(latency, query.answer(cache_time=1), api_kind="callback_ack")
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректный формат ответа."), api_kind="message_edit")
        latency.summary()
        return

    try:
        _, session_id_raw, question_id_raw, selected_option_raw = parts
        session_id = int(session_id_raw)
        latency.session_id = session_id
        question_id = int(question_id_raw)
        selected_option_index = int(selected_option_raw)
    except ValueError:
        await _timed_telegram_api_call(latency, query.answer(cache_time=1), api_kind="callback_ack")
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректные данные ответа."), api_kind="message_edit")
        latency.summary()
        return

    processing_key = f"answer:{session_id}:{question_id}"
    if not _mark_callback_processing(context, processing_key):
        _mark_repeated_tap(latency)
        await _timed_telegram_api_call(latency, query.answer("Ответ уже обрабатывается…", cache_time=1), api_kind="callback_ack")
        latency.summary()
        return
    try:
        await _timed_telegram_api_call(latency, query.answer(cache_time=1), api_kind="callback_ack")
        tg_user = update.effective_user
        if tg_user is None:
            await _timed_telegram_api_call(latency, query.edit_message_text("Не удалось определить пользователя."), api_kind="message_edit")
            latency.summary()
            return

        def _handle_answer_db():
            with get_connection(settings.db_path) as conn:
                session = get_quiz_session(conn, session_id)
                if session is None or str(session["status"]) != "in_progress":
                    return {"status": "session_missing"}
                user_row = create_or_load_user(conn, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
                if int(session["user_id"]) != int(user_row["id"]):
                    return {"status": "forbidden"}
                current = get_current_unanswered_question(conn, session_id)
                submission = submit_miniapp_answer_event(
                    conn,
                    session_id=session_id,
                    actor_user_id=int(user_row["id"]),
                    question_id=question_id,
                    selected_option_index=selected_option_index,
                )
                if submission.status == "stale_question" and submission.expected_question_id is None:
                    finalized = finalize_quiz_session(conn, session_id)
                    return {"status": "stale_finished", "finalized": finalized}
                if submission.status != "accepted":
                    return {"status": submission.status}
                answered_questions = get_answered_questions_count(conn, session_id)
                total_questions = int(current["total_questions"])
                is_last_question = answered_questions >= total_questions
                finalized = finalize_quiz_session(conn, session_id) if is_last_question else None
                return {
                    "status": "accepted",
                    "is_correct": bool(submission.is_correct),
                    "explanation": str(current["explanation"] or ""),
                    "answered_questions": answered_questions,
                    "total_questions": total_questions,
                    "reading_mode": get_user_reading_mode(conn, int(user_row["id"])),
                    "is_last_question": is_last_question,
                    "finalized": finalized,
                }

        db_started_at = time.perf_counter()
        result = await _run_db_task(_handle_answer_db)
        latency.add_db(db_started_at)
        if result["status"] == "session_missing":
            await _timed_telegram_api_call(latency, query.edit_message_text("Сессия уже завершена или не найдена."), api_kind="message_edit")
            latency.summary()
            return
        if result["status"] == "forbidden":
            await _timed_telegram_api_call(latency, query.edit_message_text("Эта сессия вам не принадлежит."), api_kind="message_edit")
            latency.summary()
            return
        if result["status"] == "invalid_question":
            await _timed_telegram_api_call(latency, query.edit_message_text("Этот вопрос не относится к текущей сессии."), api_kind="message_edit")
            latency.summary()
            return
        if result["status"] == "stale_question":
            _mark_stale_callback(latency)
            await _timed_telegram_api_call(latency, query.edit_message_text("Этот вопрос уже неактуален. Нажмите «Дальше»."), api_kind="message_edit")
            latency.summary()
            return
        if result["status"] == "stale_finished":
            finalized = result["finalized"]
            if finalized is None:
                await _timed_telegram_api_call(latency, query.edit_message_text("Не удалось завершить сессию."), api_kind="message_edit")
                latency.summary()
                return
            await show_finished_quiz_message(query, session_id=session_id, score=int(finalized["score"]), total_questions=int(finalized["total_questions"]), latency=latency)
            latency.summary()
            return
        if result["status"] == "invalid_option":
            await _timed_telegram_api_call(latency, query.edit_message_text("Выбран некорректный вариант ответа."), api_kind="message_edit")
            latency.summary()
            return
        if result["status"] == "duplicate":
            _mark_repeated_tap(latency)
            await _timed_telegram_api_call(latency, query.edit_message_text("На этот вопрос уже дан ответ."), api_kind="message_edit")
            latency.summary()
            return
        if result["status"] != "accepted":
            await _timed_telegram_api_call(latency, query.edit_message_text("Не удалось обработать ответ. Обновите состояние викторины."), api_kind="message_edit")
            latency.summary()
            return

        is_correct = result["is_correct"]
        result_line = "<b>Верно ✅</b>" if is_correct else "<b>Неверно ❌</b>"
        rendered_explanation = render_reading_mode_text(result["explanation"], result["reading_mode"])

        if result["is_last_question"]:
            finalized = result["finalized"]
            message = (
                f"{result_line}\n\n"
                f"<b>Пояснение:</b> {rendered_explanation}\n\n"
                f"{build_quiz_finished_text(int(finalized['score']), int(finalized['total_questions']))}"
            )
            await send_quiz_result_with_main_menu(query, message, latency=latency)
            latency.summary()
            return

        next_number = result["answered_questions"] + 1
        message = (
            f"{result_line}\n\n"
            f"<b>Пояснение:</b> {rendered_explanation}\n\n"
            f"<b>Прогресс:</b> {result['answered_questions']} из {result['total_questions']} отвечено"
        )
        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"Дальше → {next_number}/{result['total_questions']}", callback_data=f"next:{session_id}")]]
        )
        await _timed_telegram_api_call(latency, query.edit_message_text(message, reply_markup=markup, parse_mode="HTML"), api_kind="message_edit")
        latency.summary()
    finally:
        _unmark_callback_processing(context, processing_key)


async def next_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = _HandlerLatency(handler="next_callback", callback_prefix="next", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    query = update.callback_query
    if query is None or query.data is None:
        return

    data = query.data
    if not data.startswith("next:"):
        return
    latency.session_id = _safe_callback_session_id(data, "next")
    latency.start()

    settings = context.application.bot_data["settings"]

    try:
        session_id = int(data.split(":", 1)[1])
        latency.session_id = session_id
    except ValueError:
        await _timed_telegram_api_call(latency, query.answer(cache_time=1), api_kind="callback_ack")
        await _timed_telegram_api_call(latency, query.edit_message_text("Некорректные данные кнопки «Дальше»."), api_kind="message_edit")
        latency.summary()
        return

    processing_key = f"next:{session_id}"
    if not _mark_callback_processing(context, processing_key):
        _mark_repeated_tap(latency)
        await _timed_telegram_api_call(latency, query.answer("Переход уже выполняется…", cache_time=1), api_kind="callback_ack")
        latency.summary()
        return

    try:
        await _timed_telegram_api_call(latency, query.answer(cache_time=1), api_kind="callback_ack")
        tg_user = update.effective_user
        if tg_user is None:
            await _timed_telegram_api_call(latency, query.edit_message_text("Не удалось определить пользователя."), api_kind="message_edit")
            latency.summary()
            return

        def _load_next_state():
            with get_connection(settings.db_path) as conn:
                session = get_quiz_session(conn, session_id)
                if session is None:
                    return {"status": "missing"}
                if str(session["status"]) == "finished":
                    return {"status": "finished", "score": int(session["score"]), "total_questions": int(session["total_questions"])}
                user_row = create_or_load_user(conn, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
                if int(session["user_id"]) != int(user_row["id"]):
                    return {"status": "forbidden"}
                return {"status": "ok"}

        db_started_at = time.perf_counter()
        next_state = await _run_db_task(_load_next_state)
        latency.add_db(db_started_at)
        if next_state["status"] == "missing":
            await _timed_telegram_api_call(latency, query.edit_message_text("Сессия не найдена."), api_kind="message_edit")
            latency.summary()
            return
        if next_state["status"] == "finished":
            await show_finished_quiz_message(
                query,
                session_id=session_id,
                score=next_state["score"],
                total_questions=next_state["total_questions"],
                latency=latency,
            )
            latency.summary()
            return
        if next_state["status"] == "forbidden":
            await _timed_telegram_api_call(latency, query.edit_message_text("Эта сессия вам не принадлежит."), api_kind="message_edit")
            latency.summary()
            return

        await send_current_question(
            query,
            settings,
            session_id,
            latency=latency,
            send_as_new_message=getattr(settings, "classic_quiz_send_next_as_new_message", False),
            context=context,
        )
        latency.summary()
    finally:
        _unmark_callback_processing(context, processing_key)


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
