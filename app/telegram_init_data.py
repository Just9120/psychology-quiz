"""Verify Telegram Mini App identity independently of HTTP and database adapters."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import time
import urllib.parse

from app.payload_validation import is_sqlite_integer


class InitDataValidationError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedInitData:
    telegram_user_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    auth_date: int


def verify_telegram_init_data(init_data: str, bot_token: str, *, max_age_seconds: int = 3600) -> VerifiedInitData:
    if not init_data:
        raise InitDataValidationError("missing_init_data")
    try:
        pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise InitDataValidationError("invalid_hash") from exc
    data = {k: v for k, v in pairs}
    recv_hash = data.pop("hash", "")
    if not recv_hash:
        raise InitDataValidationError("missing_hash")
    auth_date_raw = data.get("auth_date")
    if auth_date_raw is None or not auth_date_raw.isdigit():
        raise InitDataValidationError("invalid_auth_date")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise InitDataValidationError("invalid_auth_date") from exc
    now = int(time.time())
    if auth_date > now + 60 or now - auth_date > max_age_seconds:
        raise InitDataValidationError("expired_init_data")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, recv_hash):
        raise InitDataValidationError("invalid_hash")

    raw_user = data.get("user")
    if not raw_user:
        raise InitDataValidationError("missing_user")
    try:
        user = json.loads(raw_user)
    except json.JSONDecodeError as exc:
        raise InitDataValidationError("invalid_user_json") from exc

    if not isinstance(user, dict):
        raise InitDataValidationError("invalid_user_json")
    telegram_user_id = user.get("id")
    if not is_sqlite_integer(telegram_user_id, minimum=1):
        raise InitDataValidationError("invalid_user_id")

    return VerifiedInitData(
        telegram_user_id=telegram_user_id,
        username=user.get("username") if isinstance(user.get("username"), str) else None,
        first_name=user.get("first_name") if isinstance(user.get("first_name"), str) else None,
        last_name=user.get("last_name") if isinstance(user.get("last_name"), str) else None,
        auth_date=auth_date,
    )
