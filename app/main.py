from __future__ import annotations

from html import escape
import logging
import re

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
    filters,
)

from app.config import load_settings
from app.db import (
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
    init_db_connection,
    is_question_in_session,
    save_quiz_answer,
    select_random_approved_question_ids_across_active_categories,
    select_random_approved_question_ids_by_category,
    select_random_approved_question_ids_by_categories,
    set_user_reading_mode,
    set_selected_categories_for_session,
    start_quiz_session,
    store_session_questions,
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
    ("easy", "Только easy"),
    ("medium", "Только medium"),
    ("hard", "Только hard"),
)

HELP_TEXT = (
    "Доступные команды:\n"
    "/start — приветствие\n"
    "/help — список команд\n"
    "/ping — проверка доступности\n"
    "/quiz — запустить викторину"
)
READING_MODE_BUTTON_TEXT = "👁 Режим чтения"
HIDE_MENU_BUTTON_TEXT = "🙈 Скрыть меню"
READING_MODE_LABELS = {
    "normal": "Обычный",
    "bionic": "Бионическое чтение",
}
WORD_RE = re.compile(r"([0-9A-Za-zА-Яа-яЁё]+|[^0-9A-Za-zА-Яа-яЁё]+)")


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
    return "<b>Викторина завершена</b>\n" f"<b>Результат:</b> {score} из {total_questions}"


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


def build_reading_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Обычный", callback_data="readingmode:set:normal")],
            [InlineKeyboardButton("Бионическое чтение", callback_data="readingmode:set:bionic")],
        ]
    )


def build_question_text_with_options(
    order_index: int,
    total_questions: int,
    question_text: str,
    options,
    reading_mode: str,
) -> str:
    formatted_options = "\n".join(
        f"{option_index_to_label(int(opt['option_index']))}. "
        f"{render_reading_mode_text(str(opt['option_text']), reading_mode)}"
        for opt in options
    )
    return (
        f"<b>Вопрос {order_index} из {total_questions}</b>\n\n"
        f"{render_reading_mode_text(question_text, reading_mode)}\n\n"
        f"{formatted_options}"
    )


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Запуск бота"),
            BotCommand("help", "Список команд"),
            BotCommand("ping", "Проверка доступности"),
            BotCommand("quiz", "Начать викторину"),
        ]
    )


async def safe_reply(update: Update, text: str) -> None:
    if update.message:
        await update.message.reply_text(text)


