#!/usr/bin/env python3
from __future__ import annotations

import os

from app.miniapp_fastapi import create_app


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var for local/dev run: {name}")
    return value


app = create_app(
    db_path=_required_env("MINIAPP_DB_PATH"),
    bot_token=_required_env("BOT_TOKEN"),
    initdata_ttl_seconds=int(os.getenv("MINIAPP_API_INITDATA_TTL_SECONDS", "3600")),
    allowed_origin=os.getenv("MINIAPP_API_ALLOWED_ORIGIN") or None,
)
