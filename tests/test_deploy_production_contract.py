import pathlib
import unittest


class DeployProductionWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = pathlib.Path('.github/workflows/deploy-production.yml').read_text(encoding='utf-8')
        cls.deploy_sh = pathlib.Path('deploy.sh').read_text(encoding='utf-8')

    def test_bootstrap_deploy_restarts_both_runtime_services(self):
        self.assertIn(
            'docker compose up -d --build --remove-orphans psych_quiz_bot psych_quiz_miniapp_api',
            self.workflow,
        )

    def test_bootstrap_deploy_does_not_target_only_bot(self):
        self.assertNotIn('docker compose up -d --force-recreate psych_quiz_bot', self.workflow)
        self.assertNotIn('docker compose up -d --build psych_quiz_bot', self.workflow)

    def test_normal_deploy_rebuilds_and_restarts_both_runtime_services(self):
        self.assertIn('MINIAPP_API_SERVICE_NAME="${MINIAPP_API_SERVICE_NAME:-psych_quiz_miniapp_api}"', self.deploy_sh)
        self.assertIn('RUNTIME_SERVICE_NAMES=("${SERVICE_NAME}" "${MINIAPP_API_SERVICE_NAME}")', self.deploy_sh)
        self.assertIn('docker compose up -d --build --force-recreate "${RUNTIME_SERVICE_NAMES[@]}"', self.deploy_sh)

    def test_normal_deploy_post_checks_both_runtime_services(self):
        self.assertIn('docker compose ps "${RUNTIME_SERVICE_NAMES[@]}"', self.deploy_sh)
        self.assertIn('docker compose logs --tail=50 "${MINIAPP_API_SERVICE_NAME}"', self.deploy_sh)


if __name__ == '__main__':
    unittest.main()
