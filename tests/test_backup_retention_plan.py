from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from scripts.backup_retention_plan import build_plan
from scripts.postgres_backup import file_digest

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def backup(root, name, verified, *, cluster="123", phase="verified"):
    directory = root / name
    directory.mkdir()
    dump = directory / "database.dump"
    dump.write_bytes(b"synthetic private backup")
    record = {"format": "psychology-postgres-recovery-v1", "phase": phase,
              "source": {"project": "psychology-quiz", "database": "psychology_atlas",
                         "service": "psych_quiz_postgres", "cluster": cluster},
              "created_at": verified, "verified_at": verified,
              "dump_bytes": dump.stat().st_size, "dump_sha256": file_digest(dump)}
    (directory / "record.json").write_text(json.dumps(record))
    return directory


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob('*') if path.is_file()}


def test_plan_preserves_two_verified_points_per_cluster_and_does_not_mutate(tmp_path):
    for n in range(1, 4):
        backup(tmp_path, f"release-old{n}", f"2026-01-0{n}T00:00:00Z")
    backup(tmp_path, "release-other", "2025-01-01T00:00:00Z", cluster="456")
    before = snapshot(tmp_path)
    result = build_plan(tmp_path, retention_days=30, now=NOW)
    assert result['plan_only'] and result['deletion_supported'] is False
    assert [row['entry'] for row in result['entries'] if row['action'] == 'REVIEW_CANDIDATE'] == ['release-old1']
    assert snapshot(tmp_path) == before
    assert 'synthetic private backup' not in json.dumps(result)
    assert build_plan(tmp_path, now=NOW)['candidate_count'] == 0
    assert build_plan(tmp_path, retention_days=30, pinned=[tmp_path/'release-old1'/'record.json'], now=NOW)['candidate_count'] == 0


def test_unverified_old_unknown_corrupt_and_future_records_are_kept(tmp_path):
    old = backup(tmp_path, "release-legacy", "2026-01-01T00:00:00Z")
    record = json.loads((old/'record.json').read_text())
    del record['verified_at']
    (old/'record.json').write_text(json.dumps(record))
    backup(tmp_path, "release-failed", "2026-01-01T00:00:00Z", phase="failed")
    bad = backup(tmp_path, "release-corrupt", "2026-01-01T00:00:00Z")
    (bad/'database.dump').write_bytes(b"modified")
    backup(tmp_path, "release-future", "2027-01-01T00:00:00Z")
    (tmp_path/'unrecognized.txt').write_text('private unknown artifact')
    invalid = tmp_path/'release-invalid'
    invalid.mkdir()
    (invalid/'database.dump').write_bytes(b'unknown')
    (invalid/'record.json').write_text('[]')
    before = snapshot(tmp_path)
    result = build_plan(tmp_path, retention_days=1, now=NOW)
    assert result['candidate_count'] == 0
    assert all(row['action'] == 'KEEP' for row in result['entries'])
    assert snapshot(tmp_path) == before


def test_unsafe_policy_root_or_foreign_pin_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='at_least_two'):
        build_plan(tmp_path, min_verified=1)
    with pytest.raises(ValueError, match='invalid_retention'):
        build_plan(tmp_path, retention_days=True)
    with pytest.raises(ValueError, match='pin_outside'):
        build_plan(tmp_path, pinned=[tmp_path.parent/'foreign'/'record.json'])
    file = tmp_path/'regular-file'
    file.write_bytes(b'no directory')
    with pytest.raises(ValueError, match='ordinary_backup'):
        build_plan(file)


def test_new_verified_records_capture_explicit_utc_times_without_changing_manifest(tmp_path):
    from scripts.postgres_backup import backup_and_rehearse, read_verified_record
    class Runtime:
        def require_stopped_writers(self): pass
        def manifest(self, database=None): return {'synthetic': 'exact manifest'}
        def identity(self): return {'project': 'psychology-quiz'}
        def dump(self, path): path.write_bytes(b'synthetic dump')
        def create_restore_database(self, name): self.created = name
        def restore(self, dump, database): assert database == self.created
        def drop_restore_database(self, name): assert name == self.created
    path = backup_and_rehearse(Runtime(), tmp_path/'backups')
    record = read_verified_record(path)
    assert record['before'] == {'synthetic': 'exact manifest'}
    assert datetime.fromisoformat(record['created_at']) <= datetime.fromisoformat(record['verified_at'])
    assert datetime.fromisoformat(record['verified_at']).utcoffset().total_seconds() == 0
