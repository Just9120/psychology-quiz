import os
import unittest
from unittest.mock import patch

from app.config import load_settings
from app.main import should_start_miniapp_api


class LegacyApiSwitchConfigTests(unittest.TestCase):
    def _base_env(self):
        return {
            "BOT_TOKEN": "123:abc",
            "MINIAPP_API_ENABLED": "true",
            "MINI_APP_API_BASE_URL": "https://api.example.com",
            "MINIAPP_API_ALLOWED_ORIGIN": "https://miniapp.example.com",
        }

    def test_legacy_api_enabled_by_default(self):
        with patch.dict(os.environ, self._base_env(), clear=True):
            settings = load_settings()
        self.assertTrue(settings.miniapp_legacy_api_enabled)

    def test_legacy_api_disabled_by_env_false(self):
        env = self._base_env()
        env["MINIAPP_LEGACY_API_ENABLED"] = "false"
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()
        self.assertFalse(settings.miniapp_legacy_api_enabled)
        self.assertTrue(should_start_miniapp_api(settings))


if __name__ == "__main__":
    unittest.main()
