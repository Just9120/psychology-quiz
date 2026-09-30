"""Returning to Telegram learning menus keeps every available section reachable."""
import importlib

import pytest

from app.homework_chat import BUTTON_TEXT as HOMEWORK_BUTTON_TEXT


@pytest.mark.parametrize("module", ["app.main", "app.classic_quiz_handlers", "app.glossary_handlers"])
def test_restored_learning_menu_keeps_homework_and_other_sections(module):
    keyboard = importlib.import_module(module).get_main_menu_keyboard()
    labels = [button.text for row in keyboard.keyboard for button in row]
    assert labels == [
        "🎯 Начать", "🚀 В окне", "👁 Чтение", "📚 Глоссарий",
        "📖 Литература", HOMEWORK_BUTTON_TEXT, "ℹ️ Помощь", "🙈 Скрыть меню",
    ]
    assert labels.count(HOMEWORK_BUTTON_TEXT) == 1
    assert keyboard.resize_keyboard is True
    assert keyboard.is_persistent is True
