from contextlib import closing
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from app.db import get_connection
from app.google_oauth import GoogleOAuthSettings, GoogleOAuthError
from app.owner_google_oauth import OwnerGoogleOAuth
from app.web_auth import AuthError, csrf_token
from tests.test_web_auth import web, bank, register, EMAIL, PASSWORD


@pytest.fixture
def flow(web):
    register(web)
    token = web.auth.login(EMAIL, PASSWORD)
    web.auth.settings = replace(web.auth.settings, google=GoogleOAuthSettings('client', 'synthetic-secret', 'https://pwa.example.test/web/auth/google/callback'))
    oauth = OwnerGoogleOAuth(web.auth)
    # Provider cryptography/protocol is independently verified by signed JWT tests.
    oauth.provider.exchange = lambda *args, **kwargs: {'subject': 'owner-google-sub', 'email': 'different@gmail.test'}
    return SimpleNamespace(web=web, oauth=oauth, token=token)


def begin(flow, purpose='link'):
    result, browser = flow.oauth.begin(purpose, flow.token, csrf_token(flow.token))
    state = parse_qs(urlsplit(result['url']).query)['state'][0]
    return state, browser


def test_google_explicit_owner_link_then_stable_subject_login(flow):
    state, browser = begin(flow)
    with pytest.raises(AuthError, match='invalid_oauth_state'):
        flow.oauth.complete(state, 'x'*43, 'code')
    assert flow.oauth.complete(state, browser, 'code') is None
    with pytest.raises(AuthError, match='invalid_oauth_state'):
        flow.oauth.complete(state, browser, 'code')
    state, browser = begin(flow, 'login')
    token = flow.oauth.complete(state, browser, 'code')
    with flow.web.auth.transaction() as conn:
        account = flow.web.auth.authenticate(conn, token)
        original = flow.web.auth.authenticate(conn, flow.token)
        assert account['id'] == original['id']
        assert conn.execute('SELECT COUNT(*) FROM web_accounts').fetchone()[0] == 1
        assert flow.web.auth.account_state(conn, account, token)['google_linked'] is True


@pytest.mark.parametrize('invalidate', ['logout', 'expire', 'disable', 'recover'])
def test_google_link_revalidates_initiating_owner_session(flow, invalidate):
    state, browser = begin(flow)
    with flow.web.auth.transaction() as conn:
        account = flow.web.auth.authenticate(conn, flow.token)
        if invalidate in {'logout', 'recover'}:
            conn.execute('DELETE FROM web_sessions WHERE account_id=?', (account['id'],))
        elif invalidate == 'disable':
            conn.execute('UPDATE web_accounts SET enabled=0 WHERE id=?', (account['id'],))
        else:
            flow.web.now[0] += 601
    with pytest.raises(AuthError):
        flow.oauth.complete(state, browser, 'code')
    with closing(get_connection(str(flow.web.db))) as conn:
        assert conn.execute('SELECT COUNT(*) FROM web_google_identities').fetchone()[0] == 0


def test_google_does_not_register_or_bind_by_matching_email(flow):
    state, browser = begin(flow, 'login')
    flow.oauth.provider.exchange = lambda *args, **kwargs: {'subject': 'unbound', 'email': EMAIL}
    with pytest.raises(AuthError, match='invalid_credentials'):
        flow.oauth.complete(state, browser, 'code')
    with pytest.raises(AuthError, match='csrf_failed'):
        flow.oauth.begin('link', flow.token, 'forged')
    with pytest.raises(AuthError, match='unauthorized'):
        flow.oauth.begin('link')


def test_google_failed_exchange_consumes_proof_and_unlink_invalidates_link(flow):
    state, browser = begin(flow)
    def fail(*args, **kwargs):
        raise GoogleOAuthError('provider_failed')
    provider = flow.oauth.provider.exchange
    flow.oauth.provider.exchange = fail
    with pytest.raises(AuthError, match='google_login_failed'):
        flow.oauth.complete(state, browser, 'code')
    flow.oauth.provider.exchange = provider
    with pytest.raises(AuthError, match='invalid_oauth_state'):
        flow.oauth.complete(state, browser, 'code')
    state, browser = begin(flow)
    assert flow.oauth.complete(state, browser, 'code') is None
    with flow.web.auth.transaction() as conn:
        account = flow.web.auth.authenticate(conn, flow.token)
        flow.oauth.unlink(conn, account)
    state, browser = begin(flow, 'login')
    with pytest.raises(AuthError, match='invalid_credentials'):
        flow.oauth.complete(state, browser, 'code')


