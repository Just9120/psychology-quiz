"""Guarded one-time PWA auth-source cutover; does not restart the application."""
from __future__ import annotations

import argparse
import hashlib
from ipaddress import ip_address
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile


LOCATION = re.compile(r"(?m)^([ \t]*)location \^~ /web/ \{\n[^{}]*?^\1\}")
KEY = re.compile(r"(?m)^[ \t]*(?:export[ \t]+)?PWA_AUTH_PROXY_PEERS[ \t]*=.*$")


def regular(path: Path) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Expected a single regular config file")
    return path.read_bytes()


def checked_replace(path: Path, before: bytes, after: bytes) -> None:
    info = path.lstat()
    if regular(path) != before:
        raise ValueError("Config changed concurrently")
    fd, name = tempfile.mkstemp(prefix=".pwa-auth-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            if hasattr(os, "fchmod"):
                os.fchmod(output.fileno(), stat.S_IMODE(info.st_mode))
                os.fchown(output.fileno(), info.st_uid, info.st_gid)
            output.write(after)
            output.flush()
            os.fsync(output.fileno())
        current = path.lstat()
        if ((info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)
                or regular(path) != before):
            raise ValueError("Config changed concurrently")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def transform(config: bytes, env: bytes, template: str, peer: str) -> tuple[bytes, bytes]:
    if "%" in peer:
        raise ValueError("Proxy peer must be one exact IP")
    address = ip_address(peer)
    peer = str(getattr(address, "ipv4_mapped", None) or address)
    text = config.decode("utf-8")
    locations = list(LOCATION.finditer(text))
    candidates = list(LOCATION.finditer(template))
    if len(locations) != 1 or len(candidates) != 1:
        raise ValueError("Expected exactly one simple PWA /web/ location")
    current = locations[0]
    if re.findall(r"\bproxy_pass\s+([^;]+);", current[0]) != ["http://127.0.0.1:8081"]:
        raise ValueError("Unexpected existing PWA upstream")
    replacement = candidates[0][0].replace("__API_PORT__", "8081")
    if "__" in replacement or "# BEGIN PWA AUTH SOURCE" not in replacement:
        raise ValueError("Invalid PWA template")
    updated = (text[:current.start()] + replacement + text[current.end():]).encode("utf-8")
    env_text = env.decode("utf-8")
    matches = list(KEY.finditer(env_text))
    if len(matches) > 1:
        raise ValueError("Duplicate proxy peer setting")
    line = "PWA_AUTH_PROXY_PEERS=" + peer
    env_text = KEY.sub(lambda _: line, env_text) if matches else env_text.rstrip("\r\n") + "\n" + line + "\n"
    return updated, env_text.encode("utf-8")


def apply(config: Path, env: Path, backup: Path, template: str, peer: str,
          expected_config: str, expected_env: str, *, run=subprocess.run) -> None:
    originals = (regular(config), regular(env))
    for data, expected in zip(originals, (expected_config, expected_env)):
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Config digest changed; inspect before retry")
    changed = transform(*originals, template, peer)
    # Fail before writing if the installed config or real-IP module is invalid.
    run(["nginx", "-t"], check=True, capture_output=True)
    backup.mkdir(mode=0o700)  # Existing backups are never overwritten.
    for name, data in zip(("nginx.conf", "runtime.env"), originals):
        with (backup / name).open("xb") as output:
            os.chmod(output.name, 0o600)
            output.write(data)
    written = []
    try:
        for path, before, after in zip((config, env), originals, changed):
            checked_replace(path, before, after)
            written.append((path, before, after))
        run(["nginx", "-t"], check=True, capture_output=True)
        run(["systemctl", "reload", "nginx"], check=True, capture_output=True)
        if (regular(config), regular(env)) != changed:
            raise ValueError("Config readback mismatch")
    except Exception:
        # Do not overwrite a concurrent administrator change during recovery.
        for path, before, after in reversed(written):
            checked_replace(path, after, before)
        run(["nginx", "-t"], check=True, capture_output=True)
        run(["systemctl", "reload", "nginx"], check=True, capture_output=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "env", "backup", "template"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--peer", required=True)
    parser.add_argument("--expected-config", required=True)
    parser.add_argument("--expected-env", required=True)
    args = parser.parse_args()
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        raise SystemExit("PWA_AUTH_PROXY_STOP: root operator required")
    for path in (args.config, args.env):
        if not path.is_absolute() or path.lstat().st_uid != 0:
            raise SystemExit("PWA_AUTH_PROXY_STOP: absolute root-owned config required")
    parent = args.backup.parent.stat()
    if (not args.backup.is_absolute() or parent.st_uid != 0
            or stat.S_IMODE(parent.st_mode) & 0o022):
        raise SystemExit("PWA_AUTH_PROXY_STOP: private root-owned backup parent required")
    try:
        apply(args.config, args.env, args.backup, args.template.read_text(encoding="utf-8"),
              args.peer, args.expected_config, args.expected_env)
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError) as error:
        # No config contents, commands, exception strings or private paths.
        raise SystemExit("PWA_AUTH_PROXY_STOP: " + type(error).__name__) from None
    print("PWA_AUTH_PROXY_CONFIG_OK application_restart_not_performed")


if __name__ == "__main__":
    main()
