"""Bounded transport input shared by the owner and Telegram ASGI APIs."""
from collections.abc import AsyncIterable

# Existing owner API wire limit, including the Mini App authentication envelope.
MAX_REQUEST_BODY_BYTES = 16384


class RequestBodyTooLarge(ValueError):
    pass


async def read_request_body(stream: AsyncIterable[bytes]) -> bytes:
    body = bytearray()
    async for chunk in stream:
        # Reject before copying a large chunk or consuming further input.
        if len(chunk) > MAX_REQUEST_BODY_BYTES - len(body):
            raise RequestBodyTooLarge()
        body.extend(chunk)
    return bytes(body)
