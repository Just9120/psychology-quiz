"""Private-chat confirmation for deleting Telegram learning history."""
from __future__ import annotations

import asyncio
from contextlib import closing

from telegram import Update
from telegram.ext import ContextTypes

from app.db import create_or_load_user, get_connection
from app.privacy_data import PrivacyError, confirm_learning_data_deletion, prepare_learning_data_deletion

_TOKEN_KEY = "learning_data_deletion_token"


def _run(db_path: str, telegram_user, token: str | None):
    with closing(get_connection(db_path)) as conn, conn:
        user = create_or_load_user(conn, telegram_user.id, telegram_user.username,
                                   telegram_user.first_name, telegram_user.last_name)
        actor = int(user["id"])
        return (prepare_learning_data_deletion(conn, actor) if token is None
                else confirm_learning_data_deletion(conn, actor, token))


async def delete_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    if update.effective_chat is None or update.effective_chat.type != "private":
        await update.message.reply_text("Удаление учебных данных доступно только в личном чате.")
        return
    context.user_data.pop(_TOKEN_KEY, None)
    try:
        prepared = await asyncio.to_thread(_run, context.application.bot_data["settings"].db_path,
                                           update.effective_user, None)
    except PrivacyError as error:
        if str(error) == "linked_owner_requires_separate_flow":
            await update.message.reply_text("Ваши учебные данные связаны с аккаунтом владельца PWA. Здесь нельзя удалить его общую историю; данные не изменены.")
            return
        raise
    context.user_data[_TOKEN_KEY] = prepared["confirmation_token"]
    await update.message.reply_text(
        "Можно удалить ваши ответы и попытки, отметки книг, цели, достижения и историю повторений. "
        "Это удаление истории обучения, а не аккаунта Telegram. Идентификатор Telegram и переданное имя "
        "сохранятся для работы бота. Для подтверждения в течение 10 минут отправьте /delete_data_confirm. "
        "Если передумали, ничего не отправляйте."
    )


async def confirm_delete_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    if update.effective_chat is None or update.effective_chat.type != "private":
        await update.message.reply_text("Подтверждение доступно только в личном чате.")
        return
    token = context.user_data.pop(_TOKEN_KEY, None)
    if not token:
        await update.message.reply_text("Сначала отправьте /delete_data, чтобы увидеть состав удаляемых данных.")
        return
    try:
        await asyncio.to_thread(_run, context.application.bot_data["settings"].db_path,
                                update.effective_user, token)
    except PrivacyError:
        await update.message.reply_text("Подтверждение больше не действует. Данные не изменены; начните заново через /delete_data.")
        return
    context.user_data.clear()
    await update.message.reply_text("Сохранённые учебные данные удалены. Вы можете продолжать пользоваться ботом.")
