"""Exact CORS origins, including a finite list during a hostname transition."""
from __future__ import annotations

from urllib.parse import urlsplit


def parse_allowed_origins(value: str | None) -> frozenset[str]:
    if not value:
        return frozenset()
    origins = [part.strip() for part in value.split(',')]
    for origin in origins:
        parsed = urlsplit(origin)
        if (parsed.scheme not in {'https', 'http'} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment
                or '*' in origin or any(char.isspace() for char in origin)):
            raise ValueError('Invalid Mini App allowed origin')
        try:
            parsed.port
        except ValueError:
            raise ValueError('Invalid Mini App allowed origin') from None
    return frozenset(origins)