def is_private_chat(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type == "private")


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("🎯 Начать викторину")],
            [KeyboardButton("ℹ️ Помощь")],
            [KeyboardButton(READING_MODE_BUTTON_TEXT)],
            [KeyboardButton(HIDE_MENU_BUTTON_TEXT)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    first_entry = not context.user_data.get("start_seen", False)
    context.user_data["start_seen"] = True
    message_text = (
        "Привет! Я учебный бот-викторина по психологии. Используйте /help для списка команд."
        if first_entry
        else "Меню показано."
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
    with get_connection(settings.db_path) as conn:
        user_row = create_or_load_user(
            conn,
            telegram_user_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )
        current_mode = get_user_reading_mode(conn, int(user_row["id"]))

    await update.message.reply_text(
        f"Текущий режим чтения: {READING_MODE_LABELS.get(current_mode, READING_MODE_LABELS['normal'])}",
        reply_markup=build_reading_mode_keyboard(),
    )



async def hide_menu_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    try:
        removal_message = await message.reply_text(
            text="\u2060",
            reply_markup=ReplyKeyboardRemove(),
        )
        await removal_message.delete()
    except Exception:
        logger.exception("Не удалось скрыть меню для сообщения %s", message.message_id)

    try:
        await message.delete()
    except Exception:
        logger.debug("Не удалось удалить сообщение-триггер скрытия меню %s", message.message_id)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await safe_reply(update, HELP_TEXT)


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await safe_reply(update, "pong")


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = context.application.bot_data["settings"]

    with get_connection(settings.db_path) as conn:
        categories = get_active_categories(conn)

    if not categories:
        await safe_reply(update, "Нет доступных категорий. Сначала загрузите вопросы в базу данных.")
        return

    if update.message:
        context.user_data["selected_mix_categories"] = set()
        await update.message.reply_text(
            "Выберите режим викторины:",
            reply_markup=build_quiz_mode_keyboard(),
        )


async def remove_main_menu_for_active_quiz(query) -> None:
    if query.message is None or query.message.chat.type != "private":
        return

    removal_message = await query.message.reply_text(
        "\u2060",
        reply_markup=ReplyKeyboardRemove(),
    )
    await removal_message.delete()


async def restore_main_menu_after_quiz(query) -> None:
    if query.message is None or query.message.chat.type != "private":
        return

    await query.message.reply_text(
        "Главное меню снова доступно.",
        reply_markup=get_main_menu_keyboard(),
    )


async def send_quiz_result_with_main_menu(query, text: str) -> None:
    if query.message is None:
        return

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        logger.debug("Не удалось отключить inline-кнопки у предыдущего сообщения перед показом результата.")

    await query.message.chat.send_message(
        text,
        reply_markup=get_main_menu_keyboard() if query.message.chat.type == "private" else None,
        parse_mode="HTML",
    )


async def show_finished_quiz_message(query, session_id: int, score: int, total_questions: int) -> None:
    del session_id
    await send_quiz_result_with_main_menu(query, build_quiz_finished_text(score, total_questions))


async def quiz_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    data = query.data
    if data == "qzmode:single":
        settings = context.application.bot_data["settings"]
        with get_connection(settings.db_path) as conn:
            categories = get_active_categories(conn)
        if not categories:
            await query.edit_message_text(
                "Нет доступных категорий. Сначала загрузите вопросы в базу данных."
            )
            return
        await query.edit_message_text(
            "Выберите категорию:",
            reply_markup=build_category_keyboard(categories),
        )
        return

    if data == "qzmode:all":
        await query.edit_message_text(
            "Выберите количество вопросов:",
            reply_markup=build_question_count_keyboard("qcntall"),
        )
        return

    if data == "qzmode:selected_mix":
        settings = context.application.bot_data["settings"]
        with get_connection(settings.db_path) as conn:
            categories = get_active_categories(conn)
        if not categories:
            await query.edit_message_text(
                "Нет доступных категорий. Сначала загрузите вопросы в базу данных."
            )
            return

        context.user_data["selected_mix_categories"] = set()
        await query.edit_message_text(
            "Выберите темы для микса:",
            reply_markup=build_selected_mix_keyboard(categories, set()),
        )


async def send_current_question(query, settings, session_id: int) -> bool:
    finalize_payload = None
    reading_mode = "normal"
    with get_connection(settings.db_path) as conn:
        current = get_current_unanswered_question(conn, session_id)
        if current is None:
            finalized = finalize_quiz_session(conn, session_id)
            if finalized is None:
                await query.edit_message_text("Не удалось завершить сессию.")
                return False

            await show_finished_quiz_message(
                query,
                session_id=session_id,
                score=int(finalized["score"]),
                total_questions=int(finalized["total_questions"]),
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

    if not options:
        if finalize_payload is None:
            await query.edit_message_text("Для вопроса не найдены варианты ответа. Сессия завершена.")
            return False
        await send_quiz_result_with_main_menu(
            query,
            "Для текущего вопроса не найдены варианты ответа.\n"
            "Сессия завершена досрочно.\n"
            f"{build_quiz_finished_text(finalize_payload['score'], finalize_payload['total_questions'])}\n\n"
            "Чтобы запустить новую викторину, используйте /quiz.",
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

    await query.edit_message_text(
        build_question_text_with_options(
            order_index=order_index,
            total_questions=total_questions,
            question_text=str(current["question_text"]),
            options=options,
            reading_mode=reading_mode,
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
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

    await remove_main_menu_for_active_quiz(query)
    await send_current_question(query, settings, new_session_id)


async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    data = query.data
    if not data.startswith("cat:"):
        return

    try:
        category_id = int(data.split(":", 1)[1])
    except ValueError:
        await query.edit_message_text("Некорректный выбор категории.")
        return

    await query.edit_message_text(
        "Выберите количество вопросов:",
        reply_markup=build_question_count_keyboard("qcnt", category_id),
    )


async def question_count_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    data = query.data
    if not data.startswith("qcnt:"):
        return

    parts = data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("Некорректный выбор количества вопросов.")
        return

    _, category_raw, count_raw = parts
    try:
        category_id = int(category_raw)
    except ValueError:
        await query.edit_message_text("Некорректная категория.")
        return

    if count_raw != "all":
        try:
            int(count_raw)
        except ValueError:
            await query.edit_message_text("Некорректное количество вопросов.")
            return

    await query.edit_message_text(
        "Выберите режим сложности:",
        reply_markup=build_difficulty_keyboard("qmode", category_id, count_raw),
    )


async def difficulty_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    data = query.data
    if not data.startswith("qmode:"):
        return

    parts = data.split(":")
    if len(parts) != 4:
        await query.edit_message_text("Некорректный выбор режима.")
        return

    _, category_raw, count_raw, mode = parts
    try:
        category_id = int(category_raw)
    except ValueError:
        await query.edit_message_text("Некорректная категория.")
        return

    if mode not in {"any", "easy", "medium", "hard"}:
        await query.edit_message_text("Некорректный режим сложности.")
        return

    selected_limit: int | None
    if count_raw == "all":
        selected_limit = None
    else:
        try:
            selected_limit = int(count_raw)
        except ValueError:
            await query.edit_message_text("Некорректное количество вопросов.")
            return

    settings = context.application.bot_data["settings"]
    tg_user = update.effective_user
    if tg_user is None:
        await query.edit_message_text("Не удалось определить пользователя.")
        return

    with get_connection(settings.db_path) as conn:
        user_row = create_or_load_user(
            conn,
            telegram_user_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )

        difficulty_filter = None if mode == "any" else mode
        question_ids = select_random_approved_question_ids_by_category(
            conn,
            category_id=category_id,
            limit=selected_limit,
            difficulty_mode=difficulty_filter,
        )
        if not question_ids:
            await query.edit_message_text("В этой категории пока нет одобренных вопросов.")
            return

        session_id = start_quiz_session(
            conn,
            int(user_row["id"]),
            category_id,
            difficulty_mode=difficulty_filter,
        )
        store_session_questions(conn, session_id, question_ids)

    await remove_main_menu_for_active_quiz(query)
    await send_current_question(query, settings, session_id)


async def question_count_mix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    data = query.data
    if not data.startswith("qcntall:"):
        return

    _, count_raw = data.split(":", 1)
    if count_raw != "all":
        try:
            int(count_raw)
        except ValueError:
            await query.edit_message_text("Некорректное количество вопросов.")
            return

    await query.edit_message_text(
        "Выберите режим сложности:",
        reply_markup=build_difficulty_keyboard("qmodeall", count_raw=count_raw),
    )


async def difficulty_mode_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    data = query.data
    if not data.startswith("qmodeall:"):
        return

    parts = data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("Некорректный выбор режима.")
        return

    _, count_raw, mode = parts
    await start_mix_quiz(
        query=query,
        context=context,
        tg_user=update.effective_user,
        count_raw=count_raw,
        mode=mode,
        selected_category_ids=None,
    )


async def mix_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()
    data = query.data
    if not data.startswith("mixsel:"):
        return

    settings = context.application.bot_data["settings"]
    with get_connection(settings.db_path) as conn:
        categories = get_active_categories(conn)
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
        return

    if data == "mixsel:reset":
        context.user_data["selected_mix_categories"] = set()
        await query.edit_message_text(
            "Выберите темы для микса:",
            reply_markup=build_selected_mix_keyboard(categories, set()),
        )
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
        return


async def question_count_selected_mix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()
    data = query.data
    if not data.startswith("qcntselmix:"):
        return

    parts = data.split(":")
    if len(parts) != 2:
        await query.edit_message_text("Некорректный выбор количества вопросов.")
        return

    _, count_raw = parts
    if count_raw != "all":
        try:
            int(count_raw)
        except ValueError:
            await query.edit_message_text("Некорректное количество вопросов.")
            return

    await query.edit_message_text(
        "Выберите режим сложности:",
        reply_markup=build_difficulty_keyboard("qmodeselmix", count_raw=count_raw),
    )


async def difficulty_mode_selected_mix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()
    data = query.data
    if not data.startswith("qmodeselmix:"):
        return

    parts = data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("Некорректный выбор режима.")
        return

    _, count_raw, mode = parts
    selected_ids = set(context.user_data.get("selected_mix_categories", set()))
    if not selected_ids:
        await query.edit_message_text("Сначала выберите темы для микса.")
        return

    await start_mix_quiz(
        query=query,
        context=context,
        tg_user=update.effective_user,
        count_raw=count_raw,
        mode=mode,
        selected_category_ids=sorted(selected_ids),
    )


async def start_mix_quiz(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    tg_user,
    count_raw: str,
    mode: str,
    selected_category_ids: list[int] | None,
) -> None:
    if mode not in {"any", "easy", "medium", "hard"}:
        await query.edit_message_text("Некорректный режим сложности.")
        return

    selected_limit: int | None
    if count_raw == "all":
        selected_limit = None
    else:
        try:
            selected_limit = int(count_raw)
        except ValueError:
            await query.edit_message_text("Некорректное количество вопросов.")
            return

    settings = context.application.bot_data["settings"]
    if tg_user is None:
        await query.edit_message_text("Не удалось определить пользователя.")
        return

    with get_connection(settings.db_path) as conn:
        user_row = create_or_load_user(
            conn,
            telegram_user_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )

        difficulty_filter = None if mode == "any" else mode
        if selected_category_ids:
            active_ids = {int(row["id"]) for row in get_active_categories(conn)}
            filtered_selected_ids = [category_id for category_id in selected_category_ids if category_id in active_ids]
            if not filtered_selected_ids:
                await query.edit_message_text("Выбранные темы больше недоступны.")
                return
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
            await query.edit_message_text("Пока нет одобренных вопросов в активных темах.")
            return

        session_id = start_quiz_session(
            conn,
            int(user_row["id"]),
            None,
            difficulty_mode=difficulty_filter,
        )
        if selected_category_ids:
            set_selected_categories_for_session(conn, session_id, selected_category_ids)
        store_session_questions(conn, session_id, question_ids)

    await remove_main_menu_for_active_quiz(query)
    await send_current_question(query, settings, session_id)


async def answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    data = query.data
    if not data.startswith("ans:"):
        return

    settings = context.application.bot_data["settings"]

    parts = data.split(":")
    if len(parts) != 4:
        await query.edit_message_text("Некорректный формат ответа.")
        return

    try:
        _, session_id_raw, question_id_raw, selected_option_raw = parts
        session_id = int(session_id_raw)
        question_id = int(question_id_raw)
        selected_option_index = int(selected_option_raw)
    except ValueError:
        await query.edit_message_text("Некорректные данные ответа.")
        return

    with get_connection(settings.db_path) as conn:
        session = get_quiz_session(conn, session_id)
        if session is None or str(session["status"]) != "in_progress":
            await query.edit_message_text("Сессия уже завершена или не найдена.")
            return

        tg_user = update.effective_user
        if tg_user is None:
            await query.edit_message_text("Не удалось определить пользователя.")
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

        if not is_question_in_session(conn, session_id, question_id):
            await query.edit_message_text("Этот вопрос не относится к текущей сессии.")
            return

        current = get_current_unanswered_question(conn, session_id)
        if current is None:
            finalized = finalize_quiz_session(conn, session_id)
            if finalized is None:
                await query.edit_message_text("Не удалось завершить сессию.")
                return
            await show_finished_quiz_message(
                query,
                session_id=session_id,
                score=int(finalized["score"]),
                total_questions=int(finalized["total_questions"]),
            )
            return

        if int(current["question_id"]) != question_id:
            await query.edit_message_text("Этот вопрос уже неактуален. Нажмите «Дальше».")
            return

        answer = save_quiz_answer(conn, session_id, question_id, selected_option_index)
        if int(answer["already_answered"]) == 1:
            await query.edit_message_text("На этот вопрос уже дан ответ.")
            return

        explanation = str(current["explanation"] or "")
        total_questions = int(current["total_questions"])
        answered_questions = get_answered_questions_count(conn, session_id)
        reading_mode = get_user_reading_mode(conn, int(user_row["id"]))

        is_last_question = answered_questions >= total_questions
        if is_last_question:
            finalized = finalize_quiz_session(conn, session_id)
            if finalized is None:
                await query.edit_message_text("Не удалось завершить сессию.")
                return

    is_correct = int(answer["is_correct"]) == 1
    result_line = "<b>Верно ✅</b>" if is_correct else "<b>Неверно ❌</b>"
    rendered_explanation = render_reading_mode_text(explanation, reading_mode)

    if is_last_question:
        message = (
            f"{result_line}\n\n"
            f"<b>Пояснение:</b> {rendered_explanation}\n\n"
            f"{build_quiz_finished_text(int(finalized['score']), int(finalized['total_questions']))}\n\n"
            "Чтобы запустить новую викторину, используйте /quiz."
        )
        await send_quiz_result_with_main_menu(query, message)
        return

    next_number = answered_questions + 1
    message = (
        f"{result_line}\n\n"
        f"<b>Пояснение:</b> {rendered_explanation}\n\n"
        f"<b>Прогресс:</b> {answered_questions} из {total_questions} отвечено"
    )
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"Дальше → {next_number}/{total_questions}", callback_data=f"next:{session_id}")]]
    )
    await query.edit_message_text(message, reply_markup=markup, parse_mode="HTML")


async def next_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    data = query.data
    if not data.startswith("next:"):
        return

    settings = context.application.bot_data["settings"]

    try:
        session_id = int(data.split(":", 1)[1])
    except ValueError:
        await query.edit_message_text("Некорректные данные кнопки «Дальше».")
        return

    tg_user = update.effective_user
    if tg_user is None:
        await query.edit_message_text("Не удалось определить пользователя.")
        return

    with get_connection(settings.db_path) as conn:
        session = get_quiz_session(conn, session_id)
        if session is None:
            await query.edit_message_text("Сессия не найдена.")
            return
        if str(session["status"]) == "finished":
            await show_finished_quiz_message(
                query,
                session_id=session_id,
                score=int(session["score"]),
                total_questions=int(session["total_questions"]),
            )
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

    await send_current_question(query, settings, session_id)


async def reading_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    data = query.data
    if data == "readingmode:menu":
        tg_user = update.effective_user
        if tg_user is None:
            await query.edit_message_text("Не удалось определить пользователя.")
            return

        settings = context.application.bot_data["settings"]
        with get_connection(settings.db_path) as conn:
            user_row = create_or_load_user(
                conn,
                telegram_user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
            current_mode = get_user_reading_mode(conn, int(user_row["id"]))

        await query.edit_message_text(
            f"Текущий режим чтения: {READING_MODE_LABELS.get(current_mode, READING_MODE_LABELS['normal'])}",
            reply_markup=build_reading_mode_keyboard(),
        )
        return

    if not data.startswith("readingmode:set:"):
        return

    mode = data.split(":")[-1]
    if mode not in READING_MODE_LABELS:
        await query.edit_message_text("Некорректный режим чтения.")
        return

    tg_user = update.effective_user
    if tg_user is None:
        await query.edit_message_text("Не удалось определить пользователя.")
        return

    settings = context.application.bot_data["settings"]
    with get_connection(settings.db_path) as conn:
        user_row = create_or_load_user(
            conn,
            telegram_user_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )
        saved_mode = set_user_reading_mode(conn, int(user_row["id"]), mode)

    await query.edit_message_text(
        f"Режим чтения обновлен: {READING_MODE_LABELS[saved_mode]}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Изменить режим", callback_data="readingmode:menu")]]
        ),
    )


def configure_logging(log_level: str) -> None:
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)

    logger.info("Запуск приложения в окружении '%s'", settings.app_env)
    logger.info("Проверка подключения к SQLite: %s", settings.db_path)
    init_db_connection(settings.db_path)
    logger.info("Подключение к SQLite успешно")

    application = Application.builder().token(settings.bot_token).post_init(post_init).build()
    application.bot_data["settings"] = settings

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.Regex(r"^🎯 Начать викторину$"),
            start_quiz_button_handler,
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
            filters.ChatType.PRIVATE & filters.Regex(r"^👁 Режим чтения$"),
            reading_mode_button_handler,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.Regex(r"^🙈 Скрыть меню$"),
            hide_menu_button_handler,
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            reading_mode_callback,
            pattern=r"^readingmode:(menu|set:(normal|bionic))$",
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

    logger.info("Бот запущен (long polling)")
    application.run_polling()


if __name__ == "__main__":
    main()
