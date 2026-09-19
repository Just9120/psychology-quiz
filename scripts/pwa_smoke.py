"""Bounded public-asset and unauthenticated routing check; sends no owner data."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import ssl
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, HTTPSHandler, Request

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.pwa_release import manifest_at


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def smoke(origin, artifact, expected, *, ca_file=None):
    manifest = manifest_at(artifact, expected)
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("An exact HTTPS origin is required")
    opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=ca_file)))

    def read(path):
        try:
            response = opener.open(Request(origin + path, headers={"Cache-Control": "no-cache"}), timeout=5)
        except HTTPError as error:
            response = error
        with closing(response):
            body = response.read(20 * 1024 * 1024 + 1)
            if len(body) > 20 * 1024 * 1024:
                raise ValueError("Unexpectedly large public response")
            return response.status, response.headers, body

    status, _, body = read("/build.json")
    if status != 200 or json.loads(body) != manifest:
        raise ValueError("Published artifact identity differs from the validated build")
    for name, expected_hash in manifest["files"].items():
        status, headers, body = read("/" + name)
        if status != 200 or hashlib.sha256(body).hexdigest() != expected_hash:
            raise ValueError("Published asset is missing or has a different digest")
        if name.endswith(".js") and "javascript" not in headers.get("Content-Type", ""):
            raise ValueError("JavaScript MIME type is invalid")
        if name == "index.html" and ("no-store" not in headers.get("Cache-Control", "")
                                     or "frame-ancestors 'none'" not in headers.get("Content-Security-Policy", "")):
            raise ValueError("Static privacy/security headers are missing")
    status, headers, body = read("/web/auth/me")
    if (status != 401 or "no-store" not in headers.get("Cache-Control", "")
            or json.loads(body) != {"ok": False, "error": "unauthorized"}):
        raise ValueError("Enabled unauthenticated web boundary must return 401/no-store")
    print(f"PWA_PUBLIC_SMOKE_OK revision={expected} assets={len(manifest['files'])}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--ca-file", help="Optional explicit private CA; certificate verification stays enabled")
    args = parser.parse_args()
    smoke(args.origin, args.artifact, args.sha, ca_file=args.ca_file)


if __name__ == "__main__":
    main()
