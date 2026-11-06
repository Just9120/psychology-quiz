"""Authentication source identity from the socket and explicitly trusted proxy."""
from ipaddress import ip_address

from app.web_auth import AuthError

CLIENT_ADDRESS_HEADER = "x-psychology-client-address"


def canonical_address(value: str) -> str:
    # A forwarded address is one IP, never a chain, hostname, port or zone ID.
    if not isinstance(value, str) or value != value.strip() or "%" in value:
        raise ValueError("invalid_client_address")
    address = ip_address(value)
    mapped = getattr(address, "ipv4_mapped", None)
    return str(mapped if mapped is not None else address)


def authentication_source(request, settings) -> str:
    try:
        peer = canonical_address(request.client.host)
    except (AttributeError, ValueError):
        raise AuthError("auth_source_unavailable", 503) from None
    values = request.headers.getlist(CLIENT_ADDRESS_HEADER)
    if peer not in settings.auth_proxy_peers:
        # Never let an untrusted caller rotate its budget using supplied headers.
        return peer
    if len(values) != 1:
        raise AuthError("auth_source_unavailable", 503)
    try:
        return canonical_address(values[0])
    except ValueError:
        raise AuthError("auth_source_unavailable", 503) from None
