"""Linux CI: run the actual HTTPS template against a synthetic upstream and built assets."""
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import URLError, HTTPError
from urllib.request import urlopen, Request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.pwa_release import stage, activate, MARKER
from scripts.pwa_smoke import smoke


def main():
    nginx = shutil.which("nginx")
    if not nginx:
        raise RuntimeError("Nginx is required for this CI check")
    artifact = ROOT / "pwa/dist"
    sha = json.loads((artifact / "build.json").read_text())["revision"]
    received = []

    class Upstream(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.path, self.headers.get_all("X-Psychology-Client-Address")))
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b'{"ok":false,"error":"unauthorized"}')

        def log_message(self, *args):
            pass

    with tempfile.TemporaryDirectory(prefix="pwa-nginx-") as temp:
        temp = Path(temp)
        site = temp / "site"
        site.mkdir()
        (site / ".pwa-root").write_text(MARKER)
        stage(artifact, site, sha)
        activate(site, sha, "NONE")
        cert, key = temp / "cert.pem", temp / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-keyout", str(key), "-out", str(cert), "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], check=True, capture_output=True)
        with closing(socket.socket()) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        template = (ROOT / "deployment/pwa/nginx.conf.template").read_text()
        for token, value in {"__HTTPS_BIND__": f"127.0.0.1:{port}", "__PWA_HOST__": "localhost",
                             "__TLS_CERTIFICATE__": str(cert), "__TLS_KEY__": str(key),
                             "__PWA_RELEASE_ROOT__": str(site), "__API_PORT__": str(upstream.server_port)}.items():
            template = template.replace(token, value)
        with closing(socket.socket()) as sock:
            sock.bind(("127.0.0.1", 0))
            proxy_port = sock.getsockname()[1]
        # This SECOND test-only listener models a trusted edge using loopback.
        # The actual template above retains only the published Cloudflare peers.
        edge_fixture = template.replace(f"127.0.0.1:{port} ssl", f"127.0.0.1:{proxy_port} ssl").replace(
            "# BEGIN PWA AUTH SOURCE", "# BEGIN PWA AUTH SOURCE\n        set_real_ip_from 127.0.0.1;")
        config = temp / "nginx.conf"
        config.write_text(f'pid {temp}/nginx.pid; error_log {temp}/error.log; events {{}}\n'
                          f'http {{ access_log off; client_body_temp_path {temp}/body; proxy_temp_path {temp}/proxy; '
                          f'fastcgi_temp_path {temp}/fastcgi; uwsgi_temp_path {temp}/uwsgi; scgi_temp_path {temp}/scgi; '
                          'types { text/html html; application/javascript js; text/css css; '
                          'image/png png; image/svg+xml svg; application/json json; }\n' + template + '\n' + edge_fixture + '\n}')
        subprocess.run([nginx, "-p", str(temp), "-c", str(config), "-t"], check=True)
        server = subprocess.Popen([nginx, "-p", str(temp), "-c", str(config), "-g", "daemon off;"])
        origin = f"https://127.0.0.1:{port}"
        context = ssl.create_default_context(cafile=cert)
        try:
            for attempt in range(60):
                try:
                    with urlopen(origin + "/build.json", context=context, timeout=1):
                        break
                except URLError:
                    if server.poll() is not None:
                        raise RuntimeError("Nginx exited before readiness")
                    time.sleep(.05)
            smoke(origin, artifact, sha, ca_file=str(cert))
            assert received == [("/web/auth/me", ["127.0.0.1"])], "API path and source must be preserved"
            # The real template must overwrite, rather than append, a client's
            # private header. CF/XFF claims from a direct socket are untrusted.
            request = Request(origin + "/web/auth/me", headers={
                "X-Psychology-Client-Address": "203.0.113.7",
                "X-Forwarded-For": "203.0.113.8",
                "CF-Connecting-IP": "203.0.113.9"})
            try:
                urlopen(request, context=context, timeout=2)
            except HTTPError as error:
                assert error.code == 401
                error.close()
            else:
                raise AssertionError("Synthetic API must return 401")
            assert received[-1] == ("/web/auth/me", ["127.0.0.1"])
            edge_request = Request(f"https://127.0.0.1:{proxy_port}/web/auth/me", headers={
                "CF-Connecting-IP": "203.0.113.9",
                "X-Psychology-Client-Address": "203.0.113.7", "X-Forwarded-For": "203.0.113.8"})
            try:
                urlopen(edge_request, context=context, timeout=2)
            except HTTPError as error:
                assert error.code == 401
                error.close()
            else:
                raise AssertionError("Synthetic API must return 401")
            assert received[-1] == ("/web/auth/me", ["203.0.113.9"])
        finally:
            server.terminate()
            server.wait(timeout=5)
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=5)
        print("PWA_NGINX_TEMPLATE_OK")


if __name__ == "__main__":
    main()
