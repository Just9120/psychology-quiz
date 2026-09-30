"""Shared Telegram navigation restored by quiz and glossary handlers."""
from telegram import KeyboardButton, ReplyKeyboardMarkup

START_QUIZ_BUTTON_TEXT = "🎯 Начать"
MINI_APP_BUTTON_TEXT = "🚀 В окне"
READING_MODE_BUTTON_TEXT = "👁 Чтение"
GLOSSARY_BUTTON_TEXT = "📚 Глоссарий"
LITERATURE_BUTTON_TEXT = "📖 Литература"
HOMEWORK_BUTTON_TEXT = "📝 Домашние задания"
HIDE_MENU_BUTTON_TEXT = "🙈 Скрыть меню"


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(START_QUIZ_BUTTON_TEXT), KeyboardButton(MINI_APP_BUTTON_TEXT)],
            [KeyboardButton(READING_MODE_BUTTON_TEXT), KeyboardButton(GLOSSARY_BUTTON_TEXT)],
            [KeyboardButton(LITERATURE_BUTTON_TEXT), KeyboardButton(HOMEWORK_BUTTON_TEXT)],
            [KeyboardButton("ℹ️ Помощь")],
            [KeyboardButton(HIDE_MENU_BUTTON_TEXT)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
