from __future__ import annotations

from app.miniapp_fastapi import create_app_from_env

# Production Uvicorn entrypoint; environment validation runs before app startup.
app = create_app_from_env()
