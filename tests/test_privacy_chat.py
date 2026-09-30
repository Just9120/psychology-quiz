"""Telegram's destructive command requires a second private-chat message."""
import asyncio
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.db import create_or_load_user, get_connection
from app.privacy_chat import confirm_delete_data_command, delete_data_command
from scripts import init_db


def test_telegram_learning_deletion_requires_private_repeat_confirmation(tmp_path):
    bank = tmp_path / "privacy-chat.sqlite3"
    with patch.object(init_db, "resolve_db_path", return_value=str(bank)):
        assert init_db.main() == 0
    with closing(get_connection(str(bank))) as conn, conn:
        create_or_load_user(conn, 42, None, "Owner", None)
        other = create_or_load_user(conn, 777, None, "Other", None)
        conn.execute("INSERT INTO quiz_sessions(user_id) VALUES(1)")
        conn.execute("INSERT INTO quiz_sessions(user_id) VALUES(?)", (other["id"],))

    message = SimpleNamespace(reply_text=AsyncMock())
    actor = SimpleNamespace(id=42, username=None, first_name="Owner", last_name=None)
    update = SimpleNamespace(message=message, effective_user=actor,
                             effective_chat=SimpleNamespace(type="group"))
    context = SimpleNamespace(user_data={}, application=SimpleNamespace(
        bot_data={"settings": SimpleNamespace(db_path=str(bank))}))
    asyncio.run(delete_data_command(update, context))
    assert context.user_data == {}
    with closing(get_connection(str(bank))) as conn:
        assert conn.execute("SELECT count(*) FROM quiz_sessions").fetchone()[0] == 2

    update.effective_chat.type = "private"
    asyncio.run(confirm_delete_data_command(update, context))
    assert "Сначала отправьте /delete_data" in message.reply_text.await_args.args[0]
    asyncio.run(delete_data_command(update, context))
    assert "learning_data_deletion_token" in context.user_data
    with closing(get_connection(str(bank))) as conn:
        assert conn.execute("SELECT count(*) FROM quiz_sessions").fetchone()[0] == 2

    asyncio.run(confirm_delete_data_command(update, context))
    assert context.user_data == {}
    with closing(get_connection(str(bank))) as conn:
        assert conn.execute("SELECT count(*) FROM quiz_sessions WHERE user_id=1").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM quiz_sessions WHERE user_id=?", (other["id"],)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM users WHERE id=1").fetchone()[0] == 1

    with closing(get_connection(str(bank))) as conn, conn:
        conn.execute("""INSERT INTO web_accounts(email,password_hash,user_id,verified_at,created_at)
            VALUES(?,?,?,?,?)""", ("owner@example.invalid", "test-only", other["id"], 1, 1))
    update.effective_user = SimpleNamespace(id=777, username=None, first_name="Other", last_name=None)
    asyncio.run(delete_data_command(update, context))
    assert "learning_data_deletion_token" not in context.user_data
    assert "связаны с аккаунтом владельца PWA" in message.reply_text.await_args.args[0]
    with closing(get_connection(str(bank))) as conn:
        assert conn.execute("SELECT count(*) FROM quiz_sessions WHERE user_id=?", (other["id"],)).fetchone()[0] == 1
