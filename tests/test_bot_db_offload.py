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



if __name__ == '__main__':
    unittest.main()
