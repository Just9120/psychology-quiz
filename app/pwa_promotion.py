"""One-time, private-chat introduction to the browser PWA."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
import secrets
from urllib.parse import urlsplit

from app.database import begin_write

INVITATION_TTL = 24 * 3600
INVITATION_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


def public_pwa_origin(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        return None
    return value.rstrip("/")


def parse_invitee_ids(value: str) -> frozenset[int]:
    if not value.strip():
        return frozenset()
    parts = [part.strip() for part in value.split(",")]
    if any(not part or not part.isascii() or not part.isdecimal() for part in parts):
        raise ValueError("Invalid PWA_STUDENT_INVITEE_IDS")
    return frozenset(int(part) for part in parts)


def claim_first_offer(conn, telegram_user_id: int, *, now: int | None = None) -> bool:
    """Persist the single automatic offer; a manual menu entry remains available."""
    if not isinstance(telegram_user_id, int) or isinstance(telegram_user_id, bool):
        return False
    begin_write(conn, f"pwa-offer:{telegram_user_id}")
    actor = conn.execute("SELECT id FROM users WHERE telegram_user_id=?", (telegram_user_id,)).fetchone()
    if actor is None:
        return False
    user_id = int(actor[0])
    if conn.execute("SELECT 1 FROM web_accounts WHERE user_id=?", (user_id,)).fetchone():
        return False
    conn.execute("INSERT INTO pwa_invitations(user_id) VALUES(?) ON CONFLICT(user_id) DO NOTHING", (user_id,))
    offered_at = now if now is not None else int(datetime.now(timezone.utc).timestamp())
    return conn.execute("UPDATE pwa_invitations SET promo_shown_at=? WHERE user_id=? AND promo_shown_at IS NULL RETURNING user_id",
                        (offered_at, user_id)).fetchone() is not None


def issue_invitation(conn, telegram_user_id: int, *, now: int | None = None) -> str | None:
    """Called only for a verified Telegram user when the student launch gate is open."""
    if not isinstance(telegram_user_id, int) or isinstance(telegram_user_id, bool):
        return None
    begin_write(conn, f"pwa-invite:{telegram_user_id}")
    actor = conn.execute("SELECT id FROM users WHERE telegram_user_id=?", (telegram_user_id,)).fetchone()
    if actor is None:
        return None
    user_id = int(actor[0])
    if conn.execute("SELECT 1 FROM web_accounts WHERE user_id=?", (user_id,)).fetchone():
        return None
    if conn.execute("SELECT 1 FROM pwa_invitations WHERE user_id=? AND account_id IS NOT NULL", (user_id,)).fetchone():
        return None
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    issued_at = now if now is not None else int(datetime.now(timezone.utc).timestamp())
    conn.execute("""INSERT INTO pwa_invitations(user_id,promo_shown_at,token_digest,expires_at)
        VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
        token_digest=excluded.token_digest,expires_at=excluded.expires_at,
        consumed_at=NULL,invited_email=NULL,account_id=NULL""",
        (user_id, issued_at, digest, issued_at + INVITATION_TTL))
    return token


def reserve_invitation(conn, token: object, email: str, *, now: int) -> bool:
    if not isinstance(token, str) or INVITATION_TOKEN.fullmatch(token) is None:
        return False
    digest = hashlib.sha256(token.encode()).hexdigest()
    conn.execute("UPDATE pwa_invitations SET invited_email=NULL WHERE expires_at<=? AND account_id IS NULL", (now,))
    if conn.execute("SELECT 1 FROM pwa_invitations WHERE invited_email=? AND token_digest<>?", (email, digest)).fetchone():
        return False
    return conn.execute("""UPDATE pwa_invitations SET invited_email=?
        WHERE token_digest=? AND expires_at>? AND consumed_at IS NULL AND account_id IS NULL
        AND (invited_email IS NULL OR invited_email=?) RETURNING user_id""",
        (email, digest, now, email)).fetchone() is not None


def complete_invitation(conn, email: str, account_id: int, *, now: int) -> int | None:
    row = conn.execute("""UPDATE pwa_invitations SET account_id=?,consumed_at=?,token_digest=NULL
        WHERE invited_email=? AND expires_at>? AND consumed_at IS NULL AND account_id IS NULL
        RETURNING user_id""", (account_id, now, email, now)).fetchone()
    return int(row[0]) if row else None


def invited_actor(conn, account_id: int) -> int | None:
    row = conn.execute("SELECT user_id FROM pwa_invitations WHERE account_id=? AND consumed_at IS NOT NULL", (account_id,)).fetchone()
    return int(row[0]) if row else None
