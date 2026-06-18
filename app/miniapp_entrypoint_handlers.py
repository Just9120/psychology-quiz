from __future__ import annotations

import asyncio
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from app.db import create_or_load_user, get_active_categories, get_connection
from app.glossary import GLOSSARY_QUIZ_SESSION_KEY
from app.handler_latency import HandlerLatency
from app.miniapp_context import build_miniapp_setup_entrypoint_url
from app.miniapp_runner import build_miniapp_runner_state

logger = logging.getLogger(__name__)

START_QUIZ_BUTTON_TEXT = "🎯 Начать"
MINI_APP_BUTTON_TEXT = "🚀 В окне"
LEGACY_MINI_APP_BUTTON_TEXT = "🚀 Викторина в окне"
MINI_APP_BUTTON_ALIASES = (MINI_APP_BUTTON_TEXT, LEGACY_MINI_APP_BUTTON_TEXT)


async def _run_db_task(func, *args, **kwargs):
    import sys

    main_module = sys.modules.get("app.main")
    main_run_db_task = getattr(main_module, "_run_db_task", None)
    if main_run_db_task is not None and main_run_db_task is not _run_db_task:
        return await main_run_db_task(func, *args, **kwargs)
    return await asyncio.to_thread(func, *args, **kwargs)


def is_private_chat(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type == "private")


def build_miniapp_launch_inline_keyboard(
    url: str,
    *,
    force_setup_url: str | None = None,
    reopen_result: bool = False,
) -> InlineKeyboardMarkup:
    first_label = "📊 Показать результат" if reopen_result else "🚀 Открыть викторину"
    keyboard = [[InlineKeyboardButton(first_label, web_app=WebAppInfo(url=url))]]
    if force_setup_url:
        keyboard.append([InlineKeyboardButton("🆕 Новая викторина", web_app=WebAppInfo(url=force_setup_url))])
    return InlineKeyboardMarkup(keyboard)


async def mini_app_menu_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ui_command(update, context)


async def ui_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    latency = HandlerLatency(handler="ui_command", command="/ui", telegram_user_id=getattr(getattr(update, "effective_user", None), "id", None))
    latency.start()
    context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
    if update.message is None:
        return
    if not is_private_chat(update):
        await update.message.reply_text("Викторина в окне доступна только в личном чате с ботом.")
        return

    settings = context.application.bot_data["settings"]
    if not settings.mini_app_url:
        await update.message.reply_text(
            "Викторина в окне пока не настроена. Можно пройти викторину в чате через /quiz."
        )
        return

    tg_user = update.effective_user

    def _load_ui_context():
        with get_connection(settings.db_path) as conn:
            categories = get_active_categories(conn)
            runner_state = None
            if tg_user is not None:
                user_row = create_or_load_user(conn, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
                runner_state = build_miniapp_runner_state(conn, actor_user_id=int(user_row["id"]))
            return categories, runner_state

    db_started_at = time.perf_counter()
    categories, runner_state = await _run_db_task(_load_ui_context)
    latency.add_db(db_started_at)
    if not categories:
        api_started_at = time.perf_counter()
        await update.message.reply_text(
            "Сейчас нет доступных тем для запуска викторины.\n"
            "Используйте /quiz позже или проверьте загрузку вопросов."
        )
        latency.add_telegram_api(api_started_at)
        latency.summary()
        return

    has_active = isinstance(runner_state, dict) and runner_state.get("state") == "in_progress"
    miniapp_url, fallback_mode = build_miniapp_setup_entrypoint_url(
        settings.mini_app_url,
        categories,
        abandons_active_session=has_active,
        api_base_url=settings.mini_app_api_base_url,
    )
    if miniapp_url is None:
        await update.message.reply_text(
            "Викторину в окне сейчас не удалось открыть. Попробуйте /ui ещё раз или пройдите её в чате через /quiz."
        )
        return
    logger.debug("Mini App setup URL length: %s", len(miniapp_url))

    intro_text = (
        "Откройте викторину в удобном окне.\n"
        "\n"
        f"В чате её по-прежнему можно пройти через {START_QUIZ_BUTTON_TEXT}.\n"
        "\n"
        f"Если кнопка не открылась, нажмите {MINI_APP_BUTTON_TEXT} в меню или отправьте /ui ещё раз."
    )
    if fallback_mode:
        intro_text = (
            "Часть данных не поместилась в ссылку открытия. Если экран выглядит неполным, "
            "откройте викторину заново или используйте /quiz.\n\n"
            + intro_text
        )
    if has_active:
        intro_text = (
            "У вас уже есть начатая викторина. В окне можно выбрать новый режим.\n"
            "Запуск новой викторины завершит текущую активную попытку.\n"
            "\n"
            f"Если кнопка не открылась, нажмите {MINI_APP_BUTTON_TEXT} в меню или отправьте /ui ещё раз."
        )
    api_started_at = time.perf_counter()
    await update.message.reply_text(
        intro_text,
        reply_markup=build_miniapp_launch_inline_keyboard(miniapp_url),
    )
    latency.add_telegram_api(api_started_at)
    latency.summary()
