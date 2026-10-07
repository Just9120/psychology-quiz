"""Scoped local DB backup retention. Default is a read-only plan."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.backup_retention_plan import build_plan
from scripts.postgres_backup import read_verified_record

PROJECT = Path('/opt/psychology-quiz')


def private_path(path: Path, directory=False):
    info = path.lstat()
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or (not directory and info.st_nlink != 1):
        raise ValueError('ordinary_private_path_required')
    if os.name == 'posix' and (info.st_uid != os.geteuid() or info.st_mode & 0o077):
        raise ValueError('private_owner_required')
    return info


def read_record(path):
    private_path(path)
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('unknown_recovery_record')
    return data


def recovery_pins(state: Path):
    """Unknown or unfinished recovery stops the whole cleanup, never guesses."""
    private_path(state, True)
    current = read_record(state / 'state.json')
    if (current.get('format') != 'psychology-postgres-vps-v1'
            or current.get('project') != PROJECT.as_posix()):
        raise ValueError('foreign_postgres_state')
    if current.get('phase') != 'complete':
        raise ValueError('unfinished_postgres_operation')
    pins = set()
    # Completed recovery records stay untouched. A future recovery record with
    # unknown semantics must be reviewed before any old snapshot is removed.
    rehearsals = state / 'recovery-rehearsals'
    if rehearsals.exists() or rehearsals.is_symlink():
        private_path(rehearsals, True)
        for directory in rehearsals.iterdir():
            private_path(directory, True)
            record = read_record(directory / 'record.json')
            if (record.get('format') != 'psychology-user-recovery-v1'
                    or record.get('phase') != 'verified'
                    or record.get('restore_cleanup') != 'removed'):
                raise ValueError('unfinished_user_recovery')
    # Pin any explicitly referenced snapshots, even after the operation ends.
    def references(value):
        if isinstance(value, dict):
            for child in value.values():
                references(child)
        elif isinstance(value, list):
            for child in value:
                references(child)
        elif isinstance(value, str) and Path(value).name == 'record.json':
            path = Path(value)
            if path.parent.parent == state / 'backups':
                pins.add(path)
    references(current)
    # The vector switch record is stored below the state directory. Refuse
    # unknown JSON control records instead of treating them as completed.
    for path in state.iterdir():
        if path.suffix == '.json' and path.name != 'state.json':
            record = read_record(path)
            if (path.name != 'pgvector-upgrade.json'
                    or record.get('format') != 'psychology-pgvector-upgrade-v1'
                    or record.get('phase') != 'complete'):
                raise ValueError('unknown_or_unfinished_control_record')
            references(record)
    return pins


def plan_cleanup(state: Path, *, now=None):
    pins = recovery_pins(state)
    root = state / 'backups'
    private_path(root, True)
    result = build_plan(root, retention_days=30, pinned=pins, now=now)
    candidates = []
    for row in result['entries']:
        if row['action'] != 'REVIEW_CANDIDATE':
            continue
        directory = root / row['entry']
        private_path(directory, True)
        # Only the known two-file backup unit is eligible. Never recursively
        # remove unknown contents, logs, persistent DB files or recovery records.
        if {p.name for p in directory.iterdir()} != {'record.json', 'database.dump'}:
            raise ValueError('unknown_backup_contents')
        for name in ('record.json', 'database.dump'):
            private_path(directory / name)
        record = read_verified_record(directory / 'record.json')
        candidates.append({'entry': directory.name,
                           'record_sha256': hashlib.sha256((directory/'record.json').read_bytes()).hexdigest(),
                           'dump_sha256': record['dump_sha256']})
    return {'format': 'psychology-local-backup-cleanup-v1',
            'retention_days': 30, 'min_verified_per_cluster': 2,
            'observed_at': (now or datetime.now(timezone.utc)).isoformat(),
            'candidates': candidates, 'candidate_count': len(candidates)}


def apply_cleanup(state: Path, expected, *, now=None):
    fresh = plan_cleanup(state, now=now)
    if fresh['candidates'] != expected['candidates']:
        raise ValueError('backup_plan_changed')
    removed = []
    for item in fresh['candidates']:
        # Recheck recovery and unit content before each irreversible unit.
        pins = recovery_pins(state)
        directory = state / 'backups' / item['entry']
        if directory / 'record.json' in pins:
            raise ValueError('backup_became_pinned')
        private_path(directory, True)
        if {p.name for p in directory.iterdir()} != {'record.json', 'database.dump'}:
            raise ValueError('unknown_backup_contents')
        for name in ('record.json', 'database.dump'):
            private_path(directory / name)
        record = read_verified_record(directory / 'record.json')
        if (record['dump_sha256'] != item['dump_sha256']
                or hashlib.sha256((directory/'record.json').read_bytes()).hexdigest() != item['record_sha256']):
            raise ValueError('backup_unit_changed')
        (directory / 'database.dump').unlink()
        (directory / 'record.json').unlink()
        directory.rmdir()
        removed.append(item['entry'])
    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    revision = parser.add_mutually_exclusive_group()
    revision.add_argument('--expected-sha')
    revision.add_argument('--scheduled-from')
    args = parser.parse_args()
    # Production target is fixed; no caller-supplied directory or remote DB.
    if os.name != 'posix' or os.geteuid() != 0:
        raise SystemExit('BACKUP_RETENTION_STOP: root Linux operator required')
    import fcntl
    if PROJECT.resolve(strict=True) != PROJECT:
        raise SystemExit('BACKUP_RETENTION_STOP: physical target required')
    fd = os.open('/tmp/psychology-quiz-deploy.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o022:
            raise ValueError('unsafe_lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.apply:
            anchor = args.scheduled_from or args.expected_sha
            if not anchor or not re.fullmatch(r'[0-9a-f]{40}', anchor):
                raise ValueError('expected_revision_required')
            def git(*args):
                return subprocess.check_output(['git', '-C', str(PROJECT), *args],
                    text=True, stderr=subprocess.DEVNULL).strip()
            current_sha = git('rev-parse', 'HEAD')
            if args.scheduled_from:
                subprocess.run(['git', '-C', str(PROJECT), 'merge-base', '--is-ancestor', anchor, current_sha],
                               check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if (not re.fullmatch(r'[0-9a-f]{40}', current_sha)
                    or (not args.scheduled_from and current_sha != args.expected_sha)
                    or git('branch', '--show-current') != 'main'
                    or git('remote', 'get-url', 'origin') not in {
                        'https://github.com/Just9120/psychology-quiz.git',
                        'git@github.com:Just9120/psychology-quiz.git'}):
                raise ValueError('foreign_revision_or_repository')
            if git('diff', '--name-only') or git('diff', '--cached', '--name-only'):
                raise ValueError('uncommitted_runtime_changes')
        plan = plan_cleanup(PROJECT / '.postgres')
        if args.apply:
            removed = apply_cleanup(PROJECT / '.postgres', plan)
            print(json.dumps({'result': 'BACKUP_RETENTION_OK', 'removed_count': len(removed)}))
        else:
            print(json.dumps(plan, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
        print('BACKUP_RETENTION_STOP: preserve backups; inspect private recovery state', file=sys.stderr)
        return 1
    finally:
        os.close(fd)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
