"""Durable, browser-bound owner OIDC flow; provider tokens never persist."""
import hmac
import secrets

from app.google_oauth import GoogleOAuthClient, GoogleOAuthError, authorization_url
from app.web_auth import AuthError, IDLE_TTL, digest, valid_token

TTL = 600


class OwnerGoogleOAuth:
    def __init__(self, auth):
        self.auth = auth
        self.provider = GoogleOAuthClient(auth.settings.google) if auth.settings.google else None

    @property
    def cookie_name(self):
        return "__Host-psychology_oauth" if self.auth.settings.secure_cookie else "psychology_dev_oauth"

    def begin(self, purpose, token=None, csrf=None):
        if self.provider is None:
            raise AuthError("google_unavailable", 503)
        if purpose not in {"login", "link"}:
            raise AuthError("invalid_oauth_purpose")
        self.auth.limit("google_begin", 10, 60)
        state, browser, nonce, verifier = [secrets.token_urlsafe(32) for _ in range(4)]
        now = int(self.auth.clock())
        with self.auth.transaction() as conn:
            account = self.auth.authenticate(conn, token, csrf=csrf, mutation=True) if purpose == "link" else None
            if account is not None and conn.execute("SELECT 1 FROM web_google_identities WHERE account_id=?", (account["id"],)).fetchone():
                raise AuthError("google_already_linked", 409)
            conn.execute("DELETE FROM web_oauth_challenges WHERE expires_at<=?", (now,))
            conn.execute("""INSERT INTO web_oauth_challenges
                (state_digest,browser_digest,nonce,pkce_verifier,purpose,account_id,session_digest,expires_at)
                VALUES(?,?,?,?,?,?,?,?)""", (digest(state), digest(browser), nonce, verifier, purpose,
                account["id"] if account else None, account["session_digest"] if account else None, now+TTL))
        return {"ok": True, "url": authorization_url(self.auth.settings.google, state=state, nonce=nonce, verifier=verifier)}, browser

    def complete(self, state, browser, code):
        if self.provider is None:
            raise AuthError("google_unavailable", 503)
        if not valid_token(state) or not valid_token(browser):
            raise AuthError("invalid_oauth_state", 401)
        self.auth.limit("google_callback", 10, 60)
        now = int(self.auth.clock())
        # Commit consumption before network IO: failed code exchange also consumes
        # this proof, and concurrent callbacks can never exchange it twice.
        with self.auth.transaction() as conn:
            row = conn.execute("SELECT * FROM web_oauth_challenges WHERE state_digest=? AND expires_at>?",
                               (digest(state), now)).fetchone()
            if row is None or not hmac.compare_digest(row["browser_digest"], digest(browser)):
                raise AuthError("invalid_oauth_state", 401)
            proof = dict(row)
            conn.execute("DELETE FROM web_oauth_challenges WHERE state_digest=?", (digest(state),))
        try:
            identity = self.provider.exchange(code, verifier=proof["pkce_verifier"], nonce=proof["nonce"])
        except GoogleOAuthError:
            raise AuthError("google_login_failed", 401) from None
        with self.auth.transaction() as conn:
            now = int(self.auth.clock())
            if proof["purpose"] == "link":
                # Cross-site callback cannot rely on the Strict session cookie;
                # the initiating session itself must still be live in storage.
                account = conn.execute("""SELECT a.* FROM web_accounts a JOIN web_sessions s ON s.account_id=a.id
                    WHERE a.id=? AND s.digest=? AND s.expires_at>? AND s.last_seen_at>? AND a.enabled=1""",
                    (proof["account_id"], proof["session_digest"], now, now-IDLE_TTL)).fetchone()
                if account is None or not self.auth._allowed_email(account["email"]):
                    raise AuthError("unauthorized", 401)
                if conn.execute("SELECT 1 FROM web_google_identities WHERE subject=? OR account_id=?",
                                (identity["subject"], account["id"])).fetchone():
                    raise AuthError("google_link_conflict", 409)
                conn.execute("INSERT INTO web_google_identities VALUES(?,?,?)", (identity["subject"], account["id"], now))
                return None
            account = conn.execute("""SELECT a.* FROM web_accounts a JOIN web_google_identities g ON g.account_id=a.id
                WHERE g.subject=? AND a.enabled=1""", (identity["subject"],)).fetchone()
            if account is None or not self.auth._allowed_email(account["email"]):
                raise AuthError("invalid_credentials", 401)
            return self.auth.create_session(conn, account["id"], now)

    def unlink(self, conn, account):
        conn.execute("DELETE FROM web_google_identities WHERE account_id=?", (account["id"],))
        conn.execute("DELETE FROM web_oauth_challenges WHERE account_id=?", (account["id"],))
        # Disconnecting a sign-in provider also revokes other owner sessions;
        # the current authenticated session and password access remain valid.
        conn.execute("DELETE FROM web_sessions WHERE account_id=? AND digest<>?",
                     (account["id"], account["session_digest"]))