def test_google_api_callback_is_browser_bound_and_leaves_actor_unchanged(flow, monkeypatch):
    from fastapi.testclient import TestClient
    from app.miniapp_fastapi import create_app
    from tests.test_web_auth import ORIGIN, TOKEN
    monkeypatch.setattr('app.google_oauth.GoogleOAuthClient.exchange',
        lambda *args, **kwargs: {'subject': 'api-owner', 'email': 'different@gmail.test'})
    app = create_app(db_path=str(flow.web.db), bot_token=TOKEN, web_settings=flow.web.auth.settings,
                     web_mailer=flow.web.mailbox, web_clock=lambda: flow.web.now[0])
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get('/web/auth/google/available').json()['available'] is False
        client.cookies.set(flow.web.auth.settings.cookie_name, flow.token)
        before = client.get('/web/auth/me').json()
        body = client.post('/web/auth/google/begin', json={'purpose': 'link'},
            headers={'Origin': ORIGIN, 'X-CSRF-Token': before['csrf_token']})
        assert body.status_code == 200
        cookie_header = body.headers['set-cookie'].lower()
        assert 'httponly' in cookie_header and 'secure' in cookie_header and 'samesite=lax' in cookie_header
        state = parse_qs(urlsplit(body.json()['url']).query)['state'][0]
        # A provider navigation does not carry the Strict application cookie.
        client.cookies.delete(flow.web.auth.settings.cookie_name)
        result = client.get('/web/auth/google/callback', params={'state': state, 'code': 'synthetic'},
                            headers={'Sec-Fetch-Site': 'cross-site'}, follow_redirects=False)
        assert result.status_code == 303 and result.headers['location'] == ORIGIN+'/'
        assert result.headers['cache-control'] == 'no-store'
        assert client.get('/web/auth/google/available').json()['available'] is True
        body = client.post('/web/auth/google/begin', json={'purpose': 'login'}, headers={'Origin': ORIGIN})
        state = parse_qs(urlsplit(body.json()['url']).query)['state'][0]
        result = client.get('/web/auth/google/callback', params={'state': state, 'code': 'synthetic'}, follow_redirects=False)
        assert result.status_code == 303
        assert 'samesite=strict' in result.headers['set-cookie'].lower()
        after = client.get('/web/auth/me').json()
        assert after['email'] == before['email'] and after['needs_identity'] == before['needs_identity']
        assert after['google_linked'] is True
        replay = client.get('/web/auth/google/callback', params={'state': state, 'code': 'synthetic'})
        assert replay.status_code == 401 and 'synthetic' not in replay.text
        assert client.post('/web/auth/google/unlink', json={}, headers={'Origin': ORIGIN}).status_code == 403
        assert client.post('/web/auth/google/unlink', json={}, headers={'Origin': ORIGIN, 'X-CSRF-Token': after['csrf_token']}).status_code == 200
        assert client.get('/web/auth/google/available').json()['available'] is False
        assert client.get('/web/auth/me').status_code == 200
        assert client.post('/web/auth/google/begin', json={'purpose':'login'}, headers={'Origin':'https://attacker.test'}).status_code == 403


def test_google_callback_failure_keeps_credentials_out_of_response_and_logs(flow, monkeypatch, caplog):
    import logging
    from fastapi.testclient import TestClient
    from app.miniapp_fastapi import create_app
    from tests.test_web_auth import ORIGIN, TOKEN

    def fail(*args, **kwargs):
        raise RuntimeError('private-provider-code private-cookie synthetic-secret private-owner-identity')

    monkeypatch.setattr('app.owner_google_oauth.OwnerGoogleOAuth.complete', fail)
    app = create_app(db_path=str(flow.web.db), bot_token=TOKEN, web_settings=flow.web.auth.settings,
                     web_mailer=flow.web.mailbox, web_clock=lambda: flow.web.now[0])
    with caplog.at_level(logging.INFO), TestClient(app, base_url=ORIGIN) as client:
        client.cookies.set(flow.oauth.cookie_name, 'private-cookie')
        result = client.get('/web/auth/google/callback?state=private-state&code=private-provider-code',
                            follow_redirects=False)
        assert result.status_code == 500 and result.json() == {'ok': False, 'error': 'internal_error'}
        assert result.headers['cache-control'] == 'no-store'
        assert result.headers['referrer-policy'] == 'no-referrer'
        # Exercise the actual installed Uvicorn filter with its argument layout.
        logging.getLogger('uvicorn.access').info('%s - "%s %s HTTP/%s" %s',
            'private-client-address', 'GET', '/web/auth/google/callback?code=private-provider-code', '1.1', 500)
    assert 'web_oauth_failure type=RuntimeError' in caplog.text
    captured = result.text + caplog.text
    for secret in ('private-provider-code', 'private-cookie', 'synthetic-secret',
                   'private-owner-identity', 'private-state', 'private-client-address'):
        assert secret not in captured


def test_google_configuration_is_default_off_and_requires_complete_secret_config(monkeypatch):
    from app.web_config import WebSettings
    for name, value in {'PWA_ENABLED':'true', 'PWA_ORIGIN':'https://pwa.example.test',
        'PWA_OWNER_EMAIL':EMAIL, 'PWA_SMTP_FROM':EMAIL, 'PWA_SMTP_HOST':'smtp.test',
        'PWA_SMTP_PORT':'465', 'PWA_SMTP_USERNAME':EMAIL, 'PWA_SMTP_PASSWORD':'synthetic'}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv('PWA_GOOGLE_OAUTH_ENABLED', raising=False)
    assert WebSettings.from_env().google is None
    monkeypatch.setenv('PWA_GOOGLE_OAUTH_ENABLED', 'true')
    monkeypatch.delenv('PWA_GOOGLE_CLIENT_ID', raising=False)
    with pytest.raises(RuntimeError, match='PWA_GOOGLE_CLIENT_ID'):
        WebSettings.from_env()
    monkeypatch.setenv('PWA_GOOGLE_CLIENT_ID', 'synthetic-client')
    monkeypatch.setenv('PWA_GOOGLE_CLIENT_SECRET', 'synthetic-secret')
    settings = WebSettings.from_env()
    assert settings.google.redirect_uri == settings.origin+'/web/auth/google/callback'
    assert 'synthetic-secret' not in repr(settings) and 'synthetic-secret' not in repr(settings.google)
