import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.main import quiz_command, ui_command, stats_command, reading_mode_button_handler


class BotDbOffloadTests(unittest.TestCase):
    def _context(self):
        settings = SimpleNamespace(db_path=':memory:', mini_app_url='https://example.com', mini_app_api_base_url=None, admin_telegram_ids={1})
        app = SimpleNamespace(bot_data={'settings': settings})
        return SimpleNamespace(application=app, user_data={})

    def test_quiz_command_offloads_db(self):
        update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
        context = self._context()

        async def fake_run_db_task(func, *args, **kwargs):
            return [{'id': 1, 'name': 'Cat'}]

        with patch('app.main._run_db_task', side_effect=fake_run_db_task) as mocked:
            asyncio.run(quiz_command(update, context))
        self.assertTrue(mocked.called)

    def test_ui_command_offloads_db(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(type='private'), effective_user=None)
        context = self._context()

        async def fake_run_db_task(func, *args, **kwargs):
            return ([{'id': 1, 'name': 'Cat'}], None)

        with patch('app.main._run_db_task', side_effect=fake_run_db_task) as mocked:
            asyncio.run(ui_command(update, context))
        self.assertTrue(mocked.called)

    def test_stats_command_offloads_db(self):
        update = SimpleNamespace(effective_chat=SimpleNamespace(type='private'), effective_user=SimpleNamespace(id=1), message=SimpleNamespace(reply_text=AsyncMock()))
        context = self._context()

        async def fake_run_db_task(func, *args, **kwargs):
            return {'total_users': 0, 'new_users_24h': 0, 'new_users_7d': 0, 'new_users_30d': 0, 'active_users_24h': 0, 'active_users_7d': 0, 'active_users_30d': 0, 'total_quiz_sessions': 0, 'completed_quiz_sessions': 0, 'in_progress_quiz_sessions': 0, 'total_quiz_answers': 0, 'total_approved_questions': 0, 'active_categories_count': 0, 'questions_by_category': [], 'top_categories_30d': []}

        with patch('app.main._run_db_task', side_effect=fake_run_db_task) as mocked:
            asyncio.run(stats_command(update, context))
        self.assertTrue(mocked.called)

    def test_reading_mode_button_handler_offloads_db(self):
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1, username='u', first_name='f', last_name='l'), message=SimpleNamespace(reply_text=AsyncMock()))
        context = self._context()

        async def fake_run_db_task(func, *args, **kwargs):
            return 'normal'

        with patch('app.main._run_db_task', side_effect=fake_run_db_task) as mocked:
            asyncio.run(reading_mode_button_handler(update, context))
        self.assertTrue(mocked.called)


if __name__ == '__main__':
    unittest.main()
