import pathlib
import unittest


class DockerComposeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = pathlib.Path("docker-compose.yml").read_text(encoding="utf-8")

    def test_fastapi_service_exists(self):
        self.assertIn("psych_quiz_miniapp_api:", self.compose)

    def test_bot_has_no_8081_host_port_binding(self):
        marker = "psych_quiz_bot:"
        bot_block = self.compose.split(marker, 1)[1].split("\n\n", 1)[0]
        self.assertNotIn("127.0.0.1:8081:8081", bot_block)

    def test_fastapi_service_owns_8081_binding_and_uvicorn_command(self):
        fastapi_block = self.compose.split("psych_quiz_miniapp_api:", 1)[1]
        self.assertIn("127.0.0.1:8081:8081", fastapi_block)
        self.assertIn('"uvicorn", "app.miniapp_fastapi_runtime:app"', fastapi_block)

    def test_bot_disables_legacy_api(self):
        marker = "psych_quiz_bot:"
        bot_block = self.compose.split(marker, 1)[1].split("\n\n", 1)[0]
        self.assertIn('MINIAPP_LEGACY_API_ENABLED: "false"', bot_block)


if __name__ == "__main__":
    unittest.main()
