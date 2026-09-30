"""Shared asynchronous Telegram operations, independent of the entrypoint."""
from __future__ import annotations

import asyncio
import time


async def run_db_task(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


async def safe_reply(update, text: str) -> None:
    if update.message:
        await update.message.reply_text(text)


async def timed_telegram_api_call(latency, call, api_kind: str | None = None):
    started_at = time.perf_counter()
    result = await call
    if latency is not None:
        latency.add_telegram_api(started_at, api_kind=api_kind)
    return result
