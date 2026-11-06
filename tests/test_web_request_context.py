from dataclasses import replace

import pytest
from starlette.requests import Request

from app.web_auth import AuthError
from app.web_request_context import authentication_source, CLIENT_ADDRESS_HEADER
from tests.test_web_auth import SETTINGS


def request(peer, values=()):
    return Request({"type": "http", "method": "POST", "path": "/web/auth/login",
                    "client": (peer, 12345), "headers": [
                        (CLIENT_ADDRESS_HEADER.encode(), value.encode()) for value in values]})


def test_untrusted_peer_cannot_rotate_budget_with_forwarded_header():
    for values in ((), ("203.0.113.2",), ("forged",), ("203.0.113.2", "203.0.113.3")):
        assert authentication_source(request("198.51.100.8", values), SETTINGS) == "198.51.100.8"


def test_exact_trusted_peer_uses_one_canonical_address():
    settings = replace(SETTINGS, auth_proxy_peers=frozenset({"172.20.0.1"}))
    for value, expected in (("203.0.113.2", "203.0.113.2"),
                            ("::ffff:203.0.113.2", "203.0.113.2"),
                            ("2001:0db8:0:0::1", "2001:db8::1")):
        assert authentication_source(request("172.20.0.1", (value,)), settings) == expected
    # Neither the entire Docker subnet nor a claimed XFF chain is trusted.
    assert authentication_source(request("172.20.0.2", ("203.0.113.2",)), settings) == "172.20.0.2"


@pytest.mark.parametrize("values", [(), ("203.0.113.2", "203.0.113.3"),
    ("203.0.113.2, 203.0.113.3",), ("example.test",), ("203.0.113.2:80",),
    ("[2001:db8::1]:80",), ("fe80::1%eth0",), (" 203.0.113.2",), ("203.0.113.2\t",)])
def test_trusted_proxy_missing_or_ambiguous_address_fails_closed(values):
    settings = replace(SETTINGS, auth_proxy_peers=frozenset({"172.20.0.1"}))
    with pytest.raises(AuthError, match="auth_source_unavailable") as error:
        authentication_source(request("172.20.0.1", values), settings)
    assert error.value.status == 503


def test_mapped_ipv4_socket_does_not_bypass_proxy_identity():
    settings = replace(SETTINGS, auth_proxy_peers=frozenset({"172.20.0.1"}))
    assert authentication_source(request("::ffff:172.20.0.1", ("203.0.113.2",)), settings) == "203.0.113.2"
