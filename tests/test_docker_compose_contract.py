import pathlib
import shutil
import subprocess
import unittest



class DockerComposeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = pathlib.Path("docker-compose.yml").read_text(encoding="utf-8")

    def test_fastapi_service_exists(self):
        self.assertIn("psych_quiz_miniapp_api:", self.compose)

    def test_bot_publishes_only_internal_webhook_port(self):
        marker = "psych_quiz_bot:"
        bot_block = self.compose.split(marker, 1)[1].split("\n\n", 1)[0]
        self.assertNotIn("127.0.0.1:8081:8081", bot_block)
        self.assertIn("ports:", bot_block)
        self.assertIn('"127.0.0.1:8090:8090"', bot_block)
        self.assertNotIn('"0.0.0.0:8090:8090"', bot_block)

    def test_fastapi_service_owns_8081_binding_and_uvicorn_command(self):
        fastapi_block = self.compose.split("psych_quiz_miniapp_api:", 1)[1]
        self.assertEqual(fastapi_block.count("127.0.0.1:8081:8081"), 1)
        self.assertIn('"uvicorn", "app.miniapp_fastapi_runtime:app"', fastapi_block)

    def test_no_duplicate_published_host_ports(self):
        host_port_lines = [
            line.strip()
            for line in self.compose.splitlines()
            if '"127.0.0.1:' in line and line.strip().startswith('- "127.0.0.1:')
        ]
        self.assertEqual(len(host_port_lines), len(set(host_port_lines)))

    def test_bot_disables_legacy_api(self):
        marker = "psych_quiz_bot:"
        bot_block = self.compose.split(marker, 1)[1].split("\n\n", 1)[0]
        self.assertIn('MINIAPP_LEGACY_API_ENABLED: "false"', bot_block)

    def test_compose_services_include_bot_and_fastapi(self):
        if shutil.which("docker") is None:
            self.skipTest("docker CLI is not installed in this environment")
        result = subprocess.run(
            ["docker", "compose", "config", "--services"],
            check=True,
            capture_output=True,
            text=True,
        )
        services = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        self.assertIn("psych_quiz_bot", services)
        self.assertIn("psych_quiz_miniapp_api", services)


if __name__ == "__main__":
    unittest.main()
