"""Owner authentication with durable one-time proofs and server-side sessions."""
from __future__ import annotations

from contextlib import closing, contextmanager
import hashlib
import hmac
import re
import secrets
from threading import BoundedSemaphore
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

from app.db import create_or_load_user, get_connection
from app.web_config import WebSettings, normalize_email

SESSION_TTL = 7 * 86400
IDLE_TTL = 12 * 3600
VERIFY_TTL = 3600
RECOVERY_TTL = 900
LINK_TTL = 600
PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
HASH_SLOTS = BoundedSemaphore(2)
MAIL_SLOTS = BoundedSemaphore(2)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


class AuthError(Exception):
    def __init__(self, code: str, status: int = 400):
        self.code, self.status = code, status
        super().__init__(code)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def valid_token(value: object) -> bool:
    return isinstance(value, str) and TOKEN_PATTERN.fullmatch(value) is not None


def csrf_token(session: str) -> str:
    return hmac.new(session.encode(), b"psychologyatlas-csrf-v1", hashlib.sha256).hexdigest()


def validate_password(password: object) -> str:
    if not isinstance(password, str) or not 15 <= len(password) <= 128:
        raise AuthError("password_length")
    try:
        password.encode("utf-8")
    except UnicodeError:
        raise AuthError("password_format") from None
    return password


@contextmanager
def hash_slot():
    if not HASH_SLOTS.acquire(blocking=False):
        raise AuthError("auth_busy", 503)
    try:
        yield
    finally:
        HASH_SLOTS.release()


