import asyncio
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.auth_schema import migrate_auth_schema
from app.classic_quiz_handlers import maybe_send_pwa_offer
from app.db import get_connection
from app.invitation_schema import migrate_invitation_schema
from tests.test_attempt_content import bank


def test_private_quiz_offer_is_sent_once_without_student_launch(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        migrate_auth_schema(conn)
        migrate_invitation_schema(conn)
    private_chat = SimpleNamespace(type="private", send_message=AsyncMock())
    group_chat = SimpleNamespace(type="group", send_message=AsyncMock())

    async def offer():
        await maybe_send_pwa_offer(group_chat, 42, db_path=str(bank), origin="https://pwa.example.test", enabled=False)
        await maybe_send_pwa_offer(private_chat, 42, db_path=str(bank), origin="https://pwa.example.test", enabled=False)
        await maybe_send_pwa_offer(private_chat, 42, db_path=str(bank), origin="https://pwa.example.test", enabled=False)

    asyncio.run(offer())

    group_chat.send_message.assert_not_awaited()
    private_chat.send_message.assert_awaited_once()
    message = private_chat.send_message.await_args
    assert "демо-задания" in message.args[0]
    assert message.kwargs["reply_markup"].inline_keyboard[0][0].url == "https://pwa.example.test"
    with closing(get_connection(str(bank))) as conn:
        row = conn.execute("SELECT promo_shown_at, token_digest FROM pwa_invitations WHERE user_id=1").fetchone()
        assert row[0] is not None and row[1] is None
