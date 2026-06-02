import asyncio
import ast
import inspect
import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import app.main as main


class BotDbOffloadTests(unittest.TestCase):
    def _context(self):
        settings = SimpleNamespace(db_path=':memory:', mini_app_url='https://example.com', mini_app_api_base_url=None, admin_telegram_ids={1}, classic_quiz_send_next_as_new_message=False)
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


    def test_quiz_command_explains_modes_and_preserves_callback_buttons(self):
        context = self._context()
        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=123),
        )

        async def fake_run_db_task(func, *args, **kwargs):
            self.assertEqual('_load_categories', func.__name__)
            return [{'id': 1, 'name': 'Cat'}]

        with patch('app.main._run_db_task', side_effect=fake_run_db_task):
            asyncio.run(main.quiz_command(update, context))

        text = update.message.reply_text.call_args.args[0]
        markup = update.message.reply_text.call_args.kwargs['reply_markup']
        button_texts = [row[0].text for row in markup.inline_keyboard]
        callback_data = [row[0].callback_data for row in markup.inline_keyboard]

        self.assertIn('Выберите режим викторины:', text)
        self.assertIn('Конкретная тема — вопросы по одной выбранной теме.', text)
        self.assertIn('Микс из выбранных тем — вопросы из нескольких тем.', text)
        self.assertIn('Все темы — случайные вопросы из всего доступного банка.', text)
        self.assertEqual(['Конкретная тема', 'Микс из выбранных тем', 'Все темы'], button_texts)
        self.assertEqual(['qzmode:single', 'qzmode:selected_mix', 'qzmode:all'], callback_data)

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

    def test_classic_reply_text_answer_logs_safe_status_and_latency_bucket(self):
        context = self._context()
        context.application.bot_data['settings'].classic_quiz_reply_keyboard_mode = True
        context.user_data[main.CLASSIC_REPLY_STATE_KEY] = {"status": "awaiting_answer", "session_id": 10, "question_id": 20}
        message = SimpleNamespace(text="secret answer text", reply_text=AsyncMock())
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=123, username='u', first_name='secret first', last_name='secret last'),
        )

        async def fake_run_db_task(func, *args, **kwargs):
            return {
                'status': 'ok',
                'session_id': 10,
                'question_id': 20,
                'options': [{'option_index': 0, 'option_text': 'sensitive option'}],
            }

        with patch('app.main._run_db_task', side_effect=fake_run_db_task), \
             patch('app.main.logger.info') as info_log:
            asyncio.run(main.classic_reply_text_answer_handler(update, context))

        logged = "\n".join(" ".join(str(arg) for arg in call.args) for call in info_log.call_args_list)
        self.assertIn("classic_text_answer_ingress", logged)
        self.assertIn("classic_text_answer_latency", logged)
        self.assertIn("status=received", logged)
        self.assertIn("status=invalid_input", logged)
        self.assertIn("elapsed_ms=", logged)
        self.assertIn("latency_bucket=lt_", logged)
        self.assertNotIn("secret answer text", logged)
        self.assertNotIn("sensitive option", logged)
        self.assertNotIn("secret first", logged)

    def test_latency_logging_for_quiz_and_answer(self):
        context = self._context()
        update_quiz = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=123),
        )
        async def _slow_noop(*args, **kwargs):
            await asyncio.sleep(0.01)

        query = SimpleNamespace(
            data='ans:1:1:0',
            answer=AsyncMock(side_effect=_slow_noop),
            edit_message_text=AsyncMock(side_effect=_slow_noop),
        )
        update_answer = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=123, username='u', first_name='f', last_name='l'),
        )

        async def fake_run_db_task(func, *args, **kwargs):
            if func.__name__ == '_load_categories':
                return [{'id': 1, 'name': 'Cat'}]
            if func.__name__ == '_handle_answer_db':
                return {
                    'status': 'accepted',
                    'is_correct': True,
                    'explanation': 'ok',
                    'answered_questions': 1,
                    'total_questions': 2,
                    'reading_mode': 'normal',
                    'is_last_question': False,
                    'finalized': None,
                }
            return {'status': 'ok'}

        with patch('app.main._run_db_task', side_effect=fake_run_db_task), patch('app.main.logger.info') as info_log:
            asyncio.run(main.quiz_command(update_quiz, context))
            asyncio.run(main.answer_callback(update_answer, context))

        logged = " ".join(str(call.args[2]) for call in info_log.call_args_list if len(call.args) >= 3 and call.args[0] == "%s %s")
        self.assertIn("handler=quiz_command", logged)
        self.assertIn("handler=answer_callback", logged)
        self.assertIn("elapsed_ms=", logged)
        self.assertIn("telegram_api_elapsed_ms=", logged)
        self.assertIn("other_elapsed_ms=", logged)
        match = re.search(r"handler=answer_callback.*?telegram_api_elapsed_ms=(\d+)", logged)
        self.assertIsNotNone(match)
        self.assertGreater(int(match.group(1)), 0)
        self.assertNotIn("BOT_TOKEN", logged)
        self.assertNotIn("question_text", logged)
        self.assertNotIn("callback_data=", logged)

    def test_update_ingress_logs_callback_safely_and_allows_callback_handler(self):
        context = self._context()
        user = SimpleNamespace(id=1, username='u', first_name='secret first', last_name='secret last')
        query = SimpleNamespace(data='ans:123:456:2', answer=AsyncMock(), edit_message_text=AsyncMock())
        callback_update = SimpleNamespace(update_id=777, callback_query=query, effective_user=user, message=None)
        message_update = SimpleNamespace(
            update_id=778,
            callback_query=None,
            message=SimpleNamespace(text='secret message text', web_app_data=None),
            effective_user=user,
        )

        async def fake_run_db_task(func, *args, **kwargs):
            if func.__name__ == '_handle_answer_db':
                return {
                    'status': 'accepted',
                    'is_correct': False,
                    'explanation': 'question text marker and answer text marker',
                    'answered_questions': 1,
                    'total_questions': 2,
                    'reading_mode': 'normal',
                    'is_last_question': False,
                    'finalized': None,
                }
            return {'status': 'ok'}

        with patch('app.main._run_db_task', side_effect=fake_run_db_task), \
             patch('app.main.logger.info') as info_log:
            asyncio.run(main.update_ingress_logger(callback_update, context))
            asyncio.run(main.update_ingress_logger(message_update, context))
            asyncio.run(main.answer_callback(callback_update, context))

        logged = " ".join(
            " ".join(str(arg) for arg in call.args)
            for call in info_log.call_args_list
        )
        self.assertIn(main.UPDATE_INGRESS_LOG_PREFIX, logged)
        self.assertIn('update_id=777', logged)
        self.assertIn('update_type=callback_query', logged)
        self.assertIn('callback_prefix=ans', logged)
        self.assertIn('telegram_user_id=1', logged)
        self.assertIn('update_id=778', logged)
        self.assertIn('update_type=message', logged)
        self.assertIn('handler=answer_callback', logged)
        self.assertNotIn('ans:123:456:2', logged)
        self.assertNotIn('secret message text', logged)
        self.assertNotIn('question text marker', logged)
        self.assertNotIn('answer text marker', logged)
        query.answer.assert_awaited()
        query.edit_message_text.assert_awaited()

    def test_update_ingress_handler_registered_in_early_group(self):
        class FakeApplication:
            def __init__(self):
                self.handlers = []

            def add_handler(self, handler, group=0):
                self.handlers.append((handler, group))

        app = FakeApplication()
        main.register_update_ingress_handler(app)

        self.assertEqual(1, len(app.handlers))
        handler, group = app.handlers[0]
        self.assertEqual(main.UPDATE_INGRESS_HANDLER_GROUP, group)
        self.assertEqual(main.update_ingress_logger, handler.callback)
        self.assertLess(group, 0)

    def test_answer_and_next_callbacks_emit_secret_safe_handler_start_logs(self):
        context = self._context()
        user = SimpleNamespace(id=1, username='u', first_name='f', last_name='l')
        answer_query = SimpleNamespace(data='ans:123:456:2', answer=AsyncMock(), edit_message_text=AsyncMock())
        answer_update = SimpleNamespace(callback_query=answer_query, effective_user=user)
        next_query = SimpleNamespace(data='next:123', answer=AsyncMock(), edit_message_text=AsyncMock())
        next_update = SimpleNamespace(callback_query=next_query, effective_user=user)

        async def fake_run_db_task(func, *args, **kwargs):
            if func.__name__ == '_handle_answer_db':
                return {
                    'status': 'accepted',
                    'is_correct': False,
                    'explanation': 'question text marker and answer text marker',
                    'answered_questions': 1,
                    'total_questions': 2,
                    'reading_mode': 'normal',
                    'is_last_question': False,
                    'finalized': None,
                }
            if func.__name__ == '_load_next_state':
                return {'status': 'ok'}
            return {'status': 'ok'}

        with patch('app.main._run_db_task', side_effect=fake_run_db_task), \
             patch('app.main.send_current_question', new=AsyncMock()), \
             patch('app.main.logger.info') as info_log:
            asyncio.run(main.answer_callback(answer_update, context))
            context.user_data['_callback_in_progress'] = set()
            asyncio.run(main.next_callback(next_update, context))

        start_logs = [
            str(call.args[2])
            for call in info_log.call_args_list
            if len(call.args) >= 3 and call.args[0] == "%s %s" and call.args[1] == main.HANDLER_START_LOG_PREFIX
        ]
        joined = " ".join(start_logs)
        self.assertIn("handler=answer_callback", joined)
        self.assertIn("handler=next_callback", joined)
        self.assertIn("phase=handler_start", joined)
        self.assertIn("callback_prefix=ans", joined)
        self.assertIn("callback_prefix=next", joined)
        self.assertIn("telegram_user_id=1", joined)
        self.assertIn("session_id=123", joined)
        self.assertNotIn("ans:123:456:2", joined)
        self.assertNotIn("next:123", joined)
        self.assertNotIn("question text marker", joined)
        self.assertNotIn("answer text marker", joined)
        self.assertNotIn("BOT_TOKEN", joined)
        self.assertNotIn("callback_data=", joined)

    def test_answer_and_next_callbacks_send_single_feedback_and_guard_repeated_taps(self):
        context = self._context()
        user = SimpleNamespace(id=1, username='u', first_name='f', last_name='l')

        repeated_answer_query = SimpleNamespace(data='ans:1:1:0', answer=AsyncMock(), edit_message_text=AsyncMock())
        repeated_answer_update = SimpleNamespace(callback_query=repeated_answer_query, effective_user=user)
        repeated_next_query = SimpleNamespace(data='next:1', answer=AsyncMock(), edit_message_text=AsyncMock())
        repeated_next_update = SimpleNamespace(callback_query=repeated_next_query, effective_user=user)
        normal_answer_query = SimpleNamespace(data='ans:1:1:0', answer=AsyncMock(), edit_message_text=AsyncMock())
        normal_answer_update = SimpleNamespace(callback_query=normal_answer_query, effective_user=user)
        normal_next_query = SimpleNamespace(data='next:1', answer=AsyncMock(), edit_message_text=AsyncMock())
        normal_next_update = SimpleNamespace(callback_query=normal_next_query, effective_user=user)

        async def fake_run_db_task(func, *args, **kwargs):
            if func.__name__ == '_handle_answer_db':
                return {
                    'status': 'accepted', 'is_correct': True, 'explanation': 'ok',
                    'answered_questions': 1, 'total_questions': 2, 'reading_mode': 'normal',
                    'is_last_question': False, 'finalized': None,
                }
            if func.__name__ == '_load_next_state':
                return {'status': 'ok'}
            return {'status': 'ok'}

        with patch('app.main._run_db_task', side_effect=fake_run_db_task), \
             patch('app.main.send_current_question', new=AsyncMock()):
            context.user_data['_callback_in_progress'] = {'answer:1:1'}
            asyncio.run(main.answer_callback(repeated_answer_update, context))
            repeated_answer_query.answer.assert_awaited_once_with("Ответ уже обрабатывается…", cache_time=1)

            context.user_data['_callback_in_progress'] = {'next:1'}
            asyncio.run(main.next_callback(repeated_next_update, context))
            repeated_next_query.answer.assert_awaited_once_with("Переход уже выполняется…", cache_time=1)

            asyncio.run(main.answer_callback(normal_answer_update, context))
            normal_answer_query.answer.assert_awaited_once_with(cache_time=1)

            context.user_data['_callback_in_progress'] = set()
            asyncio.run(main.next_callback(normal_next_update, context))
            normal_next_query.answer.assert_awaited_once_with(cache_time=1)

    def test_callback_in_progress_guard_is_cleared_on_error_paths(self):
        context = self._context()
        user = SimpleNamespace(id=1, username='u', first_name='f', last_name='l')

        answer_query = SimpleNamespace(data='ans:1:1:0', answer=AsyncMock(), edit_message_text=AsyncMock())
        answer_update = SimpleNamespace(callback_query=answer_query, effective_user=user)
        next_query = SimpleNamespace(data='next:1', answer=AsyncMock(), edit_message_text=AsyncMock())
        next_update = SimpleNamespace(callback_query=next_query, effective_user=user)

        async def fake_run_db_task_answer(func, *args, **kwargs):
            if func.__name__ == '_handle_answer_db':
                return {'status': 'session_missing'}
            return {'status': 'ok'}

        async def fake_run_db_task_next(func, *args, **kwargs):
            if func.__name__ == '_load_next_state':
                return {'status': 'missing'}
            return {'status': 'ok'}

        with patch('app.main._run_db_task', side_effect=fake_run_db_task_answer):
            asyncio.run(main.answer_callback(answer_update, context))
        self.assertNotIn('answer:1:1', context.user_data.get('_callback_in_progress', set()))

        with patch('app.main._run_db_task', side_effect=fake_run_db_task_next):
            asyncio.run(main.next_callback(next_update, context))
        self.assertNotIn('next:1', context.user_data.get('_callback_in_progress', set()))



    def test_answer_and_next_acknowledge_before_db_work(self):
        context = self._context()
        user = SimpleNamespace(id=1, username='u', first_name='f', last_name='l')
        answer_query = SimpleNamespace(data='ans:1:1:0', answer=AsyncMock(), edit_message_text=AsyncMock())
        answer_update = SimpleNamespace(callback_query=answer_query, effective_user=user)

        async def fake_answer_db(func, *args, **kwargs):
            if func.__name__ == '_handle_answer_db':
                self.assertEqual(answer_query.answer.await_count, 1)
                return {
                    'status': 'accepted', 'is_correct': True, 'explanation': 'ok',
                    'answered_questions': 1, 'total_questions': 2, 'reading_mode': 'normal',
                    'is_last_question': False, 'finalized': None,
                }
            return {'status': 'ok'}

        with patch('app.main._run_db_task', side_effect=fake_answer_db):
            asyncio.run(main.answer_callback(answer_update, context))

        next_query = SimpleNamespace(data='next:1', answer=AsyncMock(), edit_message_text=AsyncMock())
        next_update = SimpleNamespace(callback_query=next_query, effective_user=user)

        async def fake_next_db(func, *args, **kwargs):
            if func.__name__ == '_load_next_state':
                self.assertEqual(next_query.answer.await_count, 1)
                return {'status': 'missing'}
            return {'status': 'ok'}

        with patch('app.main._run_db_task', side_effect=fake_next_db):
            asyncio.run(main.next_callback(next_update, context))

    def test_answer_and_next_latency_logs_split_telegram_api_timings(self):
        context = self._context()
        user = SimpleNamespace(id=1, username='u', first_name='f', last_name='l')
        answer_query = SimpleNamespace(data='ans:1:1:0', answer=AsyncMock(), edit_message_text=AsyncMock())
        answer_update = SimpleNamespace(callback_query=answer_query, effective_user=user)
        next_query = SimpleNamespace(data='next:1', answer=AsyncMock(), edit_message_text=AsyncMock())
        next_update = SimpleNamespace(callback_query=next_query, effective_user=user)

        async def fake_answer_db(func, *args, **kwargs):
            if func.__name__ == '_handle_answer_db':
                return {
                    'status': 'accepted', 'is_correct': True, 'explanation': 'ok',
                    'answered_questions': 1, 'total_questions': 2, 'reading_mode': 'normal',
                    'is_last_question': False, 'finalized': None,
                }
            return {'status': 'ok'}

        async def fake_next_db(func, *args, **kwargs):
            if func.__name__ == '_load_next_state':
                return {'status': 'missing'}
            return {'status': 'ok'}

        with patch('app.main.logger.info') as info_log:
            with patch('app.main._run_db_task', side_effect=fake_answer_db):
                asyncio.run(main.answer_callback(answer_update, context))
            with patch('app.main._run_db_task', side_effect=fake_next_db):
                asyncio.run(main.next_callback(next_update, context))

        logged = " ".join(str(call.args[2]) for call in info_log.call_args_list if len(call.args) >= 3 and call.args[0] == "%s %s")
        self.assertRegex(logged, r"handler=answer_callback.*telegram_api_elapsed_ms=\d+.*callback_ack_elapsed_ms=\d+.*message_edit_elapsed_ms=\d+.*message_send_elapsed_ms=\d+")
        self.assertRegex(logged, r"handler=next_callback.*telegram_api_elapsed_ms=\d+.*callback_ack_elapsed_ms=\d+.*message_edit_elapsed_ms=\d+.*message_send_elapsed_ms=\d+")

    def test_repeated_tap_logs_safe_status_field(self):
        context = self._context()
        context.user_data['_callback_in_progress'] = {'answer:1:1'}
        user = SimpleNamespace(id=1, username='u', first_name='f', last_name='l')
        answer_query = SimpleNamespace(data='ans:1:1:0', answer=AsyncMock(), edit_message_text=AsyncMock())
        answer_update = SimpleNamespace(callback_query=answer_query, effective_user=user)

        with patch('app.main.logger.info') as info_log:
            asyncio.run(main.answer_callback(answer_update, context))

        logged = " ".join(str(call.args[2]) for call in info_log.call_args_list if len(call.args) >= 3 and call.args[0] == "%s %s")
        self.assertIn('status=ignored_repeated_tap', logged)
        self.assertIn('repeated_tap=true', logged)
        answer_query.answer.assert_awaited_with('Ответ уже обрабатывается…', cache_time=1)

    def test_start_mix_quiz_and_answer_callback_include_helper_telegram_timing(self):
        context = self._context()
        user = SimpleNamespace(id=1, username='u', first_name='f', last_name='l')

        mix_query = SimpleNamespace(data='qmodeselmix:5:any', answer=AsyncMock(), edit_message_text=AsyncMock())
        mix_update = SimpleNamespace(callback_query=mix_query, effective_user=user)
        context.user_data['selected_mix_categories'] = {1}

        answer_query = SimpleNamespace(data='ans:1:1:0', answer=AsyncMock(), edit_message_text=AsyncMock())
        answer_update = SimpleNamespace(callback_query=answer_query, effective_user=user)

        async def fake_run_db_task(func, *args, **kwargs):
            if func.__name__ == '_start_mix_quiz_db':
                return {'status': 'ok', 'session_id': 1}
            if func.__name__ == '_handle_answer_db':
                return {
                    'status': 'accepted', 'is_correct': True, 'explanation': 'ok',
                    'answered_questions': 1, 'total_questions': 1, 'reading_mode': 'normal',
                    'is_last_question': True, 'finalized': {'score': 1, 'total_questions': 1},
                }
            return {'status': 'ok'}

        async def slow_reply(*args, **kwargs):
            await asyncio.sleep(0.01)

        with patch('app.main._run_db_task', side_effect=fake_run_db_task),              patch('app.main.remove_main_menu_for_active_quiz', new=AsyncMock(side_effect=slow_reply)),              patch('app.main.send_current_question', new=AsyncMock(side_effect=slow_reply)),              patch('app.main.send_quiz_result_with_main_menu', new=AsyncMock(side_effect=slow_reply)),              patch('app.main.logger.info') as info_log:
            asyncio.run(main.difficulty_mode_selected_mix_callback(mix_update, context))
            asyncio.run(main.answer_callback(answer_update, context))

        logged = " ".join(str(call.args[2]) for call in info_log.call_args_list if len(call.args) >= 3 and call.args[0] == "%s %s")
        mix_values = [int(v) for v in re.findall(r"handler=difficulty_mode_selected_mix_callback.*?telegram_api_elapsed_ms=(\d+)", logged)]
        ans_values = [int(v) for v in re.findall(r"handler=answer_callback.*?telegram_api_elapsed_ms=(\d+)", logged)]
        self.assertTrue(mix_values)
        self.assertTrue(ans_values)
        self.assertTrue(all(v >= 0 for v in mix_values))
        self.assertTrue(all(v >= 0 for v in ans_values))
        self.assertRegex(logged, r"other_elapsed_ms=\d+")

    def test_bot_latency_slow_threshold(self):
        latency = main._HandlerLatency(handler='slow_test', callback_prefix='slow')
        latency._started_at -= (main.SLOW_HANDLER_THRESHOLD_MS + 50) / 1000
        with patch('app.main.logger.info') as info_log, patch('app.main.logger.warning') as warn_log:
            latency.summary()
        self.assertTrue(info_log.called)
        self.assertTrue(warn_log.called)

        fast_latency = main._HandlerLatency(handler='fast_test', callback_prefix='fast')
        with patch('app.main.logger.warning') as warn_fast:
            fast_latency.summary()
        self.assertFalse(warn_fast.called)
    def test_question_count_callbacks_do_not_raise_nameerror_and_render_next_step(self):
        context = self._context()

        qcnt_query = SimpleNamespace(data='qcnt:1:5', answer=AsyncMock(), edit_message_text=AsyncMock())
        qcnt_update = SimpleNamespace(callback_query=qcnt_query, effective_user=SimpleNamespace(id=1))
        asyncio.run(main.question_count_callback(qcnt_update, context))

        qcntall_query = SimpleNamespace(data='qcntall:5', answer=AsyncMock(), edit_message_text=AsyncMock())
        qcntall_update = SimpleNamespace(callback_query=qcntall_query, effective_user=SimpleNamespace(id=1))
        asyncio.run(main.question_count_mix_callback(qcntall_update, context))

        qcntselmix_query = SimpleNamespace(data='qcntselmix:5', answer=AsyncMock(), edit_message_text=AsyncMock())
        qcntselmix_update = SimpleNamespace(callback_query=qcntselmix_query, effective_user=SimpleNamespace(id=1))
        asyncio.run(main.question_count_selected_mix_callback(qcntselmix_update, context))

        qcnt_query.answer.assert_awaited()
        qcntall_query.answer.assert_awaited()
        qcntselmix_query.answer.assert_awaited()
        qcnt_query.edit_message_text.assert_awaited()
        qcntall_query.edit_message_text.assert_awaited()
        qcntselmix_query.edit_message_text.assert_awaited()

    def test_reading_mode_screen_text_and_normal_selected_state(self):
        context = self._context()
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=1, username='u', first_name='f', last_name='l'),
            message=message,
        )

        async def fake_run_db_task(func, *args, **kwargs):
            return 'normal'

        with patch('app.main._run_db_task', side_effect=fake_run_db_task):
            asyncio.run(main.reading_mode_button_handler(update, context))

        message.reply_text.assert_awaited_once()
        text = message.reply_text.call_args.args[0]
        keyboard = message.reply_text.call_args.kwargs['reply_markup']
        button_texts = [row[0].text for row in keyboard.inline_keyboard]
        callback_data = [row[0].callback_data for row in keyboard.inline_keyboard]

        self.assertIn('Режим чтения', text)
        self.assertIn('Текущий режим: Обычный', text)
        self.assertIn('Режим влияет на отображение текста вопросов и пояснений.', text)
        self.assertIn('Бионическое чтение выделяет начало слов жирным', text)
        self.assertEqual(button_texts, ['✅ Обычный', 'Бионическое чтение'])
        self.assertEqual(callback_data, ['readingmode:set:normal', 'readingmode:set:bionic'])

    def test_reading_mode_keyboard_marks_only_current_mode(self):
        normal_keyboard = main.build_reading_mode_keyboard('normal')
        bionic_keyboard = main.build_reading_mode_keyboard('bionic')

        normal_texts = [row[0].text for row in normal_keyboard.inline_keyboard]
        bionic_texts = [row[0].text for row in bionic_keyboard.inline_keyboard]

        self.assertEqual(normal_texts, ['✅ Обычный', 'Бионическое чтение'])
        self.assertEqual(bionic_texts, ['Обычный', '✅ Бионическое чтение'])
        self.assertEqual(sum(text.startswith('✅') for text in normal_texts), 1)
        self.assertEqual(sum(text.startswith('✅') for text in bionic_texts), 1)

    def test_reading_mode_callback_confirmations_and_change_mode_button(self):
        context = self._context()
        user = SimpleNamespace(id=1, username='u', first_name='f', last_name='l')

        saved_modes = iter(['bionic', 'normal'])

        async def fake_run_db_task(func, *args, **kwargs):
            if func.__name__ == '_save_mode':
                return next(saved_modes)
            return 'normal'

        bionic_query = SimpleNamespace(data='readingmode:set:bionic', answer=AsyncMock(), edit_message_text=AsyncMock())
        normal_query = SimpleNamespace(data='readingmode:set:normal', answer=AsyncMock(), edit_message_text=AsyncMock())

        with patch('app.main._run_db_task', side_effect=fake_run_db_task):
            asyncio.run(main.reading_mode_callback(SimpleNamespace(callback_query=bionic_query, effective_user=user), context))
            asyncio.run(main.reading_mode_callback(SimpleNamespace(callback_query=normal_query, effective_user=user), context))

        self.assertEqual(bionic_query.edit_message_text.call_args.args[0], 'Режим чтения обновлён: Бионическое чтение')
        self.assertEqual(normal_query.edit_message_text.call_args.args[0], 'Режим чтения обновлён: Обычный')
        bionic_keyboard = bionic_query.edit_message_text.call_args.kwargs['reply_markup']
        normal_keyboard = normal_query.edit_message_text.call_args.kwargs['reply_markup']
        self.assertEqual(bionic_keyboard.inline_keyboard[0][0].text, 'Изменить режим')
        self.assertEqual(bionic_keyboard.inline_keyboard[0][0].callback_data, 'readingmode:menu')
        self.assertEqual(normal_keyboard.inline_keyboard[0][0].text, 'Изменить режим')
        self.assertEqual(normal_keyboard.inline_keyboard[0][0].callback_data, 'readingmode:menu')

    def test_reading_mode_change_button_reopens_selection_with_selected_state(self):
        context = self._context()
        user = SimpleNamespace(id=1, username='u', first_name='f', last_name='l')
        query = SimpleNamespace(data='readingmode:menu', answer=AsyncMock(), edit_message_text=AsyncMock())

        async def fake_run_db_task(func, *args, **kwargs):
            return 'bionic'

        with patch('app.main._run_db_task', side_effect=fake_run_db_task):
            asyncio.run(main.reading_mode_callback(SimpleNamespace(callback_query=query, effective_user=user), context))

        text = query.edit_message_text.call_args.args[0]
        keyboard = query.edit_message_text.call_args.kwargs['reply_markup']
        button_texts = [row[0].text for row in keyboard.inline_keyboard]

        self.assertIn('Текущий режим: Бионическое чтение', text)
        self.assertIn('Режим влияет на отображение текста вопросов и пояснений.', text)
        self.assertEqual(button_texts, ['Обычный', '✅ Бионическое чтение'])

    def test_bionic_rendering_still_applies_to_reading_mode_text(self):
        rendered = main.render_reading_mode_text('Привет, мир!', 'bionic')

        self.assertIn('<b>Пр</b>ивет', rendered)
        self.assertIn('мир!', rendered)

    def test_hide_menu_removes_reply_keyboard_without_visible_message(self):
        removal_message = SimpleNamespace(delete=AsyncMock(), message_id=99)
        message = SimpleNamespace(
            reply_text=AsyncMock(return_value=removal_message),
            delete=AsyncMock(),
            message_id=10,
        )
        update = SimpleNamespace(message=message)

        asyncio.run(main.hide_menu_button_handler(update, self._context()))

        message.reply_text.assert_awaited_once()
        self.assertEqual(message.reply_text.call_args.kwargs['text'], '\u2060')
        self.assertIsInstance(message.reply_text.call_args.kwargs['reply_markup'], main.ReplyKeyboardRemove)
        removal_message.delete.assert_awaited_once()
        message.delete.assert_awaited_once()

    def test_reading_mode_callback_menu_and_set(self):
        context = self._context()
        user = SimpleNamespace(id=1, username='u', first_name='f', last_name='l')
        menu_query = SimpleNamespace(data='readingmode:menu', answer=AsyncMock(), edit_message_text=AsyncMock())
        set_query = SimpleNamespace(data='readingmode:set:normal', answer=AsyncMock(), edit_message_text=AsyncMock())
        menu_update = SimpleNamespace(callback_query=menu_query, effective_user=user)
        set_update = SimpleNamespace(callback_query=set_query, effective_user=user)

        async def fake_run_db_task(func, *args, **kwargs):
            if func.__name__ == '_load_current_mode':
                return 'normal'
            if func.__name__ == '_save_mode':
                return 'normal'
            return None

        with patch('app.main._run_db_task', side_effect=fake_run_db_task), patch('app.main.logger.info') as info_log:
            asyncio.run(main.reading_mode_callback(menu_update, context))
            asyncio.run(main.reading_mode_callback(set_update, context))

        menu_query.answer.assert_awaited()
        set_query.answer.assert_awaited()
        menu_query.edit_message_text.assert_awaited()
        set_query.edit_message_text.assert_awaited()
        logged = " ".join(str(call.args[2]) for call in info_log.call_args_list if len(call.args) >= 3 and call.args[0] == "%s %s")
        self.assertIn("handler=reading_mode_callback", logged)
        self.assertIn("callback_prefix=readingmode", logged)

    def test_quiz_mode_callback_branches_do_not_raise_nameerror_and_render_next_step(self):
        context = self._context()

        categories = [{'id': 1, 'name': 'Cat'}]
        async def fake_run_db_task(func, *args, **kwargs):
            return categories

        with patch('app.main._run_db_task', side_effect=fake_run_db_task):
            single_query = SimpleNamespace(data='qzmode:single', answer=AsyncMock(), edit_message_text=AsyncMock())
            single_update = SimpleNamespace(callback_query=single_query, effective_user=SimpleNamespace(id=1))
            asyncio.run(main.quiz_mode_callback(single_update, context))

            all_query = SimpleNamespace(data='qzmode:all', answer=AsyncMock(), edit_message_text=AsyncMock())
            all_update = SimpleNamespace(callback_query=all_query, effective_user=SimpleNamespace(id=1))
            asyncio.run(main.quiz_mode_callback(all_update, context))

            selected_mix_query = SimpleNamespace(data='qzmode:selected_mix', answer=AsyncMock(), edit_message_text=AsyncMock())
            selected_mix_update = SimpleNamespace(callback_query=selected_mix_query, effective_user=SimpleNamespace(id=1))
            asyncio.run(main.quiz_mode_callback(selected_mix_update, context))

        single_query.answer.assert_awaited()
        all_query.answer.assert_awaited()
        selected_mix_query.answer.assert_awaited()
        single_query.edit_message_text.assert_awaited()
        all_query.edit_message_text.assert_awaited()
        selected_mix_query.edit_message_text.assert_awaited()
        single_query.edit_message_text.assert_awaited_with(
            "Выберите категорию:",
            reply_markup=main.build_category_keyboard(categories),
        )
        all_query.edit_message_text.assert_awaited_with(
            "Выберите количество вопросов:",
            reply_markup=main.build_question_count_keyboard("qcntall"),
        )
        selected_mix_query.edit_message_text.assert_awaited_with(
            "Выберите темы для микса:",
            reply_markup=main.build_selected_mix_keyboard(categories, set()),
        )

    def test_static_guard_enforces_run_db_task_and_no_direct_get_connection_in_target_async_functions(self):
        source = inspect.getsource(main)
        module_ast = ast.parse(source)
        target_names = [
            'quiz_mode_callback',
            'send_current_question_to_chat',
            'web_app_data_handler',
            'difficulty_mode_callback',
            'mix_selection_callback',
            'start_mix_quiz',
            'next_callback',
        ]

        async_nodes = {
            node.name: node
            for node in module_ast.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name in target_names
        }
        self.assertEqual(set(target_names), set(async_nodes.keys()))

        def _is_get_connection_with(node: ast.With) -> bool:
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == 'get_connection':
                    return True
            return False

        def _walk_excluding_nested_defs(root: ast.AST):
            stack = [root]
            while stack:
                node = stack.pop()
                yield node
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                        continue
                    stack.append(child)

        for fn in target_names:
            fn_node = async_nodes[fn]

            has_run_db_task_await = False
            direct_get_connection_with_count = 0

            for node in _walk_excluding_nested_defs(fn_node):
                if isinstance(node, ast.Await):
                    call = node.value
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == '_run_db_task':
                        has_run_db_task_await = True

                if isinstance(node, ast.With) and _is_get_connection_with(node):
                    direct_get_connection_with_count += 1

            self.assertTrue(
                has_run_db_task_await,
                msg=f"{fn} must call await _run_db_task(...)",
            )
            self.assertEqual(
                0,
                direct_get_connection_with_count,
                msg=f"{fn} contains direct with get_connection(...) outside nested worker functions",
            )

    def test_static_guard_no_unbound_latency_reads_in_classic_callbacks(self):
        source = inspect.getsource(main)
        module_ast = ast.parse(source)
        target_names = {
            'quiz_mode_callback',
            'question_count_callback',
            'question_count_mix_callback',
            'question_count_selected_mix_callback',
            'difficulty_mode_callback',
            'difficulty_mode_all_callback',
            'difficulty_mode_selected_mix_callback',
            'category_callback',
            'answer_callback',
            'next_callback',
            'reading_mode_callback',
        }

        for node in module_ast.body:
            if not isinstance(node, ast.AsyncFunctionDef) or node.name not in target_names:
                continue

            assigned = {arg.arg for arg in node.args.args}
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id == 'latency' and isinstance(sub.ctx, ast.Store):
                    assigned.add('latency')

            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id == 'latency' and isinstance(sub.ctx, ast.Load):
                    self.assertIn(
                        'latency',
                        assigned,
                        msg=f"{node.name} reads latency without assigning/passing it",
                    )

    def test_static_guard_timed_telegram_calls_require_latency_binding(self):
        source = inspect.getsource(main)
        module_ast = ast.parse(source)

        for node in module_ast.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            uses_timed_latency = False
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                if not isinstance(sub.func, ast.Name) or sub.func.id != '_timed_telegram_api_call':
                    continue
                if not sub.args:
                    continue
                first_arg = sub.args[0]
                if isinstance(first_arg, ast.Name) and first_arg.id == 'latency':
                    uses_timed_latency = True
                    break
            if not uses_timed_latency:
                continue

            has_latency_arg = any(arg.arg == 'latency' for arg in node.args.args)
            has_latency_store = any(
                isinstance(sub, ast.Name) and sub.id == 'latency' and isinstance(sub.ctx, ast.Store)
                for sub in ast.walk(node)
            )
            self.assertTrue(
                has_latency_arg or has_latency_store,
                msg=f"{node.name} uses _timed_telegram_api_call(latency, ...) without defining latency",
            )



if __name__ == '__main__':
    unittest.main()
