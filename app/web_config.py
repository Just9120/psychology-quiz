"""Fail-closed web configuration. Repr deliberately excludes private values."""
from dataclasses import dataclass
import os
import re
from urllib.parse import urlsplit


def normalize_email(value: object) -> str:
    if not isinstance(value, str) or len(value) > 254:
        raise ValueError("invalid_email")
    value = value.strip().lower()
    # Owner-only conventional mailbox; no display names, control/header characters.
    if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value):
        raise ValueError("invalid_email")
    return value


@dataclass(frozen=True, repr=False)
class WebSettings:
    origin: str
    owner_email: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    sender: str
    secure_cookie: bool = True
    # Synthetic tests can exercise student account flows. Production config
    # deliberately cannot enable them before age/privacy decisions are approved.
    student_access_enabled: bool = False

    @property
    def cookie_name(self) -> str:
        return "__Host-psychology_session" if self.secure_cookie else "psychology_dev_session"

    @classmethod
    def from_env(cls):
        enabled = os.getenv("PWA_ENABLED", "false").strip().lower()
        if enabled not in {"true", "false"}:
            raise RuntimeError("Invalid PWA_ENABLED")
        if enabled != "true":
            return None
        student = os.getenv("PWA_STUDENT_ACCESS_ENABLED", "false").strip().lower()
        if student not in {"true", "false"}:
            raise RuntimeError("Invalid PWA_STUDENT_ACCESS_ENABLED")
        if student == "true":
            raise RuntimeError("Student PWA access requires approved age/privacy policy; this release keeps it disabled")
        def required(name):
            value = os.getenv(name, "").strip()
            if not value:
                raise RuntimeError(f"Missing {name}")
            return value
        origin = required("PWA_ORIGIN").rstrip("/")
        parsed = urlsplit(origin)
        local = (os.getenv("PWA_ALLOW_HTTP_LOCALHOST", "false") == "true"
                 and parsed.hostname in {"localhost", "127.0.0.1", "::1"} and parsed.scheme == "http")
        if (parsed.scheme != "https" and not local) or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise RuntimeError("PWA_ORIGIN must be an HTTPS origin")
        try:
            owner = normalize_email(required("PWA_OWNER_EMAIL"))
            sender = normalize_email(required("PWA_SMTP_FROM"))
            port = int(required("PWA_SMTP_PORT"))
        except ValueError:
            raise RuntimeError("Invalid PWA mailbox/port configuration") from None
        if port not in {465, 587}:
            raise RuntimeError("PWA SMTP requires TLS port 465 or 587")
        return cls(origin, owner, required("PWA_SMTP_HOST"), port,
                   required("PWA_SMTP_USERNAME"), required("PWA_SMTP_PASSWORD"), sender, not local)
