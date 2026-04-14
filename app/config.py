from __future__ import annotations

import os
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


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError("Переменная окружения BOT_TOKEN обязательна.")

    bot_username = os.getenv("BOT_USERNAME", "").strip() or None
    app_env = os.getenv("APP_ENV", "dev").strip() or "dev"
    log_level = os.getenv("LOG_LEVEL", "INFO").strip() or "INFO"
    db_path = os.getenv("DB_PATH", "/data/quiz.sqlite3").strip() or "/data/quiz.sqlite3"

    return Settings(
        bot_token=bot_token,
        bot_username=bot_username,
        app_env=app_env,
        log_level=log_level,
        db_path=db_path,
    )
