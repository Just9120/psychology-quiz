"""Set only Mini App URL and finite CORS origins in the private runtime .env."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import shlex
import tempfile
from urllib.parse import urlsplit


OLD = 'https://miniapp.librechat.online'
NEW = 'https://miniapp.psy.cloud-nodes.net'
VALUES = {'MINI_APP_URL': NEW, 'MINIAPP_API_ALLOWED_ORIGIN': OLD + ',' + NEW}


class ConfigValidationError(ValueError):
    """Only fixed, non-sensitive diagnostic messages may be exposed to the owner."""


def migrated_url(value: str) -> str:
    """Change only the known entrypoint origin; keep its path/query verbatim."""
    parsed = urlsplit(value)
    if (any(ord(char) <= 32 or ord(char) == 127 for char in value)
            or parsed.scheme != 'https'
            or parsed.netloc not in {urlsplit(OLD).netloc, urlsplit(NEW).netloc}
            or parsed.path not in {'', '/'} or parsed.fragment):
        raise ConfigValidationError('Unknown existing Mini App URL; config was not changed')
    return parsed._replace(netloc=urlsplit(NEW).netloc).geturl()


def read_regular(path: Path) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ConfigValidationError('Expected a regular private config file')
    return path.read_bytes()


def replace_checked(path: Path, original: bytes, changed: bytes) -> None:
    before = path.lstat()
    if read_regular(path) != original:
        raise ConfigValidationError('Runtime config changed concurrently')
    fd, name = tempfile.mkstemp(prefix='.miniapp-config-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            os.fchmod(output.fileno(), 0o600) if hasattr(os, 'fchmod') else None
            output.write(changed)
            output.flush()
            os.fsync(output.fileno())
        after = path.lstat()
        if ((before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                or read_regular(path) != original):
            raise ConfigValidationError('Runtime config changed concurrently')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def apply(path: Path, backup: Path) -> None:
    original = read_regular(path)
    text = original.decode('utf-8')
    pattern = re.compile(r'^\s*(?:export\s+)?(MINI_APP_URL|MINIAPP_API_ALLOWED_ORIGIN)\s*=')
    lines = text.splitlines(keepends=True)
    for key in VALUES:
        if sum(bool(pattern.match(line) and pattern.match(line)[1] == key) for line in lines) != 1:
            raise ConfigValidationError('Missing or duplicate config key; config was not changed')
    parsed = {}
    for line in lines:
        match = pattern.match(line)
        if match:
            lexer = shlex.shlex(line[match.end():].strip(), posix=True)
            lexer.whitespace_split = True
            lexer.commenters = '#'
            tokens = list(lexer)
            if len(tokens) != 1:
                raise ConfigValidationError('Unsupported runtime config value; config was not changed')
            parsed[match[1]] = tokens[0]
    values = dict(VALUES, MINI_APP_URL=migrated_url(parsed['MINI_APP_URL']))
    origins = {value.strip() for value in parsed['MINIAPP_API_ALLOWED_ORIGIN'].split(',')}
    if not origins or not origins.issubset({OLD, NEW}):
        raise ConfigValidationError('Unknown existing allowed origins; config was not changed')
    changed = ''.join(m[1] + '=' + values[m[1]] + '\n'
                      if (m := pattern.match(line)) else line for line in lines).encode('utf-8')
    # A private backup is required before mutation; never overwrite an existing backup.
    with backup.open('xb') as output:
        os.chmod(backup, 0o600)
        output.write(original)
    marker = backup.with_name(backup.name + '.updated-sha256')
    with marker.open('x', encoding='ascii') as output:
        os.chmod(marker, 0o600)
        output.write(hashlib.sha256(changed).hexdigest())
    replace_checked(path, original, changed)


def restore(path: Path, backup: Path) -> None:
    current = read_regular(path)
    marker = backup.with_name(backup.name + '.updated-sha256')
    expected = read_regular(marker).decode('ascii')
    if hashlib.sha256(current).hexdigest() != expected:
        raise ConfigValidationError('Runtime config changed after cutover; preserve it for manual recovery')
    replace_checked(path, current, read_regular(backup))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'restore'))
    parser.add_argument('--env', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    args = parser.parse_args()
    if not hasattr(os, 'geteuid') or os.geteuid() != 0 or args.env.lstat().st_uid != 0:
        raise SystemExit('MINIAPP_CONFIG_STOP: root-owned VPS config required')
    try:
        (apply if args.action == 'apply' else restore)(args.env, args.backup)
    except ConfigValidationError as error:
        raise SystemExit('MINIAPP_CONFIG_STOP: ' + str(error)) from None
    except (ValueError, OSError, UnicodeError) as error:
        raise SystemExit('MINIAPP_CONFIG_STOP: ' + type(error).__name__) from None
    print('MINIAPP_CONFIG_' + args.action.upper() + '_OK')


if __name__ == '__main__':
    main()
