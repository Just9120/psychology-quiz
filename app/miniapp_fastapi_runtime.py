from __future__ import annotations

from app.miniapp_fastapi import create_app_from_env

# Future runtime entrypoint for uvicorn (repo-only readiness).
app = create_app_from_env()
