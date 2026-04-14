from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app.config import load_settings
from app.db import (
    create_or_load_user,
    finalize_quiz_session,
    get_active_categories,
    get_connection,
    get_question_options,
    get_quiz_session,
    get_random_approved_question_by_category,
    init_db_connection,
    save_quiz_answer,
    start_quiz_session,
)


logger = logging.getLogger(__name__)


async def safe_reply(update: Update, text: str) -> None:
    if update.message:
        await update.message.reply_text(text)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await safe_reply(
        update,
        "Привет! Я учебный бот-викторина по психологии. Используйте /help для списка команд.",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await safe_reply(
        update,
        "Доступные команды:\n"
        "/start — приветствие\n"
        "/help — список команд\n"
        "/ping — проверка доступности\n"
        "/quiz — запустить викторину",
    )


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

    keyboard = [
        [InlineKeyboardButton(str(row["name"]), callback_data=f"cat:{int(row['id'])}")]
        for row in categories
    ]
    markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text("Выберите категорию:", reply_markup=markup)


async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    data = query.data
    if not data.startswith("cat:"):
        return

    settings = context.application.bot_data["settings"]

    try:
        category_id = int(data.split(":", 1)[1])
    except ValueError:
        await query.edit_message_text("Некорректный выбор категории.")
        return

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
        session_id = start_quiz_session(conn, int(user_row["id"]), category_id)
        question = get_random_approved_question_by_category(conn, category_id)

        if question is None:
            conn.execute("DELETE FROM quiz_sessions WHERE id = ?", (session_id,))
            await query.edit_message_text("В этой категории пока нет одобренных вопросов.")
            return

        options = get_question_options(conn, int(question["id"]))

    if not options:
        with get_connection(settings.db_path) as conn:
            conn.execute("DELETE FROM quiz_sessions WHERE id = ?", (session_id,))
        await query.edit_message_text("Для вопроса не найдены варианты ответа.")
        return

    keyboard = []
    for opt in options:
        option_index = int(opt["option_index"])
        keyboard.append(
            [
                InlineKeyboardButton(
                    str(opt["option_text"]),
                    callback_data=f"ans:{session_id}:{int(question['id'])}:{option_index}",
                )
            ]
        )

    await query.edit_message_text(
        f"Вопрос:\n{question['question_text']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return

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
            await query.answer("Эта сессия вам не принадлежит.", show_alert=True)
            return

        answer = save_quiz_answer(conn, session_id, question_id, selected_option_index)
        if int(answer["already_answered"]) == 1:
            await query.edit_message_text("На этот вопрос уже дан ответ.")
            return

        question_row = conn.execute(
            "SELECT explanation FROM questions WHERE id = ?",
            (question_id,),
        ).fetchone()
        explanation = str(question_row["explanation"] or "") if question_row else ""

        finalized = finalize_quiz_session(conn, session_id)
        if finalized is None:
            await query.edit_message_text("Не удалось завершить сессию.")
            return

    is_correct = int(answer["is_correct"]) == 1
    result_line = "Верно ✅" if is_correct else "Неверно ❌"
    score = int(finalized["score"])
    total_questions = int(finalized["total_questions"])

    message = (
        f"{result_line}\n\n"
        f"Пояснение: {explanation}\n\n"
        f"Результат: {score} из {total_questions}"
    )
    await query.edit_message_text(message)


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

    application = Application.builder().token(settings.bot_token).build()
    application.bot_data["settings"] = settings

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CallbackQueryHandler(category_callback, pattern=r"^cat:\d+$"))
    application.add_handler(CallbackQueryHandler(answer_callback, pattern=r"^ans:\d+:\d+:\d+$"))

    logger.info("Бот запущен (long polling)")
    application.run_polling()


if __name__ == "__main__":
    main()
