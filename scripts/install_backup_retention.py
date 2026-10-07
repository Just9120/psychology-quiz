"""Install only the owned local backup timer after exact-revision delivery."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.backup_retention import PROJECT, plan_cleanup

UNITS = Path('/etc/systemd/system')
SERVICE = 'psychology-quiz-backup-retention.service'
TIMER = 'psychology-quiz-backup-retention.timer'
SHA = re.compile(r'[0-9a-f]{40}')


def definitions(revision):
    if not SHA.fullmatch(revision):
        raise ValueError('exact_revision_required')
    return {
        SERVICE: f"""# Managed by psychology-quiz; local backups only.
[Unit]
Description=PsychologyAtlas verified local backup retention
[Service]
Type=oneshot
User=root
UMask=0077
WorkingDirectory=/opt/psychology-quiz
ExecStart=/usr/bin/python3 /opt/psychology-quiz/scripts/backup_retention.py --apply --scheduled-from {revision}
ProtectSystem=strict
ProtectHome=yes
NoNewPrivileges=yes
ReadWritePaths=/opt/psychology-quiz/.postgres /tmp/psychology-quiz-deploy.lock
TimeoutStartSec=300
StandardOutput=null
StandardError=null
""",
        TIMER: """# Managed by psychology-quiz; local backups only.
[Unit]
Description=Daily PsychologyAtlas local backup retention
[Timer]
OnCalendar=*-*-* 03:00:00 UTC
RandomizedDelaySec=30m
Persistent=true
Unit=psychology-quiz-backup-retention.service
[Install]
WantedBy=timers.target
""",
    }


def run(*args):
    return subprocess.check_output(['systemctl', *args], text=True,
                                   stderr=subprocess.DEVNULL).strip()


def validate_units(directory, revision):
    info = directory.lstat()
    if (not stat.S_ISDIR(info.st_mode)
            or (os.name == 'posix' and (info.st_uid != 0 or info.st_mode & 0o022))):
        raise ValueError('unsafe_unit_directory')
    expected = definitions(revision)
    existing = {}
    for name, content in expected.items():
        path = directory / name
        fragment = run('show', name, '--property=FragmentPath', '--value')
        if fragment and fragment != path.as_posix():
            raise ValueError('foreign_unit_location')
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or (os.name == 'posix' and (info.st_uid != 0 or info.st_mode & 0o022))):
                raise ValueError('unsafe_unit_file')
            original = path.read_text(encoding='utf-8')
            if name == SERVICE:
                matches = re.findall(r'--scheduled-from ([0-9a-f]{40})', original)
                if len(matches) != 1 or original != definitions(matches[0])[name]:
                    raise ValueError('unrecognized_existing_unit')
            elif original != content:
                raise ValueError('unrecognized_existing_unit')
            existing[name] = original
        else:
            existing[name] = None
    if (existing[SERVICE] is None) != (existing[TIMER] is None):
        raise ValueError('partial_installation_requires_review')
    for name in expected:
        dropins = run('show', name, '--property=DropInPaths', '--value')
        if dropins:
            raise ValueError('foreign_unit_override')
    return existing


def atomic_write(path, content):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.psychology-retention-')
    try:
        os.fchmod(fd, 0o644) if os.name == 'posix' else None
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(directory, revision):
    before = validate_units(directory, revision)
    enabled = run('show', TIMER, '--property=UnitFileState', '--value')
    active = run('show', TIMER, '--property=ActiveState', '--value')
    if enabled not in {'', 'disabled', 'enabled'} or active not in {'', 'inactive', 'active'}:
        raise ValueError('unexpected_timer_state')
    try:
        # No cleanup is started here. The service waits for its scheduled time
        # and takes the shared deployment lock before examining any backup.
        if validate_units(directory, revision) != before:
            raise ValueError('unit_changed_during_install')
        for name, content in definitions(revision).items():
            atomic_write(directory / name, content)
        run('daemon-reload')
        run('enable', '--now', TIMER)
        if run('is-active', TIMER) != 'active' or run('is-enabled', TIMER) != 'enabled':
            raise ValueError('timer_postcheck_failed')
        if validate_units(directory, revision) != definitions(revision):
            raise ValueError('unit_readback_mismatch')
    except Exception:
        # Restore only these two known units; never restore database data.
        run('disable', '--now', TIMER)
        for name, content in before.items():
            if content is None:
                (directory / name).unlink(missing_ok=True)
            else:
                atomic_write(directory / name, content)
        run('daemon-reload')
        if enabled == 'enabled':
            run('enable', TIMER)
        if active == 'active':
            run('start', TIMER)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'install'))
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--lock-held', action='store_true')
    args = parser.parse_args()
    fd = None
    try:
        if os.name != 'posix' or os.geteuid() != 0 or ROOT != PROJECT or PROJECT.resolve(strict=True) != PROJECT:
            raise ValueError('fixed_root_linux_target_required')
        if not SHA.fullmatch(args.expected_sha):
            raise ValueError('exact_revision_required')
        import fcntl
        fd = 200 if args.lock_held else os.open('/tmp/psychology-quiz-deploy.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or info.st_mode & 0o022
                or (info.st_dev, info.st_ino) != (os.lstat('/tmp/psychology-quiz-deploy.lock').st_dev, os.lstat('/tmp/psychology-quiz-deploy.lock').st_ino)):
            raise ValueError('unsafe_deployment_lock')
        if not args.lock_held:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def git(*values):
            return subprocess.check_output(['git', '-C', str(PROJECT), *values], text=True, stderr=subprocess.DEVNULL).strip()
        if (git('rev-parse', 'HEAD') != args.expected_sha or git('branch', '--show-current') != 'main'
                or git('remote', 'get-url', 'origin') not in {'https://github.com/Just9120/psychology-quiz.git', 'git@github.com:Just9120/psychology-quiz.git'}
                or git('diff', '--name-only') or git('diff', '--cached', '--name-only')):
            raise ValueError('unverified_checkout')
        validate_units(UNITS, args.expected_sha)
        plan_cleanup(PROJECT / '.postgres')
        if args.action == 'install':
            install(UNITS, args.expected_sha)
        print('BACKUP_TIMER_' + ('OK' if args.action == 'install' else 'PREFLIGHT_OK') + ' revision=' + args.expected_sha)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError):
        print('BACKUP_TIMER_STOP: preserve backups; inspect owned timer and recovery state', file=sys.stderr)
        return 1
    finally:
        if fd is not None and not args.lock_held:
            os.close(fd)


if __name__ == '__main__':
    raise SystemExit(main())
