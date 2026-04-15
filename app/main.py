from __future__ import annotations

from html import escape
import logging

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
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
    finalize_quiz_session,
    get_active_categories,
    get_answered_questions_count,
    get_connection,
    get_current_unanswered_question,
    get_question_options,
    get_quiz_session,
    init_db_connection,
    is_question_in_session,
    save_quiz_answer,
    select_random_approved_question_ids_across_active_categories,
    select_random_approved_question_ids_by_category,
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


def build_post_quiz_keyboard(session_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔁 Пройти еще раз", callback_data=f"postquiz:repeat:{session_id}")],
            [InlineKeyboardButton("🎯 Новая викторина", callback_data="postquiz:new")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="postquiz:help")],
        ]
    )


def build_quiz_finished_text(score: int, total_questions: int) -> str:
    return "<b>Викторина завершена</b>\n" f"<b>Результат:</b> {score} из {total_questions}"


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
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.message:
        await update.message.reply_text(
            "Привет! Я учебный бот-викторина по психологии. Используйте /help для списка команд.",
            reply_markup=get_main_menu_keyboard() if is_private_chat(update) else None,
        )


async def start_quiz_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await quiz_command(update, context)


async def help_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await help_command(update, context)


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
        await update.message.reply_text(
            "Выберите режим викторины:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Одна тема", callback_data="qzmode:single")],
                    [InlineKeyboardButton("🎲 Микс тем", callback_data="qzmode:mix")],
                ]
            ),
        )


async def show_finished_quiz_message(query, session_id: int, score: int, total_questions: int) -> None:
    await query.edit_message_text(
        build_quiz_finished_text(score, total_questions),
        reply_markup=build_post_quiz_keyboard(session_id),
        parse_mode="HTML",
    )


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

    if data == "qzmode:mix":
        await query.edit_message_text(
            "Выберите количество вопросов:",
            reply_markup=build_question_count_keyboard("qcntmix"),
        )


async def send_current_question(query, settings, session_id: int) -> bool:
    finalize_payload = None
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
        await query.edit_message_text(
            "Для текущего вопроса не найдены варианты ответа.\n"
            "Сессия завершена досрочно.\n"
            f"{build_quiz_finished_text(finalize_payload['score'], finalize_payload['total_questions'])}",
            reply_markup=build_post_quiz_keyboard(session_id),
            parse_mode="HTML",
        )
        return False

    keyboard = []
    for opt in options:
        option_index = int(opt["option_index"])
        keyboard.append(
            [
                InlineKeyboardButton(
                    str(opt["option_text"]),
                    callback_data=f"ans:{session_id}:{question_id}:{option_index}",
                )
            ]
        )

    question_text = escape(str(current["question_text"]))
    await query.edit_message_text(
        f"<b>Вопрос {order_index} из {total_questions}</b>\n\n{question_text}",
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
        if category_id is None:
            question_ids = select_random_approved_question_ids_across_active_categories(
                conn,
                limit=question_limit,
                difficulty_mode=None,
            )
        else:
            question_ids = select_random_approved_question_ids_by_category(
                conn,
                category_id=int(category_id),
                limit=question_limit,
                difficulty_mode=None,
            )

        if not question_ids:
            await query.edit_message_text("Не удалось подобрать вопросы для повторной попытки.")
            return

        new_session_id = start_quiz_session(conn, int(user_row["id"]), category_id)
        store_session_questions(conn, new_session_id, question_ids)

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

        session_id = start_quiz_session(conn, int(user_row["id"]), category_id)
        store_session_questions(conn, session_id, question_ids)

    await send_current_question(query, settings, session_id)


async def question_count_mix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    data = query.data
    if not data.startswith("qcntmix:"):
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
        reply_markup=build_difficulty_keyboard("qmodemix", count_raw=count_raw),
    )


