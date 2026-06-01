import logging
import unittest
from io import StringIO

from app.logging_config import (
    NOISY_HTTP_CLIENT_LOGGERS,
    TelegramBotApiUrlRedactionFilter,
    configure_app_logging,
    redact_telegram_bot_api_urls,
)


class LoggingConfigTests(unittest.TestCase):
    def test_redacts_telegram_bot_api_urls(self):
        raw = "HTTP Request: POST https://api.telegram.org/bot123456:secret-token/answerCallbackQuery"

        redacted = redact_telegram_bot_api_urls(raw)

        self.assertEqual(
            redacted,
            "HTTP Request: POST https://api.telegram.org/bot<redacted>/answerCallbackQuery",
        )
        self.assertNotIn("123456:secret-token", redacted)

    def test_redaction_filter_sanitizes_format_args(self):
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(TelegramBotApiUrlRedactionFilter())
        logger = logging.getLogger("tests.telegram_redaction")
        old_handlers = logger.handlers[:]
        old_propagate = logger.propagate
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)
        try:
            logger.info(
                "HTTP Request: POST %s",
                "https://api.telegram.org/bot123456:secret-token/sendMessage",
            )
        finally:
            logger.handlers = old_handlers
            logger.propagate = old_propagate

        logged = stream.getvalue()
        self.assertIn("https://api.telegram.org/bot<redacted>/sendMessage", logged)
        self.assertNotIn("123456:secret-token", logged)

    def test_configure_app_logging_quiets_noisy_http_clients(self):
        old_levels = {name: logging.getLogger(name).level for name in NOISY_HTTP_CLIENT_LOGGERS}
        try:
            configure_app_logging("INFO")
            for logger_name in NOISY_HTTP_CLIENT_LOGGERS:
                self.assertGreaterEqual(logging.getLogger(logger_name).getEffectiveLevel(), logging.WARNING)
            self.assertEqual(logging.getLogger("app.main").getEffectiveLevel(), logging.INFO)
        finally:
            for logger_name, level in old_levels.items():
                logging.getLogger(logger_name).setLevel(level)


if __name__ == "__main__":
    unittest.main()
