"""Capture only this runtime's child output in private daily files (14 days)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.logging_config import redact_telegram_bot_api_urls

LOG_NAME = re.compile(r'(bot|api)-(\d{4}-\d{2}-\d{2})\.log')
COMMANDS = {
    'bot': [sys.executable, '-m', 'app.main'],
    'api': [sys.executable, '-m', 'uvicorn', 'app.miniapp_fastapi_runtime:app',
            '--host', '0.0.0.0', '--port', '8081'],
}


def private(path, directory=False):
    info = path.lstat()
    expected = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not expected or (not directory and info.st_nlink != 1):
        raise ValueError('ordinary_log_path_required')
    if os.name == 'posix' and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
        raise ValueError('private_log_owner_required')
    return info


class DailyLog:
    def __init__(self, root, service):
        if service not in COMMANDS:
            raise ValueError('known_runtime_service_required')
        self.root, self.service = Path(root), service
        if not self.root.exists() and not self.root.is_symlink():
            self.root.mkdir(mode=0o700)
        private(self.root, True)
        self.lock = threading.Lock()

    def prune(self, now=None):
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=14)).date()
        with self.lock:
            private(self.root, True)
            for path in self.root.iterdir():
                match = LOG_NAME.fullmatch(path.name)
                if not match or match[1] != self.service:
                    continue  # Never touch another service or unknown file.
                day = datetime.strptime(match[2], '%Y-%m-%d').date()
                if day <= cutoff:
                    private(path)
                    path.unlink()

    def write(self, text, now=None):
        now = now or datetime.now(timezone.utc)
        path = self.root / f'{self.service}-{now.date().isoformat()}.log'
        with self.lock:
            private(self.root, True)
            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
            fd = os.open(path, flags, 0o600)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or (os.name == 'posix' and (info.st_uid != os.geteuid() or info.st_mode & 0o077))):
                    raise ValueError('private_log_file_required')
                data = redact_telegram_bot_api_urls(text).encode('utf-8')
                # os.write may return a short write, including on full disks.
                while data:
                    size = os.write(fd, data)
                    if size <= 0:
                        raise OSError('log_write_failed')
                    data = data[size:]
            finally:
                os.close(fd)


def supervise(command, log, *, interval=3600, upkeep=None):
    """Forward termination to the real service and preserve its exit status."""
    def maintenance():
        log.prune()
        if upkeep is not None:
            try:
                upkeep()
            except (OSError, ValueError, KeyError, TypeError):
                # A concurrent operator or invalid receipt never destroys copies
                # or stops learning. Keep a private diagnostic for operator review.
                log.write('COPY_RETENTION_STOP: preserve private delivery files\n')
    maintenance()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=(os.name == 'posix'))
    stopped = threading.Event()
    failures = []
    original = {}

    def forward(signum, frame=None):
        if process.poll() is None:
            try:
                if os.name == 'posix':
                    os.killpg(process.pid, signum)
                else:
                    process.terminate()
            except ProcessLookupError:
                pass  # Child exited between poll and signal; wait still reaps it.

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGTERM, signal.SIGINT):
            original[signum] = signal.signal(signum, forward)

    def prune_quiet_logs():
        while not stopped.wait(interval):
            try:
                maintenance()
            except Exception:
                failures.append(True)
                forward(signal.SIGTERM)
                return

    worker = threading.Thread(target=prune_quiet_logs, daemon=True)
    worker.start()
    try:
        while True:
            part = process.stdout.readline(65536)
            if not part:
                break
            log.write(part.decode('utf-8', errors='replace'))
        status = process.wait()
        return 1 if failures else (status if status >= 0 else 128 - status)
    finally:
        stopped.set()
        worker.join(timeout=2)
        if process.poll() is None:
            forward(signal.SIGTERM)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()
        process.stdout.close()
        for signum, handler in original.items():
            signal.signal(signum, handler)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit('RUNTIME_LOG_STOP: known service required')
    os.umask(0o077)
    try:
        service = sys.argv[1]
        from scripts.learning_copy_retention import locked_cleanup
        upkeep = (lambda: locked_cleanup(apply=True)) if service == 'api' else None
        return supervise(COMMANDS[service], DailyLog('/data/runtime-logs', service), upkeep=upkeep)
    except (OSError, ValueError):
        print('RUNTIME_LOG_STOP: preserve private logs; inspect owned directory', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
