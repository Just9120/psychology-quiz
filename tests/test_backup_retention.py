from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pytest
from scripts.backup_retention import plan_cleanup, apply_cleanup
from scripts.postgres_backup import file_digest

NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)


def state(root):
    root.mkdir(mode=0o700)
    (root/'backups').mkdir(mode=0o700)
    write(root/'state.json', {'phase':'complete','format':'psychology-postgres-vps-v1','project':'/opt/psychology-quiz'})
    for n in range(1,4):
        d=root/'backups'/f'release-old{n}'
        d.mkdir(mode=0o700)
        dump=d/'database.dump'
        dump.write_bytes(b'synthetic backup')
        if os.name == 'posix': dump.chmod(0o600)
        write(d/'record.json', {'format':'psychology-postgres-recovery-v1', 'phase':'verified',
            'source':{'project':'psychology-quiz','database':'psychology_atlas',
                      'service':'psych_quiz_postgres','cluster':'123'},
            'created_at':f'2026-01-0{n}T00:00:00Z', 'verified_at':f'2026-01-0{n}T00:00:00Z',
            'dump_bytes':dump.stat().st_size,'dump_sha256':file_digest(dump)})
    return root


def write(path, value):
    path.write_text(json.dumps(value),encoding='utf-8')
    if os.name=='posix': path.chmod(0o600)


def test_only_old_verified_unit_removed_and_latest_two_preserved(tmp_path):
    root=state(tmp_path/'state')
    before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    plan=plan_cleanup(root,now=NOW)
    assert [r['entry'] for r in plan['candidates']]==['release-old1']
    assert before=={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert apply_cleanup(root,plan,now=NOW)==['release-old1']
    assert sorted(p.name for p in (root/'backups').iterdir())==['release-old2','release-old3']
    assert plan_cleanup(root,now=NOW)['candidate_count']==0


def test_control_reference_pins_old_backup(tmp_path):
    root=state(tmp_path/'state')
    write(root/'state.json',{'phase':'complete','format':'psychology-postgres-vps-v1','project':'/opt/psychology-quiz','recovery_record':str(root/'backups/release-old1/record.json')})
    assert plan_cleanup(root,now=NOW)['candidate_count']==0


@pytest.mark.parametrize('phase',['creating_restore','failed','prepared'])
def test_unfinished_recovery_blocks_all_cleanup(tmp_path,phase):
    root=state(tmp_path/'state')
    recovery=root/'recovery-rehearsals/rehearsal-owned'
    recovery.mkdir(parents=True,mode=0o700)
    if os.name=='posix': recovery.parent.chmod(0o700)
    write(recovery/'record.json',{'format':'psychology-user-recovery-v1','phase':phase,'restore_cleanup':'pending'})
    with pytest.raises(ValueError,match='unfinished_user_recovery'):
        plan_cleanup(root,now=NOW)
    assert (root/'backups/release-old1/database.dump').exists()


def test_unknown_backup_file_and_changed_plan_fail_closed(tmp_path):
    root=state(tmp_path/'state')
    plan=plan_cleanup(root,now=NOW)
    (root/'backups/release-old1/unknown').write_text('keep')
    with pytest.raises(ValueError,match='unknown_backup_contents'):
        apply_cleanup(root,plan,now=NOW)
    assert (root/'backups/release-old1/database.dump').exists()


def test_changed_dump_is_kept_before_any_deletion(tmp_path):
    root=state(tmp_path/'state')
    plan=plan_cleanup(root,now=NOW)
    dump=root/'backups/release-old1/database.dump'
    dump.write_bytes(b'changed after plan')
    with pytest.raises(ValueError,match='backup_plan_changed'):
        apply_cleanup(root,plan,now=NOW)
    assert dump.exists()


def test_foreign_state_is_not_a_cleanup_target(tmp_path):
    root=state(tmp_path/'state')
    write(root/'state.json',{'phase':'complete','format':'other','project':'/other'})
    with pytest.raises(ValueError,match='foreign_postgres_state'):
        plan_cleanup(root,now=NOW)



def test_unknown_completed_control_record_preserves_all_copies(tmp_path):
    root = state(tmp_path / 'state')
    write(root / 'unknown.json', {'phase': 'complete', 'format': 'foreign'})
    with pytest.raises(ValueError, match='unknown_or_unfinished_control_record'):
        plan_cleanup(root, now=NOW)
    assert (root / 'backups/release-old1/database.dump').exists()
