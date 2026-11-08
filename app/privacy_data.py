"""Explicit, one-use deletion of a Telegram actor's saved learning state.

The Telegram identity row and any linked owner account remain so the bot and
owner PWA can still authenticate. The question bank is never modified.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from app.database import begin_write
from app.deletion_journal import JournalError, actor_digest, recorded_deletion

CHALLENGE_LIFETIME = timedelta(minutes=10)
LEARNING_TABLES = (
    "quiz_sessions",
    "glossary_sessions",
    "user_literature_progress",
    "user_literature_work_progress",
    "user_learning_goals",
    "user_achievements",
    "user_review_events",
    "user_review_sessions",
)


class PrivacyError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def prepare_learning_data_deletion(conn, actor_user_id: int) -> dict:
    """Replace any previous challenge and describe what confirmation affects."""
    begin_write(conn, f"actor:{actor_user_id}")
    if conn.execute("SELECT 1 FROM users WHERE id=?", (actor_user_id,)).fetchone() is None:
        raise PrivacyError("unknown_actor")
    if conn.execute("SELECT 1 FROM web_accounts WHERE user_id=?", (actor_user_id,)).fetchone() is not None:
        raise PrivacyError("linked_owner_requires_separate_flow")
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    expires = (_utcnow() + CHALLENGE_LIFETIME).isoformat()
    conn.execute("DELETE FROM user_data_deletion_challenges WHERE user_id=?", (actor_user_id,))
    conn.execute("INSERT INTO user_data_deletion_challenges(user_id,token_digest,expires_at) VALUES(?,?,?)",
                 (actor_user_id, digest, expires))
    return {"ok": True, "confirmation_token": token, "expires_at": expires,
            "deletes": ["quiz_attempts", "glossary_attempts", "reading_statuses",
                        "learning_goals", "achievements", "review_history"],
            "keeps": ["telegram_access", "identity", "owner_account", "shared_question_bank"]}


def confirm_learning_data_deletion(conn, actor_user_id: int, token: str) -> dict:
    """Consume the challenge and delete only this actor's learning rows atomically."""
    if not isinstance(token, str) or len(token) > 128 or len(token) < 32:
        raise PrivacyError("invalid_confirmation")
    begin_write(conn, f"actor:{actor_user_id}")
    if conn.execute("SELECT 1 FROM web_accounts WHERE user_id=?", (actor_user_id,)).fetchone() is not None:
        raise PrivacyError("linked_owner_requires_separate_flow")
    row = conn.execute("SELECT token_digest,expires_at FROM user_data_deletion_challenges WHERE user_id=?",
                       (actor_user_id,)).fetchone()
    if row is None or not hmac.compare_digest(row[0], hashlib.sha256(token.encode("utf-8")).hexdigest()):
        raise PrivacyError("invalid_confirmation")
    try:
        valid = datetime.fromisoformat(row[1]) >= _utcnow()
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise PrivacyError("confirmation_expired")
    telegram_id = conn.execute("SELECT telegram_user_id FROM users WHERE id=?", (actor_user_id,)).fetchone()[0]
    try:
        with recorded_deletion(conn, telegram_id):
            conn.execute("DELETE FROM user_data_deletion_challenges WHERE user_id=?", (actor_user_id,))
            deleted = _delete_learning_rows(conn, actor_user_id)
    except (OSError, JournalError) as error:
        raise PrivacyError("deletion_reconciliation_required") from error
    return {"ok": True, "deleted": deleted, "telegram_access_retained": True}


def _delete_learning_rows(conn, actor_user_id: int) -> dict:
    deleted = {}
    for table in LEARNING_TABLES:
        deleted[table] = conn.execute(f"DELETE FROM {table} WHERE user_id=?", (actor_user_id,)).rowcount
    return deleted


def replay_learning_deletions(conn, journal: dict, affected: set[str]) -> int:
    """Apply receipts to a verified, offline restore after rebuilding its schema."""
    if not affected:
        return 0
    actors = [int(row[0]) for row in conn.execute(
        "SELECT id,telegram_user_id FROM users WHERE telegram_user_id IS NOT NULL")
        if actor_digest(journal, row[1]) in affected]
    for actor in actors:
        begin_write(conn, f"actor:{actor}")
        if conn.execute("SELECT 1 FROM web_accounts WHERE user_id=?", (actor,)).fetchone():
            raise PrivacyError("restored_actor_requires_owner_reconciliation")
        conn.execute("DELETE FROM user_data_deletion_challenges WHERE user_id=?", (actor,))
        _delete_learning_rows(conn, actor)
        if any(conn.execute(f"SELECT 1 FROM {table} WHERE user_id=? LIMIT 1", (actor,)).fetchone()
               for table in LEARNING_TABLES):
            raise PrivacyError("restored_learning_deletion_incomplete")
    return len(actors)
