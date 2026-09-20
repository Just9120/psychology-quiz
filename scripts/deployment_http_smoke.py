"""Internal health/version and unauthenticated API boundary, without user writes."""
import argparse
import json
import os
import time
import urllib.error
import urllib.request
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.database import is_postgres_target, resolve_database_target


def main(*, require_pwa=False) -> None:
    if require_pwa and os.getenv("PWA_ENABLED", "false").strip().lower() != "true":
        raise RuntimeError("Enabled PWA required before static activation")
    expected = os.environ["APP_REVISION"]
    expected_backend = "postgresql" if is_postgres_target(resolve_database_target()) else "sqlite"
    for attempt in range(30):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8081/healthz", timeout=3) as response:
                health = json.load(response)
            if health.get("ok") is not True or health.get("revision") != expected:
                raise RuntimeError("Health/version mismatch")
            with urllib.request.urlopen("http://127.0.0.1:8081/readyz", timeout=5) as response:
                readiness = json.load(response)
            if (readiness.get("ok") is not True or readiness.get("revision") != expected
                    or readiness.get("database_backend") != expected_backend or not readiness.get("database_version")):
                raise RuntimeError("Runtime database readiness/backend mismatch")
            break
        except (OSError, ValueError, RuntimeError):
            if attempt == 29:
                raise
            time.sleep(2)
    try:
        urllib.request.urlopen("http://127.0.0.1:8081/miniapp/state", timeout=3)
    except urllib.error.HTTPError as error:
        if error.code != 401 or not json.load(error).get("error"):
            raise RuntimeError("API authentication boundary failed") from None
    else:
        raise RuntimeError("Unauthenticated API request was accepted")
    expected_web_status = 401 if os.getenv("PWA_ENABLED", "false").strip().lower() == "true" else 404
    try:
        urllib.request.urlopen("http://127.0.0.1:8081/web/auth/me", timeout=3)
    except urllib.error.HTTPError as error:
        if error.code != expected_web_status:
            raise RuntimeError("PWA authentication/configuration boundary failed") from None
    else:
        raise RuntimeError("Unauthenticated PWA request was accepted")
    print(f"PWA_AUTH_BOUNDARY_OK status={expected_web_status}")
    print(f"DATABASE_READINESS_OK backend={expected_backend} version={readiness['database_version']}")
    print(f"HTTP_SMOKE_OK revision={expected}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-pwa", action="store_true")
    main(require_pwa=parser.parse_args().require_pwa)
