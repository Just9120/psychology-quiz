"""Internal health/version and unauthenticated API boundary, without user writes."""
import json
import os
import time
import urllib.error
import urllib.request


def main() -> None:
    expected = os.environ["APP_REVISION"]
    for attempt in range(30):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8081/healthz", timeout=3) as response:
                health = json.load(response)
            if health.get("ok") is not True or health.get("revision") != expected:
                raise RuntimeError("Health/version mismatch")
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
    print(f"HTTP_SMOKE_OK revision={expected}")


if __name__ == "__main__":
    main()
