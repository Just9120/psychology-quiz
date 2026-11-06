import asyncio
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import classic_quiz_handlers as classic, study_quiz_chat as chat
from app.attempt_content import get_attempt_content
from app.db import get_connection, create_or_load_user, start_quiz_session, store_session_questions
from app.study_navigation import question_scopes
from tests.test_study_navigation import mapped, TOPIC
from tests.test_attempt_content import bank, make_attempt


USER = SimpleNamespace(id=42, username=None, first_name='Synthetic', last_name=None)


def query(data):
    return SimpleNamespace(data=data, message=SimpleNamespace(chat=SimpleNamespace(type='private')),
                           answer=AsyncMock(), edit_message_text=AsyncMock())


@pytest.fixture
def flow(mapped, monkeypatch):
    with closing(get_connection(str(mapped))) as conn:
        navigation = question_scopes(conn)[0]
    settings = SimpleNamespace(db_path=str(mapped))
    context = SimpleNamespace(user_data={}, application=SimpleNamespace(bot_data={'settings': settings}))
    sender = AsyncMock()
    monkeypatch.setattr(classic, 'send_current_question', sender)
    return SimpleNamespace(db=mapped, navigation=navigation, context=context, sender=sender)


def begin(flow, mode='single'):
    first = query('qzmode:' + mode)
    asyncio.run(chat.begin_study_quiz(first, flow.context, mode, flow.navigation))
    return first


def click(flow, data, user=USER):
    callback = query(data)
    asyncio.run(chat.study_quiz_callback(SimpleNamespace(callback_query=callback, effective_user=user), flow.context))
    return callback


def buttons(callback):
    return [button for row in callback.edit_message_text.call_args.kwargs['reply_markup'].inline_keyboard for button in row]


def pick_topic(flow):
    click(flow, 'qn:nav:' + chat._token(('module2',)) + ':0')
    choice = click(flow, 'qn:nav:' + chat._token(('module2', '1')) + ':0')
    assert 'Уточнение запроса' in choice.edit_message_text.call_args.args[0]
    return click(flow, 'qn:pick:' + chat._token('topic:' + TOPIC))


def test_real_navigation_starts_only_reviewed_topic_and_replay_cannot_create_a_second_attempt(flow):
    root = begin(flow)
    assert 'Модуль 2' in root.edit_message_text.call_args.args[0]
    count = pick_topic(flow)
    with closing(get_connection(str(flow.db))) as conn:
        assert conn.execute('SELECT COUNT(*) FROM quiz_sessions').fetchone()[0] == 0
    action = next(button.callback_data for button in buttons(count) if button.text == '5')
    click(flow, action)
    sid = flow.sender.call_args.args[2]
    with closing(get_connection(str(flow.db))) as conn:
        assert conn.execute('SELECT user_id FROM quiz_sessions WHERE id=?', (sid,)).fetchone()[0] == 1
        assert [row[0] for row in conn.execute('SELECT question_id FROM quiz_session_questions WHERE session_id=?', (sid,))] == [1]
    replay = click(flow, action)
    assert 'устарел' in replay.edit_message_text.call_args.args[0]
    with closing(get_connection(str(flow.db))) as conn:
        assert conn.execute('SELECT COUNT(*) FROM quiz_sessions').fetchone()[0] == 1


def test_mix_keeps_topics_across_modules_and_all_difficulty_controls_remain_functional(flow):
    begin(flow, 'selected_mix')
    pick_topic(flow)
    click(flow, 'qn:nav:' + chat._token(('unmapped',)) + ':0')
    click(flow, 'qn:nav:' + chat._token(('unmapped', '2')) + ':0')
    mixed = click(flow, 'qn:pick:' + chat._token('topic:unclassified:2'))
    assert 'Выбрано: 2' in mixed.edit_message_text.call_args.args[0]
    counts = click(flow, 'qn:done')
    old_action = next(button.callback_data for button in buttons(counts) if button.text == '5')
    key = flow.context.user_data[chat.STATE]['pending']
    click(flow, f'qn:difficulty:{key}:hard')
    assert 'изменились' in click(flow, old_action).edit_message_text.call_args.args[0]
    key = flow.context.user_data[chat.STATE]['pending']
    empty = click(flow, f'qn:start:{key}:5:hard')
    assert 'вопросов пока нет' in empty.edit_message_text.call_args.args[0]
    assert not flow.sender.called
    key = flow.context.user_data[chat.STATE]['pending']
    counts = click(flow, f'qn:difficulty:{key}:any')
    click(flow, next(button.callback_data for button in buttons(counts) if button.text == 'Все доступные'))
    sid = flow.sender.call_args.args[2]
    with closing(get_connection(str(flow.db))) as conn:
        assert {row[0] for row in conn.execute('SELECT question_id FROM quiz_session_questions WHERE session_id=?', (sid,))} == {1, 2}


def test_replacement_is_explicit_actor_bound_and_preserves_saved_edition(flow):
    with closing(get_connection(str(flow.db))) as conn, conn:
        sid = make_attempt(conn)
        original = get_attempt_content(conn, sid, 1)
        other = create_or_load_user(conn, 99, None, 'Other', None)
        foreign = start_quiz_session(conn, other['id'], None)
        store_session_questions(conn, foreign, [2])
    begin(flow)
    counts = pick_topic(flow)
    start = next(button.callback_data for button in buttons(counts) if button.text == '5')
    confirmation = click(flow, start)
    replace = next(button.callback_data for button in buttons(confirmation) if button.text == 'Заменить и начать')
    assert next(button.callback_data for button in buttons(confirmation) if 'Отмена' in button.text) == f'quizresume:{sid}'
    forged = replace.rsplit(':', 1)[0] + ':' + str(foreign)
    assert 'изменились' in click(flow, forged).edit_message_text.call_args.args[0]
    with closing(get_connection(str(flow.db))) as conn:
        assert conn.execute('SELECT status FROM quiz_sessions WHERE id=?', (sid,)).fetchone()[0] == 'in_progress'
        assert get_attempt_content(conn, sid, 1) == original
    click(flow, replace)
    with closing(get_connection(str(flow.db))) as conn:
        assert conn.execute('SELECT status FROM quiz_sessions WHERE id=?', (sid,)).fetchone()[0] == 'abandoned'
        assert conn.execute('SELECT status FROM quiz_sessions WHERE id=?', (foreign,)).fetchone()[0] == 'in_progress'
        assert get_attempt_content(conn, sid, 1) == original
    click(flow, replace)
    with closing(get_connection(str(flow.db))) as conn:
        assert conn.execute('SELECT COUNT(*) FROM quiz_sessions WHERE user_id=1').fetchone()[0] == 2


def test_group_and_unknown_callback_do_not_touch_database(flow, monkeypatch):
    def forbidden(*args):
        raise AssertionError('Rejected callback must not read or write DB')
    monkeypatch.setattr(chat, '_read', forbidden)
    begin(flow)
    unknown = click(flow, 'qn:pick:not-valid')
    assert 'устарел' in unknown.edit_message_text.call_args.args[0]
    callback = query('qn:done')
    callback.message.chat.type = 'group'
    asyncio.run(chat.study_quiz_callback(SimpleNamespace(callback_query=callback, effective_user=USER), flow.context))
    assert 'личном чате' in callback.edit_message_text.call_args.args[0]


def test_rendered_actions_are_short_and_registered_under_dedicated_prefix(flow):
    for mode in ('single', 'selected_mix', 'all'):
        root = begin(flow, mode)
        for button in buttons(root):
            assert len(button.callback_data.encode()) <= 64
            assert chat.PATTERN.fullmatch(button.callback_data)
