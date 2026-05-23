from __future__ import annotations

import os
import logging
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    bot_username: str | None
    app_env: str
    log_level: str
    db_path: str
    mini_app_url: str | None
    admin_telegram_ids: frozenset[int]
    miniapp_api_bind: str
    miniapp_api_port: int
    miniapp_api_initdata_ttl_seconds: int
    miniapp_api_allowed_origin: str | None
    mini_app_api_base_url: str | None


def _parse_admin_telegram_ids(raw_ids: str) -> frozenset[int]:
    parsed_ids: set[int] = set()
    for token in raw_ids.split(","):
        clean_token = token.strip()
        if not clean_token:
            continue
        if clean_token.isdigit():
            parsed_ids.add(int(clean_token))
            continue
        logger.warning(
            "Некорректный ADMIN_TELEGRAM_IDS токен '%s' проигнорирован. Ожидался numeric Telegram user id.",
            clean_token,
        )
    return frozenset(parsed_ids)


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError("Переменная окружения BOT_TOKEN обязательна.")

    bot_username = os.getenv("BOT_USERNAME", "").strip() or None
    app_env = os.getenv("APP_ENV", "dev").strip() or "dev"
    log_level = os.getenv("LOG_LEVEL", "INFO").strip() or "INFO"
    db_path = os.getenv("DB_PATH", "/data/quiz.sqlite3").strip() or "/data/quiz.sqlite3"
    mini_app_url = os.getenv("MINI_APP_URL", "").strip() or None
    admin_telegram_ids = _parse_admin_telegram_ids(os.getenv("ADMIN_TELEGRAM_IDS", ""))
    miniapp_api_bind = os.getenv("MINIAPP_API_BIND", "127.0.0.1").strip() or "127.0.0.1"
    miniapp_api_port = int(os.getenv("MINIAPP_API_PORT", "8081"))
    miniapp_api_initdata_ttl_seconds = int(os.getenv("MINIAPP_API_INITDATA_TTL_SECONDS", "3600"))
    miniapp_api_allowed_origin = os.getenv("MINIAPP_API_ALLOWED_ORIGIN", "").strip() or None
    mini_app_api_base_url = os.getenv("MINI_APP_API_BASE_URL", "").strip() or None

    return Settings(
        bot_token=bot_token,
        bot_username=bot_username,
        app_env=app_env,
        log_level=log_level,
        db_path=db_path,
        mini_app_url=mini_app_url,
        admin_telegram_ids=admin_telegram_ids,
        miniapp_api_bind=miniapp_api_bind,
        miniapp_api_port=miniapp_api_port,
        miniapp_api_initdata_ttl_seconds=miniapp_api_initdata_ttl_seconds,
        miniapp_api_allowed_origin=miniapp_api_allowed_origin,
        mini_app_api_base_url=mini_app_api_base_url,
    )
logger = logging.getLogger(__name__)
