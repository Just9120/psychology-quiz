"""Classic Telegram UI for the same durable glossary used by web clients."""
import asyncio
from contextvars import ContextVar
from functools import wraps
import time
from app.handler_latency import HandlerLatency
from html import escape
import logging
from types import SimpleNamespace

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app import glossary_service as service
from app.database import DATABASE_ERRORS
from app.glossary import (
    GLOSSARY_QUIZ_SESSION_KEY, GLOSSARY_UNAVAILABLE_TEXT,
    build_glossary_answer_keyboard, build_glossary_count_keyboard, build_glossary_feedback_keyboard,
    build_glossary_topics_keyboard, callback_token_to_topic_id,
    format_glossary_count_text, format_glossary_question_text, format_glossary_result_text,
    format_glossary_topics_text, load_glossary_entries, topic_title,
)
from app.miniapp_entrypoint_handlers import MINI_APP_BUTTON_TEXT
from app.miniapp_glossary import run

logger = logging.getLogger(__name__)
START_QUIZ_BUTTON_TEXT = '🎯 Начать'
READING_MODE_BUTTON_TEXT = '👁 Чтение'
GLOSSARY_BUTTON_TEXT = '📚 Глоссарий'
HIDE_MENU_BUTTON_TEXT = '🙈 Скрыть меню'
CLASSIC_REPLY_NEXT_TEXT = 'Далее'
CLASSIC_REPLY_STATE_KEY = 'classic_reply_keyboard_state'


_latency = ContextVar('glossary_latency', default=None)


def _measure(handler):
    @wraps(handler)
    async def wrapped(update, context):
        latency = HandlerLatency(handler=handler.__name__, callback_prefix='gls')
        token = _latency.set(latency)
        latency.start()
        try:
            return await handler(update, context)
        except Exception:
            latency.set_error('handler_failed')
            raise
        finally:
            latency.summary()
            _latency.reset(token)
    return wrapped


async def _reply(message, *args, **kwargs):
    start = time.perf_counter()
    try:
        return await message.reply_text(*args, **kwargs)
    finally:
        if _latency.get():
            _latency.get().add_telegram_api(start, api_kind='message_send')


def get_main_menu_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton(START_QUIZ_BUTTON_TEXT), KeyboardButton(MINI_APP_BUTTON_TEXT)],
        [KeyboardButton(READING_MODE_BUTTON_TEXT), KeyboardButton(GLOSSARY_BUTTON_TEXT)],
        [KeyboardButton('ℹ️ Помощь')], [KeyboardButton(HIDE_MENU_BUTTON_TEXT)],
    ], resize_keyboard=True, is_persistent=True)


async def _operation(update, context, operation, *args, **kwargs):
    if update.effective_user is None:
        return None
    try:
        started = time.perf_counter()
        try:
            return await asyncio.to_thread(run, context.application.bot_data['settings'].db_path,
                                           update.effective_user.id, operation, *args, **kwargs)
        finally:
            if _latency.get(): _latency.get().add_db(started)
    except service.GlossaryError as error:
        if _latency.get(): _latency.get().set_error(error.code)
        await _reply(update.effective_message, 'Тест изменился. Откройте /glossary, чтобы восстановить сохранённое состояние.')
    except DATABASE_ERRORS as error:
        if _latency.get(): _latency.get().set_error('database_unavailable')
        logger.warning('glossary_database_unavailable type=%s', type(error).__name__)
        await _reply(update.effective_message, GLOSSARY_UNAVAILABLE_TEXT)
    return None


async def _render(message, context, state):
    if state is None:
        return
    # Only routing/display coordinates are transient; no answers or score live here.
    context.user_data.pop(CLASSIC_REPLY_STATE_KEY, None)
    if state['state'] == 'idle':
        context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
        await _reply(message, format_glossary_topics_text(), reply_markup=build_glossary_topics_keyboard(), parse_mode='HTML')
        return
    sid = state['session_id']
    if state['state'] == 'completed':
        context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton('Пройти ещё раз', callback_data=f'glsq:retry:{sid}')],
            [InlineKeyboardButton('К темам глоссария', callback_data='gls:topics')],
        ])
        await _reply(message, format_glossary_result_text(**state['result']), reply_markup=keyboard, parse_mode='HTML')
        return
    question = state['current_question']
    context.user_data[GLOSSARY_QUIZ_SESSION_KEY] = {'session_id': sid, 'step_id': question['step_id'],
        'status': 'awaiting_next' if state['state'] == 'feedback' else 'awaiting_answer'}
    if state['state'] == 'feedback':
        f = state['feedback']
        text = ('<b>Верно ✅</b>' if f['is_correct'] else '<b>Неверно ❌</b>')
        text += f"\n\n<b>Ваш ответ:</b> {escape(f['selected_option_text'])}"
        if not f['is_correct']:
            text += f"\n<b>Правильный ответ:</b> {escape(f['correct_option_text'])}"
        text += f"\n\n<b>Краткое объяснение:</b> {escape(f['explanation'])}\n\n<b>Прогресс:</b> {f['answered_count']} из {f['total_questions']}"
        await _reply(message, text, reply_markup=build_glossary_feedback_keyboard(True), parse_mode='HTML')
    else:
        display = SimpleNamespace(entry=SimpleNamespace(term=question['term']), options=[item['option_text'] for item in question['options']])
        await _reply(message, format_glossary_question_text(display, question['order_index'], question['total_questions']),
                                 reply_markup=build_glossary_answer_keyboard(display), parse_mode='HTML')


