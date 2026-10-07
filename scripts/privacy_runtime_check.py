"""Read-only check of owned live logging settings, without printing inspect data."""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys

SERVICES = {"psych_quiz_bot": "bot", "psych_quiz_miniapp_api": "api"}


def verify(container, service, revision):
    config = container.get("Config") or {}
    labels = config.get("Labels") or {}
    if (service not in SERVICES or not re.fullmatch(r"[0-9a-f]{40}", revision)
            or labels.get("com.docker.compose.project") != "psychology-quiz"
            or labels.get("com.docker.compose.service") != service
            or labels.get("org.opencontainers.image.revision") != revision
            or (container.get("State") or {}).get("Running") is not True):
        raise ValueError("unexpected_runtime_identity")
    if (config.get("Cmd") != ["python", "scripts/runtime_log.py", SERVICES[service]]
            or ((container.get("HostConfig") or {}).get("LogConfig") or {}).get("Type") != "none"):
        raise ValueError("runtime_retention_settings_mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.expected_sha):
            raise ValueError("exact_revision_required")
        for service, name in SERVICES.items():
            container_id = subprocess.check_output([
                "docker", "compose", "-p", "psychology-quiz", "-f", "docker-compose.yml",
                "ps", "-q", service], text=True, stderr=subprocess.DEVNULL).strip()
            if not re.fullmatch(r"[0-9a-f]{64}", container_id):
                raise ValueError("one_running_container_required")
            data = json.loads(subprocess.check_output(["docker", "inspect", container_id],
                text=True, stderr=subprocess.DEVNULL))
            if not isinstance(data, list) or len(data) != 1:
                raise ValueError("one_running_container_required")
            verify(data[0], service, args.expected_sha)
            # Check file metadata only. Never read log text, actor copies or env.
            code = """from pathlib import Path
from scripts.runtime_log import private
from scripts.learning_copy_retention import locked_cleanup
import sys
root = Path('/data/runtime-logs')
private(root, True)
files = list(root.glob(sys.argv[1] + '-*.log'))
assert files, 'runtime_log_missing'
for path in files:
    private(path)
if sys.argv[1] == 'api':
    locked_cleanup(apply=False)
"""
            subprocess.run(["docker", "exec", container_id, "python", "-c", code, name],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("PRIVACY_RUNTIME_OK revision=" + args.expected_sha + " logs_days=14 copies_days=7")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError):
        print("PRIVACY_RUNTIME_STOP: inspect owned runtime settings and private paths", file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
