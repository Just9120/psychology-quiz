#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


BASE_URL = os.getenv("MINIAPP_FASTAPI_BASE_URL", "http://127.0.0.1:8081").rstrip("/")


def _request(path: str, method: str = "GET", headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(f"{BASE_URL}{path}", method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    print(f"[smoke] base_url={BASE_URL} (local/dev only)")

    status, headers, body = _request("/healthz")
    _assert(status == 200, f"GET /healthz expected 200 got {status}")
    payload = json.loads(body.decode("utf-8"))
    _assert(payload.get("ok") is True, "GET /healthz expected ok=true")
    _assert(payload.get("service") == "miniapp_api", "GET /healthz expected service=miniapp_api")
    _assert(headers.get("Content-Type", "").startswith("application/json"), "GET /healthz expected JSON")
    print("[smoke] GET /healthz ok")

    status, _, _ = _request(
        "/miniapp/answer",
        method="OPTIONS",
        headers={
            "Origin": "https://miniapp.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )
    _assert(status in {204, 404}, f"OPTIONS /miniapp/answer expected 204 or 404 got {status}")
    print("[smoke] OPTIONS /miniapp/answer ok")

    status, headers, body = _request("/miniapp/state")
    _assert(status == 401, f"GET /miniapp/state without initData expected 401 got {status}")
    _assert(headers.get("Content-Type", "").startswith("application/json"), "GET /miniapp/state expected JSON error")
    payload = json.loads(body.decode("utf-8"))
    _assert(payload.get("ok") is False, "GET /miniapp/state expected ok=false")
    _assert(payload.get("error") == "missing_init_data", "GET /miniapp/state expected missing_init_data")
    print("[smoke] GET /miniapp/state auth error JSON ok")

    print("[smoke] all checks passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"[smoke] failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