async def difficulty_mode_mix_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    data = query.data
    if not data.startswith("qmodemix:"):
        return

    parts = data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("Некорректный выбор режима.")
        return

    _, count_raw, mode = parts
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
        question_ids = select_random_approved_question_ids_across_active_categories(
            conn,
            limit=selected_limit,
            difficulty_mode=difficulty_filter,
        )
        if not question_ids:
            await query.edit_message_text("Пока нет одобренных вопросов в активных темах.")
            return

        session_id = start_quiz_session(conn, int(user_row["id"]), None)
        store_session_questions(conn, session_id, question_ids)

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

        is_last_question = answered_questions >= total_questions
        if is_last_question:
            finalized = finalize_quiz_session(conn, session_id)
            if finalized is None:
                await query.edit_message_text("Не удалось завершить сессию.")
                return

    is_correct = int(answer["is_correct"]) == 1
    result_line = "<b>Верно ✅</b>" if is_correct else "<b>Неверно ❌</b>"
    escaped_explanation = escape(explanation)

    if is_last_question:
        message = (
            f"{result_line}\n\n"
            f"<b>Пояснение:</b> {escaped_explanation}\n\n"
            f"{build_quiz_finished_text(int(finalized['score']), int(finalized['total_questions']))}"
        )
        await query.edit_message_text(
            message,
            reply_markup=build_post_quiz_keyboard(session_id),
            parse_mode="HTML",
        )
        return

    next_number = answered_questions + 1
    message = (
        f"{result_line}\n\n"
        f"<b>Пояснение:</b> {escaped_explanation}\n\n"
        f"<b>Вопрос {next_number} из {total_questions}</b>"
    )
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Дальше", callback_data=f"next:{session_id}")]]
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


async def post_quiz_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()
    data = query.data

    if data == "postquiz:new":
        await query.edit_message_text(
            "Выберите режим викторины:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Одна тема", callback_data="qzmode:single")],
                    [InlineKeyboardButton("🎲 Микс тем", callback_data="qzmode:mix")],
                ]
            ),
        )
        return

    if data == "postquiz:help":
        await query.edit_message_text(HELP_TEXT)
        return

    if not data.startswith("postquiz:repeat:"):
        return

    try:
        session_id = int(data.split(":")[-1])
    except ValueError:
        await query.edit_message_text("Некорректная сессия для повтора.")
        return

    tg_user = update.effective_user
    if tg_user is None:
        await query.edit_message_text("Не удалось определить пользователя.")
        return

    settings = context.application.bot_data["settings"]
    await restart_quiz_from_finished_session(query, settings, tg_user, session_id)


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
    application.add_handler(CallbackQueryHandler(quiz_mode_callback, pattern=r"^qzmode:(single|mix)$"))
    application.add_handler(CallbackQueryHandler(category_callback, pattern=r"^cat:\d+$"))
    application.add_handler(CallbackQueryHandler(question_count_callback, pattern=r"^qcnt:\d+:(5|10|15|all)$"))
    application.add_handler(
        CallbackQueryHandler(
            difficulty_mode_callback,
            pattern=r"^qmode:\d+:(5|10|15|all):(any|easy|medium|hard)$",
        )
    )
    application.add_handler(
        CallbackQueryHandler(question_count_mix_callback, pattern=r"^qcntmix:(5|10|15|all)$")
    )
    application.add_handler(
        CallbackQueryHandler(
            difficulty_mode_mix_callback,
            pattern=r"^qmodemix:(5|10|15|all):(any|easy|medium|hard)$",
        )
    )
    application.add_handler(CallbackQueryHandler(answer_callback, pattern=r"^ans:\d+:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(next_callback, pattern=r"^next:\d+$"))
    application.add_handler(
        CallbackQueryHandler(
            post_quiz_action_callback,
            pattern=r"^postquiz:(new|help|repeat:\d+)$",
        )
    )

    logger.info("Бот запущен (long polling)")
    application.run_polling()


if __name__ == "__main__":
    main()
