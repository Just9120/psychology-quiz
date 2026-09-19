import asyncio
from dataclasses import replace
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.web_config import WebSettings
from app.web_link_handlers import link_command, confirm_link_callback
from app.web_mail import SmtpMailer
from tests.test_web_auth import web, post, register, login, SETTINGS, EMAIL, ORIGIN
from tests.test_attempt_content import bank


def test_web_quiz_full_flow_retries_and_restart_state(web):
    register(web)
    csrf = login(web)
    assert web.client.get('/web/quiz/state').status_code == 409
    assert post(web, 'identity/new', csrf=csrf).status_code == 200
    assert post(web, 'identity/new', csrf=csrf).status_code == 200
    options = web.client.get('/web/quiz/options').json()['setup_options']
    assert len(options['categories']) == 2
    assert post(web, 'quiz/setup', {'quiz_mode': [], 'category_ids': [], 'question_count':None,'difficulty':'any'}, csrf=csrf).status_code == 400
    setup = post(web, 'quiz/setup', {'quiz_mode':'all','category_ids':[],'question_count':None,'difficulty':'any'}, csrf=csrf)
    assert setup.status_code == 200
    state = setup.json()['runner_state']
    sid = state['session']['session_id']
    for _ in range(2):
        request = {'session_id':sid, 'question_id':state['current_question']['question_id'], 'selected_option_index':0}
        saved = post(web, 'quiz/answer', request, csrf=csrf)
        assert saved.status_code == 200
        payload = saved.json()
        assert payload['submission_status'] == 'accepted'
        assert payload['feedback']['explanation']
        retry = post(web, 'quiz/answer', {**request,'selected_option_index':1}, csrf=csrf).json()
        assert retry['submission_status'] == 'duplicate'
        assert retry['feedback'] == payload['feedback']
        state = payload['runner_state']
    assert state['state'] == 'completed'
    assert web.client.get('/web/quiz/state').json()['runner_state']['result'] == state['result']
    assert post(web, 'link/start', csrf=csrf).status_code == 409


def test_bot_command_requires_private_chat_then_bound_callback(web):
    register(web)
    csrf = login(web)
    token = post(web, 'link/start', csrf=csrf).json()['code']
    user = SimpleNamespace(id=42, username=None, first_name='Original user', last_name=None)
    message = SimpleNamespace(reply_text=AsyncMock())
    context = SimpleNamespace(args=[token], application=SimpleNamespace(bot_data={'web_link_auth':web.auth}))
    update = SimpleNamespace(effective_user=user, effective_chat=SimpleNamespace(type='group'), message=message)
    asyncio.run(link_command(update, context))
    message.reply_text.assert_not_called()
    update.effective_chat.type = 'private'
    asyncio.run(link_command(update, context))
    assert EMAIL in message.reply_text.call_args.args[0]
    keyboard = message.reply_text.call_args.kwargs['reply_markup']
    assert keyboard.inline_keyboard[0][0].callback_data == 'pwa_link:'+token
    assert post(web, 'link/complete', csrf=csrf).status_code == 400
    query = SimpleNamespace(data='pwa_link:'+token, answer=AsyncMock(), edit_message_text=AsyncMock())
    update.callback_query = query
    update.effective_user = SimpleNamespace(id=7)
    asyncio.run(confirm_link_callback(update, context))
    assert post(web, 'link/complete', csrf=csrf).status_code == 400
    update.effective_user = user
    asyncio.run(confirm_link_callback(update, context))
    assert post(web, 'link/complete', csrf=csrf).status_code == 200
    assert web.client.get('/web/auth/me').json()['telegram_linked'] is True


@pytest.mark.parametrize('port', [465,587])
def test_smtp_uses_validated_tls_and_fragment_only_token(port):
    settings = replace(SETTINGS, smtp_port=port)
    client = MagicMock()
    client.__enter__.return_value = client
    constructor = 'smtplib.SMTP_SSL' if port == 465 else 'smtplib.SMTP'
    with patch(constructor, return_value=client) as factory:
        SmtpMailer(settings).send(EMAIL, 'register', 'synthetic-token')
    assert factory.call_args.kwargs['timeout'] == 10
    if port == 465:
        assert factory.call_args.kwargs['context'].check_hostname is True
    else:
        assert client.starttls.call_args.kwargs['context'].check_hostname is True
        names = [call[0] for call in client.method_calls]
        assert names.index('starttls') < names.index('login') < names.index('send_message')
    message = client.send_message.call_args.args[0]
    assert message['To'] == EMAIL and message['From'] == EMAIL
    assert ORIGIN+'/#verify=synthetic-token' in message.get_content()
    assert '?token=' not in message.get_content()


def test_smtp_tls_failure_does_not_authenticate_or_send():
    client = MagicMock()
    client.__enter__.return_value = client
    client.starttls.side_effect = OSError('TLS unavailable')
    with patch('smtplib.SMTP', return_value=client), pytest.raises(OSError):
        SmtpMailer(replace(SETTINGS, smtp_port=587)).send(EMAIL,'recover','synthetic-token')
    client.login.assert_not_called()
    client.send_message.assert_not_called()


def env_settings():
    return {'PWA_ENABLED':'true','PWA_OWNER_EMAIL':EMAIL,'PWA_ORIGIN':ORIGIN,
            'PWA_SMTP_HOST':'smtp.yandex.ru','PWA_SMTP_PORT':'465','PWA_SMTP_USERNAME':EMAIL,
            'PWA_SMTP_PASSWORD':'synthetic','PWA_SMTP_FROM':EMAIL}


@pytest.mark.parametrize('key,value', [('PWA_ORIGIN','http://public.example.test'), ('PWA_ORIGIN',ORIGIN+'/path'),
    ('PWA_ORIGIN','https://user:password@example.test'), ('PWA_ORIGIN',ORIGIN+'?token=secret'),
    ('PWA_OWNER_EMAIL','owner@example.test\r\nBcc: other@example.test'), ('PWA_SMTP_PORT','25'),
    ('PWA_ENABLED','yes'), ('PWA_SMTP_PASSWORD','')])
def test_enabled_config_fails_closed(key,value):
    with patch.dict(os.environ, {**env_settings(),key:value}, clear=True), pytest.raises(RuntimeError):
        WebSettings.from_env()


def test_config_default_off_and_explicit_loopback_exception():
    with patch.dict(os.environ, {}, clear=True):
        assert WebSettings.from_env() is None
    with patch.dict(os.environ, env_settings(), clear=True):
        assert WebSettings.from_env().secure_cookie is True
        assert 'synthetic' not in repr(WebSettings.from_env())
    with patch.dict(os.environ, {**env_settings(),'PWA_ORIGIN':'http://127.0.0.1:5173','PWA_ALLOW_HTTP_LOCALHOST':'true'}, clear=True):
        settings = WebSettings.from_env()
        assert settings.secure_cookie is False
        assert not settings.cookie_name.startswith('__Host-')
    with patch.dict(os.environ, {**env_settings(),'PWA_ORIGIN':'http://public.example.test','PWA_ALLOW_HTTP_LOCALHOST':'true'}, clear=True), pytest.raises(RuntimeError):
        WebSettings.from_env()
