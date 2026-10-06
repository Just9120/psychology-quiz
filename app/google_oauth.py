"""Server-side Google code exchange and verified OIDC identity.

No Drive scopes, refresh tokens or third-party account registration.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import threading
import time
from urllib.parse import urlencode

import httpx
import jwt

AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
MAX_RESPONSE_BYTES = 65536


class GoogleOAuthError(ValueError):
    pass


@dataclass(frozen=True, repr=False)
class GoogleOAuthSettings:
    client_id: str
    client_secret: str
    redirect_uri: str


def pkce_challenge(verifier: str) -> str:
    import base64
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")


def authorization_url(settings: GoogleOAuthSettings, *, state: str, nonce: str, verifier: str) -> str:
    return AUTHORIZATION_URL + "?" + urlencode({
        "client_id": settings.client_id, "redirect_uri": settings.redirect_uri,
        "response_type": "code", "scope": "openid email", "state": state,
        "nonce": nonce, "code_challenge": pkce_challenge(verifier),
        "code_challenge_method": "S256", "prompt": "select_account",
    })


class GoogleOAuthClient:
    def __init__(self, settings: GoogleOAuthSettings, *, transport=None, clock=time.time):
        self.settings, self.transport, self.clock = settings, transport, clock
        self._lock = threading.Lock()
        self._keys, self._keys_expire = [], 0

    def _json(self, method: str, url: str, *, data=None):
        # Fixed provider endpoints; no redirects, environment proxies, retries,
        # debug logging of tokens, or arbitrary URLs from JWT headers.
        try:
            with httpx.Client(timeout=10, follow_redirects=False, trust_env=False,
                              transport=self.transport) as client:
                with client.stream(method, url, data=data) as response:
                    response.raise_for_status()
                    content = bytearray()
                    for block in response.iter_bytes():
                        content.extend(block)
                        if len(content) > MAX_RESPONSE_BYTES:
                            raise GoogleOAuthError("google_response_too_large")
                    import json
                    value = json.loads(content)
                    if not isinstance(value, dict):
                        raise GoogleOAuthError("invalid_google_response")
                    return value
        except (httpx.HTTPError, ValueError, UnicodeError) as error:
            if isinstance(error, GoogleOAuthError):
                raise
            raise GoogleOAuthError("google_provider_unavailable") from None

    def _signing_key(self, token: str):
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if header.get("alg") != "RS256" or not isinstance(kid, str) or not 1 <= len(kid) <= 200:
                raise GoogleOAuthError("invalid_google_identity")
            with self._lock:
                now = self.clock()
                if now >= self._keys_expire:
                    document = self._json("GET", JWKS_URL)
                    keys = document.get("keys")
                    if not isinstance(keys, list) or not 1 <= len(keys) <= 20:
                        raise GoogleOAuthError("invalid_google_keys")
                    self._keys, self._keys_expire = keys, now + 300
                matches = [key for key in self._keys if isinstance(key, dict) and key.get("kid") == kid]
                if len(matches) != 1:
                    # Unknown IDs fail closed until the bounded cache refresh.
                    raise GoogleOAuthError("google_signing_key_unavailable")
                key = matches[0]
                if key.get("kty") != "RSA" or key.get("alg") != "RS256" or key.get("use") != "sig":
                    raise GoogleOAuthError("invalid_google_keys")
                return jwt.PyJWK.from_dict(key, algorithm="RS256").key
        except (jwt.PyJWTError, TypeError, ValueError):
            raise GoogleOAuthError("invalid_google_identity") from None

    def verify_identity(self, token: object, *, nonce: str) -> dict:
        if not isinstance(token, str) or not 1 <= len(token) <= 16384:
            raise GoogleOAuthError("invalid_google_identity")
        try:
            claims = jwt.decode(token, self._signing_key(token), algorithms=["RS256"],
                                audience=self.settings.client_id, issuer=ISSUERS, leeway=30,
                                options={"require": ["iss", "aud", "exp", "iat", "sub", "nonce", "email", "email_verified"]})
            subject = claims.get("sub")
            actual_nonce = claims.get("nonce")
            if (not isinstance(subject, str) or not 1 <= len(subject) <= 255
                    or claims.get("email_verified") is not True
                    or not isinstance(claims.get("email"), str)
                    or not isinstance(actual_nonce, str)
                    or not hmac.compare_digest(actual_nonce, nonce)
                    or ("azp" in claims and claims["azp"] != self.settings.client_id)):
                raise GoogleOAuthError("invalid_google_identity")
            # Third-party e-mail addresses are not account ownership proof.
            # Only the durable Google subject is used after an authenticated
            # owner explicitly links this identity to their existing account.
            return {"subject": subject, "email": claims["email"]}
        except (jwt.PyJWTError, TypeError, ValueError):
            raise GoogleOAuthError("invalid_google_identity") from None

    def exchange(self, code: object, *, verifier: str, nonce: str) -> dict:
        if not isinstance(code, str) or not 1 <= len(code) <= 4096:
            raise GoogleOAuthError("invalid_google_code")
        result = self._json("POST", TOKEN_URL, data={
            "code": code, "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret, "redirect_uri": self.settings.redirect_uri,
            "grant_type": "authorization_code", "code_verifier": verifier,
        })
        # Provider access/refresh tokens are never returned or stored.
        return self.verify_identity(result.get("id_token"), nonce=nonce)
