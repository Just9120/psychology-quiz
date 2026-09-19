"""Telegram-side proof for a link initiated by an authenticated PWA session."""
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.web_auth import AuthError, WebAuth, valid_token
from app.web_config import WebSettings


def _auth(context):
    data = context.application.bot_data
    if "web_link_auth" not in data:
        settings = WebSettings.from_env()
        if settings is None:
            return None
        data["web_link_auth"] = WebAuth(data["settings"].db_path, settings, None)
    return data["web_link_auth"]


async def link_command(update, context):
    if update.effective_chat is None or update.effective_chat.type != "private" or update.effective_user is None or update.message is None:
        return
    if len(context.args or []) != 1 or not valid_token(context.args[0]):
        await update.message.reply_text("Получите код связывания в PWA и отправьте /link вместе с этим кодом в личном чате.")
        return
    try:
        auth = await asyncio.to_thread(_auth, context)
        if auth is None:
            raise AuthError("disabled")
        token = context.args[0]
        email = await asyncio.to_thread(auth.propose_telegram_link, token, update.effective_user)
        await update.message.reply_text(
            f"Связать ваш учебный прогресс с аккаунтом PWA {email}?\n"
            "Подтверждайте только если вы сами начали связывание в своём аккаунте.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Подтвердить связь", callback_data=f"pwa_link:{token}")]]),
        )
    except (AuthError, RuntimeError):
        await update.message.reply_text("Код недоступен, истёк или связь уже занята. Запросите новый код в своём аккаунте PWA.")


async def confirm_link_callback(update, context):
    query = update.callback_query
    if query is None or update.effective_chat is None or update.effective_chat.type != "private" or update.effective_user is None:
        return
    await query.answer()
    try:
        auth = await asyncio.to_thread(_auth, context)
        if auth is None or not isinstance(query.data, str) or not query.data.startswith("pwa_link:"):
            raise AuthError("invalid_link")
        await asyncio.to_thread(auth.confirm_telegram_link, query.data.removeprefix("pwa_link:"), update.effective_user.id)
        await query.edit_message_text("Владение Telegram подтверждено. Вернитесь в PWA и завершите связывание.")
    except (AuthError, RuntimeError):
        await query.edit_message_text("Подтверждение недоступно или уже использовано. Проверьте состояние в PWA.")