class WebAuth:
    def __init__(self, db_path: str, settings: WebSettings, mailer, *, clock=time.time):
        self.db_path, self.settings, self.mailer, self.clock = db_path, settings, mailer, clock
        # Unknown accounts still verify a real, equally expensive Argon2 hash.
        with hash_slot():
            self.dummy_hash = PASSWORDS.hash(secrets.token_urlsafe(32))

    @contextmanager
    def transaction(self):
        with closing(get_connection(self.db_path)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            yield conn

    def limit(self, bucket: str, maximum: int, window: int) -> None:
        now = int(self.clock())
        with self.transaction() as conn:
            row = conn.execute("SELECT started_at,count FROM web_auth_limits WHERE bucket=?", (bucket,)).fetchone()
            if row is None or now >= row["started_at"] + window:
                conn.execute("INSERT OR REPLACE INTO web_auth_limits VALUES(?,?,1)", (bucket, now))
                allowed = True
            else:
                allowed = row["count"] < maximum
                if allowed:
                    conn.execute("UPDATE web_auth_limits SET count=count+1 WHERE bucket=?", (bucket,))
        if not allowed:
            raise AuthError("rate_limited", 429)

    def request_mail(self, email: object, purpose: str) -> None:
        self.limit("mail", 5, 3600)
        try:
            email = normalize_email(email)
        except ValueError:
            return
        if email != self.settings.owner_email or purpose not in {"register", "recover"}:
            return
        if not MAIL_SLOTS.acquire(blocking=False):
            raise AuthError("mail_unavailable", 503)
        token = secrets.token_urlsafe(32)
        token_digest = digest(token)
        try:
            now = int(self.clock())
            with self.transaction() as conn:
                conn.execute("DELETE FROM web_mail_tokens WHERE expires_at<=?", (now,))
                account = conn.execute("SELECT id,enabled FROM web_accounts WHERE email=?", (email,)).fetchone()
                if purpose == "register" and account is not None:
                    return
                if purpose == "recover" and (account is None or not account["enabled"]):
                    return
                ttl = VERIFY_TTL if purpose == "register" else RECOVERY_TTL
                conn.execute("INSERT INTO web_mail_tokens VALUES(?,?,?,?,?)",
                             (token_digest, email, purpose, account["id"] if account else None, now + ttl))
            try:
                self.mailer.send(email, purpose, token)
            except Exception:
                # Do not expose SMTP exception strings (they can contain credentials).
                with self.transaction() as conn:
                    conn.execute("DELETE FROM web_mail_tokens WHERE digest=?", (token_digest,))
                raise AuthError("mail_unavailable", 503) from None
        finally:
            MAIL_SLOTS.release()

    def _mail_proof(self, conn, token: object, purpose: str):
        if not valid_token(token):
            raise AuthError("invalid_token")
        row = conn.execute("SELECT * FROM web_mail_tokens WHERE digest=? AND purpose=? AND expires_at>?",
                           (digest(token), purpose, int(self.clock()))).fetchone()
        if row is None or row["email"] != self.settings.owner_email:
            raise AuthError("invalid_token")
        return row

    def set_password(self, token: object, password: object, purpose: str) -> None:
        self.limit("token", 10, 60)
        password = validate_password(password)
        with closing(get_connection(self.db_path)) as conn:
            self._mail_proof(conn, token, purpose)
        with hash_slot():
            encoded = PASSWORDS.hash(password)
        now = int(self.clock())
        with self.transaction() as conn:
            proof = self._mail_proof(conn, token, purpose)  # Recheck after expensive hash.
            if purpose == "register":
                if conn.execute("SELECT 1 FROM web_accounts WHERE email=?", (proof["email"],)).fetchone():
                    raise AuthError("invalid_token")
                conn.execute("INSERT INTO web_accounts(email,password_hash,verified_at,created_at) VALUES(?,?,?,?)",
                             (proof["email"], encoded, now, now))
            elif purpose == "recover":
                account = conn.execute("SELECT * FROM web_accounts WHERE id=? AND enabled=1", (proof["account_id"],)).fetchone()
                if account is None:
                    raise AuthError("invalid_token")
                conn.execute("UPDATE web_accounts SET password_hash=? WHERE id=?", (encoded, account["id"]))
                conn.execute("DELETE FROM web_sessions WHERE account_id=?", (account["id"],))
            else:
                raise AuthError("invalid_token")
            # All outstanding proofs for this action are invalidated on success.
            conn.execute("DELETE FROM web_mail_tokens WHERE email=? AND purpose=?", (proof["email"], purpose))

    def login(self, email: object, password: object) -> str:
        self.limit("login", 10, 60)
        try:
            email = normalize_email(email)
        except ValueError:
            email = ""
        if not isinstance(password, str) or len(password) > 128:
            raise AuthError("invalid_credentials", 401)
        try:
            password.encode("utf-8")
        except UnicodeError:
            raise AuthError("invalid_credentials", 401) from None
        with closing(get_connection(self.db_path)) as conn:
            row = conn.execute("SELECT * FROM web_accounts WHERE email=?", (email,)).fetchone()
        encoded = row["password_hash"] if row else self.dummy_hash
        with hash_slot():
            try:
                verified = PASSWORDS.verify(encoded, password)
            except (VerificationError, InvalidHashError):
                verified = False
        if not verified or row is None or not row["enabled"] or email != self.settings.owner_email:
            raise AuthError("invalid_credentials", 401)
        now, token = int(self.clock()), secrets.token_urlsafe(32)
        with self.transaction() as conn:
            # Reset/disable may have happened while the hash was being verified.
            current = conn.execute("SELECT 1 FROM web_accounts WHERE id=? AND enabled=1 AND password_hash=?",
                                   (row["id"], encoded)).fetchone()
            if current is None:
                raise AuthError("invalid_credentials", 401)
            conn.execute("DELETE FROM web_sessions WHERE expires_at<=? OR last_seen_at<=?", (now, now-IDLE_TTL))
            conn.execute("INSERT INTO web_sessions VALUES(?,?,?,?,?)", (digest(token), row["id"], now, now+SESSION_TTL, now))
            # Bound retained sessions for this closed owner application.
            conn.execute("""DELETE FROM web_sessions WHERE account_id=? AND digest NOT IN (
                SELECT digest FROM web_sessions WHERE account_id=? ORDER BY created_at DESC,rowid DESC LIMIT 10
            )""", (row["id"], row["id"]))
        return token

    def authenticate(self, conn, token: object, *, csrf: object = None, mutation=False):
        if not valid_token(token):
            raise AuthError("unauthorized", 401)
        now = int(self.clock())
        row = conn.execute("""SELECT a.*,s.digest AS session_digest FROM web_sessions s
            JOIN web_accounts a ON a.id=s.account_id WHERE s.digest=? AND s.expires_at>?
            AND s.last_seen_at>? AND a.enabled=1 AND a.email=?""",
            (digest(token), now, now-IDLE_TTL, self.settings.owner_email)).fetchone()
        if row is None:
            raise AuthError("unauthorized", 401)
        if mutation and (not isinstance(csrf, str) or re.fullmatch(r"[0-9a-f]{64}", csrf) is None or not hmac.compare_digest(csrf_token(token), csrf)):
            raise AuthError("csrf_failed", 403)
        conn.execute("UPDATE web_sessions SET last_seen_at=? WHERE digest=?", (now, row["session_digest"]))
        return row

    def account_state(self, conn, account, session: str) -> dict:
        actor = conn.execute("SELECT telegram_user_id FROM users WHERE id=?", (account["user_id"],)).fetchone()
        pending = conn.execute("SELECT telegram_confirmed,expires_at,proposed_user_id FROM web_link_tokens WHERE session_digest=? AND expires_at>?",
                               (account["session_digest"], int(self.clock()))).fetchone()
        target = None
        if pending and pending["telegram_confirmed"]:
            target_user = conn.execute("SELECT telegram_user_id,username,first_name,last_name FROM users WHERE id=?", (pending["proposed_user_id"],)).fetchone()
            if target_user is not None:
                target = {"telegram_id": target_user["telegram_user_id"], "username": target_user["username"],
                          "display_name": " ".join(str(target_user[key]) for key in ("first_name", "last_name") if target_user[key])}
        return {"ok": True, "email": account["email"], "needs_identity": account["user_id"] is None,
                "telegram_linked": actor is not None and actor[0] is not None, "csrf_token": csrf_token(session),
                "link_pending": bool(pending), "link_confirmed": bool(pending and pending["telegram_confirmed"]), "link_target": target}

    def fresh_identity(self, conn, account) -> None:
        if account["user_id"] is not None:
            return
        actor = conn.execute("INSERT INTO users DEFAULT VALUES").lastrowid
        conn.execute("UPDATE web_accounts SET user_id=? WHERE id=? AND user_id IS NULL", (actor, account["id"]))
        conn.execute("DELETE FROM web_link_tokens WHERE account_id=?", (account["id"],))

    def start_link(self, conn, account) -> str:
        if account["user_id"] is not None:
            raise AuthError("identity_already_chosen", 409)
        token = secrets.token_urlsafe(32)
        conn.execute("DELETE FROM web_link_tokens WHERE account_id=? OR expires_at<=?", (account["id"], int(self.clock())))
        conn.execute("INSERT INTO web_link_tokens(digest,account_id,session_digest,expires_at) VALUES(?,?,?,?)",
                     (digest(token), account["id"], account["session_digest"], int(self.clock())+LINK_TTL))
        return token

    def _link_proof(self, conn, token: object):
        if not valid_token(token):
            raise AuthError("invalid_link")
        now = int(self.clock())
        row = conn.execute("""SELECT l.*,a.email,a.user_id FROM web_link_tokens l
            JOIN web_accounts a ON a.id=l.account_id JOIN web_sessions s ON s.digest=l.session_digest
            WHERE l.digest=? AND l.expires_at>? AND s.expires_at>? AND s.last_seen_at>?
            AND a.enabled=1 AND a.email=?""", (digest(token), now, now, now-IDLE_TTL, self.settings.owner_email)).fetchone()
        if row is None or row["user_id"] is not None:
            raise AuthError("invalid_link")
        return row

    def propose_telegram_link(self, token: str, telegram_user) -> str:
        # Only the trusted bot Update supplies telegram_user; never a web request ID.
        with self.transaction() as conn:
            proof = self._link_proof(conn, token)
            actor = create_or_load_user(conn, telegram_user.id, telegram_user.username, telegram_user.first_name, telegram_user.last_name)
            if conn.execute("SELECT 1 FROM web_accounts WHERE user_id=?", (actor["id"],)).fetchone():
                raise AuthError("identity_unavailable", 409)
            if proof["proposed_user_id"] is not None and proof["proposed_user_id"] != actor["id"]:
                raise AuthError("invalid_link")
            conn.execute("UPDATE web_link_tokens SET proposed_user_id=? WHERE digest=?", (actor["id"], proof["digest"]))
            return proof["email"]

    def confirm_telegram_link(self, token: str, telegram_id: int) -> None:
        with self.transaction() as conn:
            proof = self._link_proof(conn, token)
            actor = conn.execute("SELECT id FROM users WHERE telegram_user_id=?", (telegram_id,)).fetchone()
            if actor is None or actor["id"] != proof["proposed_user_id"] or proof["telegram_confirmed"]:
                raise AuthError("invalid_link")
            conn.execute("UPDATE web_link_tokens SET telegram_confirmed=1 WHERE digest=?", (proof["digest"],))

    def complete_link(self, conn, account) -> None:
        proof = conn.execute("SELECT * FROM web_link_tokens WHERE session_digest=? AND expires_at>?",
                             (account["session_digest"], int(self.clock()))).fetchone()
        if proof is None or not proof["telegram_confirmed"] or account["user_id"] is not None:
            raise AuthError("invalid_link")
        if conn.execute("SELECT 1 FROM web_accounts WHERE user_id=?", (proof["proposed_user_id"],)).fetchone():
            raise AuthError("identity_unavailable", 409)
        conn.execute("UPDATE web_accounts SET user_id=? WHERE id=?", (proof["proposed_user_id"], account["id"]))
        conn.execute("DELETE FROM web_link_tokens WHERE account_id=?", (account["id"],))
