import pathlib
import unittest


class DeployProductionWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = pathlib.Path('.github/workflows/deploy-production.yml').read_text(encoding='utf-8')

    def test_bootstrap_deploy_restarts_both_runtime_services(self):
        self.assertIn(
            'docker compose up -d --build --remove-orphans psych_quiz_bot psych_quiz_miniapp_api',
            self.workflow,
        )

    def test_bootstrap_deploy_does_not_target_only_bot(self):
        self.assertNotIn('docker compose up -d --force-recreate psych_quiz_bot', self.workflow)
        self.assertNotIn('docker compose up -d --build psych_quiz_bot', self.workflow)


if __name__ == '__main__':
    unittest.main()
