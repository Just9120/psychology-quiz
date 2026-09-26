"""Telegram clients no longer promote the owner-only PWA to students."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.main import HELP_TEXT, get_main_menu_keyboard, pwa_command


def test_student_menu_does_not_advertise_owner_pwa():
    labels = [button.text for row in get_main_menu_keyboard().keyboard for button in row]
    assert "🌐 Веб-приложение" not in labels
    assert "/pwa" not in HELP_TEXT


def test_legacy_pwa_command_returns_owner_only_notice_without_link():
    reply = AsyncMock()
    update = SimpleNamespace(message=SimpleNamespace(reply_text=reply))
    asyncio.run(pwa_command(update, SimpleNamespace()))
    reply.assert_awaited_once()
    assert "только владельцу" in reply.await_args.args[0]
    assert "reply_markup" not in reply.await_args.kwargs
