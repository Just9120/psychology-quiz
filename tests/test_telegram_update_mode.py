import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.config import load_settings
from app.main import run_application


def _render_log_calls(mock):
    rendered = []
    for call in mock.call_args_list:
        if call.args and isinstance(call.args[0], str) and len(call.args) > 1:
            try:
                rendered.append(call.args[0] % call.args[1:])
                continue
            except TypeError:
                pass
        rendered.append(" ".join(str(arg) for arg in call.args))
    return " ".join(rendered)


class TelegramUpdateModeSettingsTests(unittest.TestCase):
    def _base_env(self):
        return {"BOT_TOKEN": "123456:secret-token"}

    def test_default_update_mode_is_polling(self):
        with patch.dict(os.environ, self._base_env(), clear=True):
            settings = load_settings()

        self.assertEqual(settings.telegram_update_mode, "polling")
        self.assertIsNone(settings.telegram_webhook_url)
        self.assertIsNone(settings.telegram_webhook_listen)
        self.assertIsNone(settings.telegram_webhook_port)
        self.assertIsNone(settings.telegram_webhook_secret_token)

    def test_polling_mode_does_not_require_webhook_settings(self):
        env = self._base_env()
        env["TELEGRAM_UPDATE_MODE"] = "polling"
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()

        self.assertEqual(settings.telegram_update_mode, "polling")

    def test_webhook_mode_requires_url_listen_and_port(self):
        env = self._base_env()
        env["TELEGRAM_UPDATE_MODE"] = "webhook"
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "TELEGRAM_WEBHOOK_URL"):
                load_settings()

    def test_webhook_mode_loads_required_settings(self):
        env = self._base_env()
        env.update(
            {
                "TELEGRAM_UPDATE_MODE": "webhook",
                "TELEGRAM_WEBHOOK_URL": "https://quiz.example.com/tg/webhook",
                "TELEGRAM_WEBHOOK_LISTEN": "127.0.0.1",
                "TELEGRAM_WEBHOOK_PORT": "8090",
                "TELEGRAM_WEBHOOK_SECRET_TOKEN": "secret-header-token",
            }
        )
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()

        self.assertEqual(settings.telegram_update_mode, "webhook")
        self.assertEqual(settings.telegram_webhook_url, "https://quiz.example.com/tg/webhook")
        self.assertEqual(settings.telegram_webhook_listen, "127.0.0.1")
        self.assertEqual(settings.telegram_webhook_port, 8090)
        self.assertEqual(settings.telegram_webhook_secret_token, "secret-header-token")

    def test_invalid_update_mode_is_rejected(self):
        env = self._base_env()
        env["TELEGRAM_UPDATE_MODE"] = "invalid"
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "TELEGRAM_UPDATE_MODE"):
                load_settings()


class TelegramUpdateModeStartupTests(unittest.TestCase):
    def test_startup_chooses_polling_path(self):
        application = MagicMock()
        settings = SimpleNamespace(telegram_update_mode="polling")

        with patch("app.main.logger.info") as info_log:
            run_application(application, settings)

        application.run_polling.assert_called_once_with()
        application.run_webhook.assert_not_called()
        logged = _render_log_calls(info_log)
        self.assertIn("bot_update_mode mode=polling", logged)

    def test_startup_chooses_webhook_path_and_does_not_log_secrets(self):
        application = MagicMock()
        settings = SimpleNamespace(
            telegram_update_mode="webhook",
            bot_token="123456:secret-token",
            telegram_webhook_url="https://quiz.example.com/tg/123456:secret-token/webhook",
            telegram_webhook_listen="127.0.0.1",
            telegram_webhook_port=8090,
            telegram_webhook_secret_token="secret-header-token",
        )

        with patch("app.main.logger.info") as info_log:
            run_application(application, settings)

        application.run_polling.assert_not_called()
        application.run_webhook.assert_called_once_with(
            listen="127.0.0.1",
            port=8090,
            url_path="tg/123456:secret-token/webhook",
            webhook_url="https://quiz.example.com/tg/123456:secret-token/webhook",
            secret_token="secret-header-token",
        )
        logged = _render_log_calls(info_log)
        self.assertIn("bot_update_mode mode=webhook", logged)
        self.assertIn("webhook_host=quiz.example.com", logged)
        self.assertIn("path=/tg/<redacted>/webhook", logged)
        self.assertNotIn("123456:secret-token", logged)
        self.assertNotIn("secret-header-token", logged)


if __name__ == "__main__":
    unittest.main()
