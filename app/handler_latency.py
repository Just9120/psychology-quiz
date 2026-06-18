from __future__ import annotations

import logging
import re
import time

logger = logging.getLogger("app.main")

HANDLER_START_LOG_PREFIX = "bot_handler_start"
LATENCY_LOG_PREFIX = "bot_latency"
SLOW_LATENCY_LOG_PREFIX = "bot_latency_slow"
SLOW_HANDLER_THRESHOLD_MS = 1000


class HandlerLatency:
    def __init__(self, *, handler: str, command: str | None = None, callback_prefix: str | None = None, telegram_user_id: int | None = None, session_id: int | None = None):
        self.handler = handler
        self.command = command
        self.callback_prefix = callback_prefix
        self.telegram_user_id = telegram_user_id
        self.session_id = session_id
        self.status = "ok"
        self.error_code: str | None = None
        self._started_at = time.perf_counter()
        self.db_elapsed_ms = 0
        self.render_elapsed_ms = 0
        self.telegram_api_elapsed_ms = 0
        self.callback_ack_elapsed_ms = 0
        self.message_edit_elapsed_ms = 0
        self.message_send_elapsed_ms = 0
        self.other_elapsed_ms = 0
        self.extra_fields: dict[str, str] = {}

    def add_db(self, started_at: float) -> None:
        self.db_elapsed_ms += int((time.perf_counter() - started_at) * 1000)

    def add_render(self, started_at: float) -> None:
        self.render_elapsed_ms += int((time.perf_counter() - started_at) * 1000)

    def add_telegram_api(self, started_at: float, api_kind: str | None = None) -> None:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        self.telegram_api_elapsed_ms += elapsed_ms
        if api_kind == "callback_ack":
            self.callback_ack_elapsed_ms += elapsed_ms
        elif api_kind == "message_edit":
            self.message_edit_elapsed_ms += elapsed_ms
        elif api_kind == "message_send":
            self.message_send_elapsed_ms += elapsed_ms

    def add_field(self, key: str, value: str | bool | int) -> None:
        if re.fullmatch(r"[A-Za-z0-9_]{1,32}", key):
            self.extra_fields[key] = str(value).lower() if isinstance(value, bool) else str(value)

    def set_status(self, status: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9_]{1,32}", status):
            self.status = status

    def set_error(self, error_code: str) -> None:
        self.status = "error"
        self.error_code = error_code

    def start(self) -> None:
        fields = [
            f"handler={self.handler}",
            "phase=handler_start",
        ]
        if self.command:
            fields.append(f"command={self.command}")
        if self.callback_prefix:
            fields.append(f"callback_prefix={self.callback_prefix}")
        if self.telegram_user_id is not None:
            fields.append(f"telegram_user_id={self.telegram_user_id}")
        if self.session_id is not None:
            fields.append(f"session_id={self.session_id}")
        logger.info("%s %s", HANDLER_START_LOG_PREFIX, " ".join(fields))

    def summary(self) -> None:
        elapsed_ms = int((time.perf_counter() - self._started_at) * 1000)
        known_elapsed_ms = self.db_elapsed_ms + self.render_elapsed_ms + self.telegram_api_elapsed_ms
        self.other_elapsed_ms = max(0, elapsed_ms - known_elapsed_ms)
        fields = [
            f"handler={self.handler}",
            "phase=handler_done",
            f"status={self.status}",
            f"elapsed_ms={elapsed_ms}",
            f"db_elapsed_ms={self.db_elapsed_ms}",
            f"render_elapsed_ms={self.render_elapsed_ms}",
            f"telegram_api_elapsed_ms={self.telegram_api_elapsed_ms}",
            f"callback_ack_elapsed_ms={self.callback_ack_elapsed_ms}",
            f"message_edit_elapsed_ms={self.message_edit_elapsed_ms}",
            f"message_send_elapsed_ms={self.message_send_elapsed_ms}",
            f"other_elapsed_ms={self.other_elapsed_ms}",
        ]
        if self.command:
            fields.append(f"command={self.command}")
        if self.callback_prefix:
            fields.append(f"callback_prefix={self.callback_prefix}")
        if self.telegram_user_id is not None:
            fields.append(f"telegram_user_id={self.telegram_user_id}")
        if self.session_id is not None:
            fields.append(f"session_id={self.session_id}")
        if self.error_code:
            fields.append(f"error_code={self.error_code}")
        for key in sorted(self.extra_fields):
            fields.append(f"{key}={self.extra_fields[key]}")
        payload = " ".join(fields)
        logger.info("%s %s", LATENCY_LOG_PREFIX, payload)
        if elapsed_ms >= SLOW_HANDLER_THRESHOLD_MS:
            logger.warning("%s %s", SLOW_LATENCY_LOG_PREFIX, payload)