async def glossary_button_handler(update, context):
    await glossary_command(update, context)


@_measure
async def glossary_command(update, context):
    if update.effective_message is None:
        return
    saved = await _operation(update, context, service.state)
    if saved and saved['state'] not in {'idle', 'completed'}:
        await _reply(update.effective_message, 'Продолжаем сохранённый тест по терминам.', reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('Выбрать другую тему', callback_data='gls:topics')]]))
    await _render(update.effective_message, context, saved)


@_measure
async def glossary_callback(update, context):
    query = update.callback_query
    if query is None or not query.data or query.message is None:
        return
    ack = time.perf_counter()
    await query.answer(cache_time=1)
    _latency.get().add_telegram_api(ack, api_kind='callback_ack')
    parts = query.data.split(':')
    if query.data == 'gls:topics':
        context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
        await _reply(query.message, format_glossary_topics_text(), reply_markup=build_glossary_topics_keyboard(), parse_mode='HTML')
    elif query.data == 'gls:resume':
        await _render(query.message, context, await _operation(update, context, service.state))
    elif query.data == 'gls:main':
        context.user_data.pop(GLOSSARY_QUIZ_SESSION_KEY, None)
        await _reply(query.message, 'Главное меню:', reply_markup=get_main_menu_keyboard())
    elif len(parts) == 3 and parts[:2] == ['gls', 'topic']:
        topic = callback_token_to_topic_id(parts[2])
        entries = load_glossary_entries(topic) if topic else None
        if not entries:
            await _reply(query.message, GLOSSARY_UNAVAILABLE_TEXT)
            return
        await _reply(query.message, format_glossary_count_text(topic_title(topic), len(entries)),
            reply_markup=build_glossary_count_keyboard(topic, len(entries)), parse_mode='HTML')
    elif len(parts) in (4, 5) and parts[0] == 'glsq' and parts[1] in {'count', 'replace'}:
        replacement = parts[1] == 'replace'
        if len(parts) != (5 if replacement else 4) or parts[-1] not in {'5', '10', 'all'}:
            return
        topic = callback_token_to_topic_id(parts[-2])
        count = 'all' if parts[-1] == 'all' else int(parts[-1])
        current = await _operation(update, context, service.state)
        if current is None:
            return
        active = current.get('session_id') if current['state'] in {'in_progress', 'feedback'} else None
        if active and not replacement:
            await _reply(query.message, 'Прервать незавершённый тест по терминам и начать новый? Сохранённые ответы не удалятся.',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton('Начать новый тест', callback_data=f'glsq:replace:{active}:{parts[-2]}:{parts[-1]}')],
                    [InlineKeyboardButton('Продолжить прежний', callback_data='gls:resume')],
                ]))
            return
        state = await _operation(update, context, service.start, topic, count,
            expected_session_id=parts[2] if replacement else None, replace_active=replacement)
        await _render(query.message, context, state)
    elif len(parts) == 3 and parts[:2] == ['glsq', 'retry']:
        await _render(query.message, context, await _operation(update, context, service.restart, parts[2]))
    else:
        await _reply(query.message, 'Эта кнопка устарела. Откройте /glossary.')


def parse_glossary_reply_answer_number(text, option_count=4):
    text = text.strip()
    if not text.isdigit() or not 1 <= int(text) <= option_count:
        return None
    return int(text) - 1


@_measure
async def glossary_reply_text_answer_handler(update, context):
    message = update.message
    display = context.user_data.get(GLOSSARY_QUIZ_SESSION_KEY)
    if message is None or not message.text or not display or display.get('status') != 'awaiting_answer':
        return
    selected = parse_glossary_reply_answer_number(message.text)
    if selected is None:
        await _reply(message, 'Выберите вариант числом от 1 до 4.')
        return
    result = await _operation(update, context, service.answer, display['session_id'], selected, display['step_id'])
    if result:
        await _render(message, context, await _operation(update, context, service.state, display['session_id']))


@_measure
async def glossary_reply_text_next_handler(update, context):
    message = update.message
    display = context.user_data.get(GLOSSARY_QUIZ_SESSION_KEY)
    if message is None or not message.text or message.text.strip().lower() != CLASSIC_REPLY_NEXT_TEXT.lower():
        return
    if not display or display.get('status') != 'awaiting_next':
        return
    await _render(message, context, await _operation(update, context, service.advance, display['session_id'], display['step_id']))
