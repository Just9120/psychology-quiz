import asyncio
import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import app.main as main


class BotDbOffloadTests(unittest.TestCase):
    def _context(self):
        settings = SimpleNamespace(db_path=':memory:', mini_app_url='https://example.com', mini_app_api_base_url=None, admin_telegram_ids={1})
        app = SimpleNamespace(bot_data={'settings': settings})
        return SimpleNamespace(application=app, user_data={})

    def test_quiz_ui_stats_readingmode_offload(self):
        context = self._context()
        update_quiz = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
        update_ui = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()), effective_chat=SimpleNamespace(type='private'), effective_user=None)
        update_stats = SimpleNamespace(effective_chat=SimpleNamespace(type='private'), effective_user=SimpleNamespace(id=1), message=SimpleNamespace(reply_text=AsyncMock()))
        update_mode = SimpleNamespace(effective_user=SimpleNamespace(id=1, username='u', first_name='f', last_name='l'), message=SimpleNamespace(reply_text=AsyncMock()))

        calls = []
        async def fake_run_db_task(func, *args, **kwargs):
            calls.append(func.__name__)
            if func.__name__ == '_load_categories':
                return [{'id': 1, 'name': 'Cat'}]
            if func.__name__ == '_load_ui_context':
                return ([{'id': 1, 'name': 'Cat'}], None)
            if func.__name__ == '_load_stats':
                return {'total_users': 0, 'new_users_24h': 0, 'new_users_7d': 0, 'new_users_30d': 0, 'active_users_24h': 0, 'active_users_7d': 0, 'active_users_30d': 0, 'total_quiz_sessions': 0, 'completed_quiz_sessions': 0, 'in_progress_quiz_sessions': 0, 'total_quiz_answers': 0, 'total_approved_questions': 0, 'active_categories_count': 0, 'questions_by_category': [], 'top_categories_30d': []}
            return 'normal'

        with patch('app.main._run_db_task', side_effect=fake_run_db_task):
            asyncio.run(main.quiz_command(update_quiz, context))
            asyncio.run(main.ui_command(update_ui, context))
            asyncio.run(main.stats_command(update_stats, context))
            asyncio.run(main.reading_mode_button_handler(update_mode, context))

        self.assertGreaterEqual(len(calls), 4)

    def test_send_current_question_to_chat_offloads_db(self):
        chat = SimpleNamespace(send_message=AsyncMock())
        settings = self._context().application.bot_data['settings']

        async def fake_run_db_task(func, *args, **kwargs):
            return {
                'current': {'question_id': 1, 'order_index': 1, 'total_questions': 2, 'question_text': 'Q'},
                'question_id': 1,
                'options': [{'option_index': 0, 'option_text': 'A'}],
                'reading_mode': 'normal',
            }

        with patch('app.main._run_db_task', side_effect=fake_run_db_task) as mocked:
            result = asyncio.run(main.send_current_question_to_chat(chat, settings, 1))
        self.assertTrue(result)
        self.assertTrue(mocked.called)

    def test_webapp_answer_and_setup_branches_offload_db(self):
        context = self._context()
        message = SimpleNamespace(
            web_app_data=SimpleNamespace(data='{"type":"quiz_answer","session_id":1,"question_id":1,"selected_option_index":0}'),
            reply_text=AsyncMock(),
            delete=AsyncMock(),
            message_id=1,
            chat=SimpleNamespace(send_message=AsyncMock()),
        )
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(type='private'), effective_user=SimpleNamespace(id=1, username='u', first_name='f', last_name='l'))

        async def fake_run_db_task_answer(func, *args, **kwargs):
            return {'status': 'accepted_next', 'next_url': None}

        with patch('app.main._run_db_task', side_effect=fake_run_db_task_answer) as mocked:
            asyncio.run(main.web_app_data_handler(update, context))
        self.assertTrue(mocked.called)

        message.web_app_data = SimpleNamespace(data='{"type":"quiz_setup","quiz_mode":"all","question_count":5,"difficulty":"any","category_ids":[]}')
        async def fake_run_db_task_setup(func, *args, **kwargs):
            if func.__name__ == '_handle_webapp_setup':
                return {'status': 'ok', 'runner_state': {'state': 'setup'}, 'active_categories': [{'id': 1, 'name': 'Cat'}]}
            return None

        with patch('app.main._run_db_task', side_effect=fake_run_db_task_setup) as mocked:
            asyncio.run(main.web_app_data_handler(update, context))
        self.assertTrue(mocked.called)

    def test_difficulty_mix_start_next_offload(self):
        context = self._context()
        query = SimpleNamespace(data='qmode:1:5:any', answer=AsyncMock(), edit_message_text=AsyncMock())
        update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1, username='u', first_name='f', last_name='l'))

        async def fake_run_db_task(func, *args, **kwargs):
            name = func.__name__
            if name == '_start_single_category_quiz':
                return {'status': 'ok', 'session_id': 1}
            if name == '_load_mix_categories':
                return [{'id': 1, 'name': 'Cat'}]
            if name == '_start_mix_quiz_db':
                return {'status': 'ok', 'session_id': 1}
            if name == '_load_next_state':
                return {'status': 'ok'}
            return {'status': 'ok'}

        with patch('app.main._run_db_task', side_effect=fake_run_db_task) as mocked, \
             patch('app.main.remove_main_menu_for_active_quiz', new=AsyncMock()), \
             patch('app.main.send_current_question', new=AsyncMock()):
            asyncio.run(main.difficulty_mode_callback(update, context))

            mix_query = SimpleNamespace(data='mixsel:reset', answer=AsyncMock(), edit_message_text=AsyncMock())
            mix_update = SimpleNamespace(callback_query=mix_query)
            asyncio.run(main.mix_selection_callback(mix_update, context))

            asyncio.run(main.start_mix_quiz(query, context, update.effective_user, '5', 'any', [1]))

            next_query = SimpleNamespace(data='next:1', answer=AsyncMock(), edit_message_text=AsyncMock())
            next_update = SimpleNamespace(callback_query=next_query, effective_user=update.effective_user)
            asyncio.run(main.next_callback(next_update, context))

        self.assertTrue(mocked.called)

    def test_static_guard_no_direct_with_get_connection_in_target_async_functions(self):
        source = inspect.getsource(main)
        for fn in [
            'send_current_question_to_chat',
            'web_app_data_handler',
            'difficulty_mode_callback',
            'mix_selection_callback',
            'start_mix_quiz',
            'next_callback',
        ]:
            block = source.split(f'async def {fn}', 1)[1].split('\nasync def ', 1)[0]
            self.assertIn('await _run_db_task(', block)


if __name__ == '__main__':
    unittest.main()
