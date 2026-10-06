import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.google_oauth import (GoogleOAuthClient, GoogleOAuthError, GoogleOAuthSettings,
                              JWKS_URL, TOKEN_URL, authorization_url, pkce_challenge)

SETTINGS = GoogleOAuthSettings("test-client.apps.googleusercontent.com", "synthetic-secret",
                               "https://pwa.example.test/web/auth/google/callback")


@pytest.fixture
def provider():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid="test-key", alg="RS256", use="sig")
    now = int(time.time())
    claims = {"iss": "https://accounts.google.com", "aud": SETTINGS.client_id,
              "sub": "stable-owner-google-subject", "exp": now+300, "iat": now,
              "nonce": "expected-nonce", "email": "owner@example.test", "email_verified": True}
    client = GoogleOAuthClient(SETTINGS)
    client._keys, client._keys_expire = [public], now+300
    def token(changes=None):
        return jwt.encode({**claims, **(changes or {})}, key, algorithm="RS256", headers={"kid": "test-key"})
    return client, token, public


def test_authorization_uses_pkce_and_identity_only_scopes():
    query = parse_qs(urlsplit(authorization_url(SETTINGS, state="state", nonce="nonce", verifier="verifier")).query)
    assert query["scope"] == ["openid email"]
    assert query["code_challenge"] == [pkce_challenge("verifier")]
    assert query["code_challenge_method"] == ["S256"]
    assert query["nonce"] == ["nonce"] and query["state"] == ["state"]
    assert "client_secret" not in query and "access_type" not in query
    assert SETTINGS.client_secret not in repr(SETTINGS)


def test_google_signature_identity_and_nonce(provider):
    client, token, _ = provider
    assert client.verify_identity(token(), nonce="expected-nonce") == {
        "subject": "stable-owner-google-subject", "email": "owner@example.test"}
    changes = [{"iss": "https://attacker.example"}, {"aud": "another-client"},
               {"exp": int(time.time())-60}, {"iat": int(time.time())+120},
               {"email_verified": False}, {"email_verified": "true"}, {"nonce": "wrong"},
               {"sub": ""}, {"azp": "another-client"}]
    for change in changes:
        with pytest.raises(GoogleOAuthError):
            client.verify_identity(token(change), nonce="expected-nonce")
    with pytest.raises(GoogleOAuthError):
        client.verify_identity(token()+"altered", nonce="expected-nonce")
    with pytest.raises(GoogleOAuthError):
        client.verify_identity(jwt.encode({"sub":"forged"}, "s"*32, algorithm="HS256"), nonce="expected-nonce")


def test_exchange_uses_fixed_provider_and_does_not_return_access_tokens(provider):
    _, token, public = provider
    requests = []
    def handle(request):
        requests.append(request)
        if str(request.url) == TOKEN_URL:
            body = parse_qs(request.content.decode())
            assert body["code_verifier"] == ["private-verifier"]
            assert body["client_secret"] == [SETTINGS.client_secret]
            return httpx.Response(200, json={"id_token":token(), "access_token":"private-access", "refresh_token":"private-refresh"})
        assert str(request.url) == JWKS_URL
        return httpx.Response(200, json={"keys":[public]})
    client = GoogleOAuthClient(SETTINGS, transport=httpx.MockTransport(handle))
    result = client.exchange("private-code", verifier="private-verifier", nonce="expected-nonce")
    assert set(result) == {"subject", "email"}
    assert len(requests) == 2
    client.verify_identity(token(), nonce="expected-nonce")
    assert len(requests) == 2


@pytest.mark.parametrize("response", [httpx.Response(302, headers={"location":"https://attacker.example"}),
                                      httpx.Response(200, content=b"x"*65537),
                                      httpx.Response(200, json=[]), httpx.Response(200, json={})])
def test_provider_failures_do_not_expose_tokens(response):
    client = GoogleOAuthClient(SETTINGS, transport=httpx.MockTransport(lambda request: response))
    with pytest.raises(GoogleOAuthError) as error:
        client.exchange("private-code", verifier="private-verifier", nonce="expected-nonce")
    assert "private-code" not in str(error.value) and SETTINGS.client_secret not in str(error.value)
