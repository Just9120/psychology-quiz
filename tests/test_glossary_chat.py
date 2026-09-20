import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app import glossary_handlers as chat, glossary_service
from tests.test_attempt_content import bank
from tests.test_glossary_retries import session, call, correct_index


def context(bank):
    return SimpleNamespace(user_data={}, application=SimpleNamespace(bot_data={'settings':SimpleNamespace(db_path=str(bank))}))


def update(text=None, data=None):
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    query = SimpleNamespace(message=message, data=data, answer=AsyncMock()) if data else None
    return SimpleNamespace(message=message, effective_message=message, effective_user=SimpleNamespace(id=42), callback_query=query)


def test_new_chat_context_resumes_web_attempt_and_answer_survives_another_restart(bank, session):
    first, ctx = update(), context(bank)
    ctx.user_data[chat.CLASSIC_REPLY_STATE_KEY] = {'status':'awaiting_answer'}
    asyncio.run(chat.glossary_command(first, ctx))
    pointer = ctx.user_data[chat.GLOSSARY_QUIZ_SESSION_KEY]
    assert pointer == {'session_id':session['session_id'],'step_id':1,'status':'awaiting_answer'}
    assert chat.CLASSIC_REPLY_STATE_KEY not in ctx.user_data
    answer = update(str(correct_index(session) + 1))
    asyncio.run(chat.glossary_reply_text_answer_handler(answer, ctx))
    assert call(bank, glossary_service.state)['feedback']['is_correct']
    second, restarted = update(), context(bank)
    asyncio.run(chat.glossary_command(second, restarted))
    assert restarted.user_data[chat.GLOSSARY_QUIZ_SESSION_KEY]['status'] == 'awaiting_next'
    assert 'Верно' in second.message.reply_text.call_args.args[0]
    asyncio.run(chat.glossary_reply_text_next_handler(update('Далее'), restarted))
    assert call(bank, glossary_service.state)['current_question']['step_id'] == 2


def test_chat_old_confirmation_does_not_replace_a_newer_attempt(bank, session, monkeypatch):
    monkeypatch.setattr(chat, 'callback_token_to_topic_id', lambda _: 'fixture_topic')
    ctx = context(bank)
    prompt = update(data='glsq:count:oep:5')
    asyncio.run(chat.glossary_callback(prompt, ctx))
    assert 'Прервать' in prompt.message.reply_text.call_args.args[0]
    confirmation = prompt.message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data
    replacement = call(bank, glossary_service.start, 'fixture_topic', 5,
                       expected_session_id=session['session_id'], replace_active=True)
    stale = update(data=confirmation)
    asyncio.run(chat.glossary_callback(stale, ctx))
    assert 'Тест изменился' in stale.message.reply_text.call_args.args[0]
    assert call(bank, glossary_service.state)['session_id'] == replacement['session_id']
