"""Classic study navigation over the same reviewed scopes and quiz service as web."""
from __future__ import annotations

from contextlib import closing
import hashlib
from html import escape
import json
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from app import bot_runtime
from app.db import create_or_load_user, get_connection
from app.literature_navigation import module_label
from app.quiz_service import QuizSetupError, prepare_quiz, start_confirmed_quiz
from app.study_navigation import question_scopes

STATE = 'study_quiz_navigation'
PAGE_SIZE = 5
PATTERN = re.compile(r'^qn:(?:nav:(?:root|[a-f0-9]{12}):\d{1,3}|pick:[a-f0-9]{12}|done|clear|difficulty:[a-f0-9]{12}(?::(?:any|easy|medium|hard))?|start:[a-f0-9]{12}:(?:5|10|15|all):(?:any|easy|medium|hard)|replace:[a-f0-9]{12}:(?:5|10|15|all):(?:any|easy|medium|hard):[1-9][0-9]{0,18})$')


def _token(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()[:12]


def _index(navigation):
    nodes, choices = {}, {}
    for discipline in navigation:
        cid = discipline['category_id']
        whole = 'category:' + str(cid)
        choices[_token(whole)] = {'id': whole, 'category_id': cid, 'title': discipline['title'],
                                 'topics': [topic['id'] for topic in discipline['topics']]}
        for module in discipline['modules']:
            for topic in discipline['topics']:
                path = (module, str(cid), topic['id'])
                labels = (module_label(module), discipline['title'], topic['title'])
                for depth in (1, 2):
                    key = _token(path[:depth])
                    node = {'path': path[:depth], 'labels': labels[:depth]}
                    if key in nodes and nodes[key]['path'] != node['path']:
                        raise ValueError('quiz_navigation_collision')
                    nodes[key] = node
                value = 'topic:' + topic['id']
                choices[_token(value)] = {'id': value, 'category_id': cid, 'title': topic['title'],
                                          'topics': [topic['id']]}
    return nodes, choices


def _ordered(node):
    module = node['path'][0]
    return (0, int(module[6:]), node['labels'][1:]) if re.fullmatch(r'module[1-9][0-9]*', module) else (1, 0, node['labels'])


def _render(navigation, state):
    nodes, choices = _index(navigation)
    node = nodes.get(state.get('path')) if state.get('path') != 'root' else {'path': (), 'labels': ()}
    if node is None:
        return None
    path, labels = node['path'], node['labels']
    selected = set(state.get('selected', [])) & choices.keys()
    text = ['<b>Выбор вопросов</b>', ' → '.join(escape(value) for value in labels)]
    text.append(('Выберите модуль.', 'Выберите дисциплину.', 'Выберите всю дисциплину или конкретную тему.')[len(path)])
    rows = []
    if path:
        parent = path[:-1]
        siblings = sorted((value for value in nodes.values() if len(value['path']) == len(path)
                           and value['path'][:-1] == parent), key=_ordered)
        parent_page = next(index for index, value in enumerate(siblings) if value['path'] == path) // PAGE_SIZE
        rows.append([InlineKeyboardButton('Назад', callback_data=f"qn:nav:{_token(parent) if parent else 'root'}:{parent_page}")])
    if len(path) < 2:
        children = sorted((value for value in nodes.values() if len(value['path']) == len(path) + 1
                           and value['path'][:len(path)] == path), key=_ordered)
        actions = [(value['labels'][-1], 'qn:nav:' + _token(value['path']) + ':0') for value in children]
    else:
        discipline = next(item for item in navigation if str(item['category_id']) == path[1])
        options = [('Вся дисциплина', _token('category:' + path[1]))]
        options += [(topic['title'], _token('topic:' + topic['id'])) for topic in discipline['topics']]
        actions = [(('✓ ' if key in selected else '') + title, 'qn:pick:' + key) for title, key in options]
    page = state.get('page', 0)
    if page < 0 or (page and page * PAGE_SIZE >= len(actions)):
        return None
    for title, action in actions[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
        text.append(escape(title))
        rows.append([InlineKeyboardButton(title if len(title) <= 48 else title[:47] + '…', callback_data=action)])
    arrows = []
    if page:
        arrows.append(InlineKeyboardButton('← Предыдущие', callback_data=f"qn:nav:{state['path']}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < len(actions):
        arrows.append(InlineKeyboardButton('Следующие →', callback_data=f"qn:nav:{state['path']}:{page + 1}"))
    if arrows:
        rows.append(arrows)
    if state['mode'] == 'selected_mix':
        text.append(f'Выбрано: {len(selected)}. Выбор сохраняется между модулями.')
        if selected:
            rows.append([InlineKeyboardButton('Готово — выбрать количество', callback_data='qn:done')])
            rows.append([InlineKeyboardButton('Сбросить выбор', callback_data='qn:clear')])
    if not actions:
        text.append('Вопросов пока нет.')
    return '\n'.join(value for value in text if value), InlineKeyboardMarkup(rows)


def _payload(navigation, mode, selected):
    if mode == 'all':
        return {'quiz_mode': 'all', 'category_ids': []}
    _, choices = _index(navigation)
    if not selected or any(key not in choices for key in selected):
        raise QuizSetupError('invalid_setup')
    items = [choices[key] for key in selected]
    payload = {'quiz_mode': mode, 'category_ids': list(dict.fromkeys(item['category_id'] for item in items))}
    if any(item['id'].startswith('topic:') for item in items):
        payload['topic_ids'] = list(dict.fromkeys(topic for item in items for topic in item['topics']))
    return payload


def _counts(navigation, state):
    _payload(navigation, state['mode'], state['selected'])
    difficulty = state.get('difficulty', 'any')
    key = _token([state['mode'], sorted(state['selected']), difficulty])
    state['pending'] = key
    rows = [[InlineKeyboardButton(label, callback_data=f'qn:start:{key}:{count}:{difficulty}')]
            for count, label in (('5', '5'), ('10', '10'), ('15', '15'), ('all', 'Все доступные'))]
    rows.append([InlineKeyboardButton('Изменить сложность', callback_data=f'qn:difficulty:{key}')])
    if state['mode'] != 'all':
        rows.append([InlineKeyboardButton('Назад к выбору', callback_data=f"qn:nav:{state['path']}:{state['page']}")])
    return 'Выберите количество вопросов.\nСложность: ' + {'any': 'любая', 'easy': 'базовые', 'medium': 'средние', 'hard': 'сложные'}[difficulty], InlineKeyboardMarkup(rows)


def _read(settings):
    with closing(get_connection(settings.db_path)) as conn:
        return question_scopes(conn)[0]


async def begin_study_quiz(query, context, mode, navigation):
    if query.message is None or query.message.chat.type != 'private':
        await query.edit_message_text('Откройте викторину в личном чате с ботом.')
        return
    from app.classic_quiz_handlers import CONFIRMED_REPLACEMENT_KEY
    state = {'mode': mode, 'path': 'root', 'page': 0, 'selected': [], 'difficulty': 'any',
             'replace_for': context.user_data.get(CONFIRMED_REPLACEMENT_KEY)}
    context.user_data[STATE] = state
    view = _counts(navigation, state) if mode == 'all' else _render(navigation, state)
    await query.edit_message_text(view[0], reply_markup=view[1], parse_mode='HTML')


def _start(settings, tg_user, state, count, difficulty, expected):
    with closing(get_connection(settings.db_path)) as conn, conn:
        user = create_or_load_user(conn, tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name)
        actor = int(user['id'])
        navigation = question_scopes(conn)[0]
        payload = {**_payload(navigation, state['mode'], state['selected']),
                   'question_count': None if count == 'all' else int(count), 'difficulty': difficulty,
                   'content_kinds': ['theory', 'glossary', 'case']}
        prepared = prepare_quiz(conn, payload, actor_user_id=actor)
        active = conn.execute("SELECT id FROM quiz_sessions WHERE user_id=? AND status='in_progress' ORDER BY id DESC LIMIT 1", (actor,)).fetchone()
        if active is not None and expected is None:
            return {'confirmation': int(active[0])}
        payload.update(replace_active=expected is not None, expected_session_id=expected)
        return start_confirmed_quiz(conn, actor_user_id=actor, prepared=prepared, payload=payload)


async def study_quiz_callback(update, context):
    query, user = update.callback_query, update.effective_user
    if query is None or user is None or query.message is None:
        return
    await query.answer()
    if query.message.chat.type != 'private':
        await query.edit_message_text('Откройте викторину в личном чате с ботом.')
        return
    data = query.data or ''
    state = context.user_data.get(STATE)
    if PATTERN.fullmatch(data) is None or not state or state.get('mode') not in {'single', 'selected_mix', 'all'}:
        await query.edit_message_text('Выбор устарел. Откройте /quiz снова.')
        return
    settings = context.application.bot_data['settings']
    navigation = await bot_runtime.run_db_task(_read, settings)
    _, choices = _index(navigation)
    parts = data.split(':')
    action = parts[1]
    try:
        if state['mode'] == 'all' and action not in {'difficulty', 'start', 'replace'}:
            raise QuizSetupError('invalid_setup')
        if action == 'nav':
            state.update(path=parts[2], page=int(parts[3]))
            state.pop('pending', None)
            view = _render(navigation, state)
        elif action in {'pick', 'clear'}:
            selected = set(state['selected'])
            if action == 'clear':
                selected.clear()
            else:
                choice = choices.get(parts[2])
                if choice is None:
                    raise QuizSetupError('invalid_setup')
                if state['mode'] == 'single':
                    selected = {parts[2]}
                elif parts[2] in selected:
                    selected.remove(parts[2])
                else:
                    selected = {key for key in selected if key in choices and (
                        choices[key]['category_id'] != choice['category_id'] or
                        not (choice['id'].startswith('category:') or choices[key]['id'].startswith('category:')))}
                    selected.add(parts[2])
            state['selected'] = sorted(selected)
            state.pop('pending', None)
            view = _counts(navigation, state) if state['mode'] == 'single' and selected else _render(navigation, state)
        elif action == 'done':
            view = _counts(navigation, state)
        else:
            key = _token([state['mode'], sorted(state['selected']), state.get('difficulty', 'any')])
            if parts[2] != state.get('pending') or parts[2] != key:
                raise QuizSetupError('invalid_setup')
            if action == 'difficulty':
                if len(parts) == 4:
                    state['difficulty'] = parts[3]
                    view = _counts(navigation, state)
                else:
                    view = ('Выберите сложность:', InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f'qn:difficulty:{key}:{value}')]
                        for value, label in (('any', 'Любая'), ('easy', 'Базовые'), ('medium', 'Средние'), ('hard', 'Сложные'))]))
            else:
                count, difficulty = parts[3:5]
                if difficulty != state.get('difficulty', 'any'):
                    raise QuizSetupError('invalid_setup')
                expected = int(parts[5]) if action == 'replace' else state.get('replace_for')
                snapshot = {**state, 'selected': list(state['selected'])}
                result = await bot_runtime.run_db_task(_start, settings, user, snapshot, count, difficulty, expected)
                if 'confirmation' in result:
                    sid = result['confirmation']
                    view = ('Есть незавершённый квиз. Заменить его новой попыткой? Сохранённые ответы останутся в истории.',
                        InlineKeyboardMarkup([[InlineKeyboardButton('Заменить и начать', callback_data=f'qn:replace:{key}:{count}:{difficulty}:{sid}')],
                                              [InlineKeyboardButton('Отмена — продолжить текущий', callback_data=f'quizresume:{sid}')]]))
                else:
                    from app.classic_quiz_handlers import send_current_question, CONFIRMED_REPLACEMENT_KEY
                    context.user_data.pop(STATE, None)
                    context.user_data.pop(CONFIRMED_REPLACEMENT_KEY, None)
                    await send_current_question(query, settings, result['session']['session_id'], context=context)
                    return
        if view is None:
            raise QuizSetupError('invalid_setup')
    except QuizSetupError as error:
        if str(error) == 'no_questions':
            text, keyboard = _counts(navigation, state)
            await query.edit_message_text('По выбранным темам и сложности вопросов пока нет. Измените сложность или выбор.\n\n' + text,
                                          reply_markup=keyboard, parse_mode='HTML')
        else:
            await query.edit_message_text('Выбор или попытка изменились. Откройте /quiz снова.')
        return
    await query.edit_message_text(view[0], reply_markup=view[1], parse_mode='HTML')
