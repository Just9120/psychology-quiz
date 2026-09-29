#!/usr/bin/env python3
"""Save connector-provided UTF-8 text in ignored data/ only after exact digest check.

Send one base64 line on stdin. The script never prints content or overwrites a
capture. Source metadata and digest must be obtained independently beforehand.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
MAX_BASE64 = 8_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--encoded-file", type=Path,
                        help="ignored data/ base64 file; otherwise read one line on stdin")
    args = parser.parse_args()
    try:
        if re.fullmatch(r"[0-9a-f]{64}", args.expected_sha256) is None:
            raise ValueError("invalid_expected_digest")
        target = args.output.resolve()
        if (target.parent != (ROOT / "data").resolve() or target.suffix != ".txt"
                or args.output.is_symlink() or target.exists()):
            raise ValueError("private_capture_target_required")
        relative = target.relative_to(ROOT).as_posix()
        ignored = subprocess.run(["git", "check-ignore", "-q", "--", relative],
                                 cwd=ROOT, stdin=subprocess.DEVNULL,
                                 capture_output=True, check=False)
        if ignored.returncode != 0:
            raise ValueError("private_capture_must_be_ignored")
        if args.encoded_file is not None:
            encoded_path = args.encoded_file.resolve()
            if (encoded_path.parent != (ROOT / "data").resolve()
                    or args.encoded_file.is_symlink() or not encoded_path.is_file()
                    or not stat.S_ISREG(encoded_path.stat().st_mode)
                    or encoded_path.stat().st_size > MAX_BASE64 + 2):
                raise ValueError("private_encoded_input_required")
            encoded_relative = encoded_path.relative_to(ROOT).as_posix()
            if subprocess.run(["git", "check-ignore", "-q", "--", encoded_relative],
                              cwd=ROOT, stdin=subprocess.DEVNULL,
                              capture_output=True, check=False).returncode != 0:
                raise ValueError("private_encoded_input_must_be_ignored")
            line = encoded_path.read_bytes().strip()
        else:
            line = sys.stdin.buffer.readline(MAX_BASE64 + 2).strip()
        if not line or len(line) > MAX_BASE64:
            raise ValueError("private_capture_size_limit")
        data = base64.b64decode(line, validate=True)
        data.decode("utf-8")
        if hashlib.sha256(data).hexdigest() != args.expected_sha256:
            raise ValueError("private_capture_digest_mismatch")
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
        info = target.stat()
        if (info.st_size != len(data) or
                (os.name == "posix" and stat.S_IMODE(info.st_mode) & 0o077)):
            raise ValueError("private_capture_write_not_verified")
        print(f"PRIVATE_TEXT_CAPTURE_OK bytes={len(data)}")
        return 0
    except (ValueError, OSError, UnicodeError, binascii.Error) as error:
        print(f"PRIVATE_TEXT_CAPTURE_STOP: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
