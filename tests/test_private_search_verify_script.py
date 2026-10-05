"""Operator argument gates must stop before any privileged runtime action."""
import shutil
import subprocess
from pathlib import Path

import pytest


BASH = (str(Path("C:/Program Files/Git/bin/bash.exe"))
        if Path("C:/Program Files/Git/bin/bash.exe").is_file() else shutil.which("bash"))
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/private_search_verify.sh"


@pytest.mark.skipif(BASH is None, reason="Bash unavailable on this local host")
@pytest.mark.parametrize("arguments,expected", [
    ([], 2),
    (["invalid", "/root/bundle.zip", "a" * 64], 1),
    (["a" * 40, "/root/bundle.zip", "invalid"], 1),
    (["a" * 40, "/tmp/bundle.zip", "b" * 64], 1),
])
def test_invalid_operator_inputs_stop_before_runtime_access(arguments, expected):
    result = subprocess.run([BASH, str(SCRIPT), *arguments],
                            capture_output=True, timeout=5)
    assert result.returncode == expected
    assert b"STEP=" not in result.stdout
    assert b"PRIVATE_SEARCH_CHECKS_OK" not in result.stdout
