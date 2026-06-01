from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

TELEGRAM_BOT_API_URL_RE = re.compile(r"(https?://api\.telegram\.org/(?:file/)?bot)([^/\s]+)")
NOISY_HTTP_CLIENT_LOGGERS = (
    "httpx",
    "httpcore",
    "telegram.request",
)


def redact_telegram_bot_api_urls(value: str) -> str:
    """Redact bot tokens embedded in Telegram Bot API URLs."""
    return TELEGRAM_BOT_API_URL_RE.sub(r"\1<redacted>", value)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_telegram_bot_api_urls(value)
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _redact_value(item) for key, item in value.items()}
    return value


class TelegramBotApiUrlRedactionFilter(logging.Filter):
    """Defensive filter for handlers that need in-place Telegram URL redaction."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_value(record.msg)
        if record.args:
            record.args = _redact_value(record.args)
        return True


def install_telegram_url_redaction() -> None:
    """Install process-wide redaction for Telegram Bot API URLs in log records."""
    if getattr(logging, "_telegram_url_redaction_installed", False):
        return

    previous_factory = logging.getLogRecordFactory()

    def redacting_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous_factory(*args, **kwargs)
        TelegramBotApiUrlRedactionFilter().filter(record)
        return record

    logging.setLogRecordFactory(redacting_factory)
    setattr(logging, "_telegram_url_redaction_installed", True)


def configure_noisy_http_client_loggers(level: int = logging.WARNING) -> None:
    """Keep third-party HTTP client logs quiet without changing app diagnostics."""
    for logger_name in NOISY_HTTP_CLIENT_LOGGERS:
        logging.getLogger(logger_name).setLevel(level)


def configure_app_logging(log_level: str) -> None:
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    install_telegram_url_redaction()
    logging.getLogger().setLevel(numeric_level)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    configure_noisy_http_client_loggers()
