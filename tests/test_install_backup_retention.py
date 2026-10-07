from pathlib import Path
import pytest
from scripts import install_backup_retention as timer

SHA = 'a' * 40
OLD = 'b' * 40

@pytest.fixture
def boundary(monkeypatch, tmp_path):
    # Never call the host systemd manager; use a faithful tiny state boundary.
    calls = []
    state = {'active': 'inactive', 'enabled': 'disabled', 'fail': False}
    def run(*args):
        calls.append(args)
        if args[0] == 'show':
            if 'ActiveState' in args[2]: return state['active']
            if 'UnitFileState' in args[2]: return state['enabled']
            if 'FragmentPath' in args[2]:
                p = tmp_path / args[1]
                return p.as_posix() if p.exists() else ''
            return ''
        if args[0] == 'enable':
            state['enabled'] = 'enabled'
            if '--now' in args: state['active'] = 'active'
        if args[0] == 'disable': state.update(active='inactive', enabled='disabled')
        if args[0] == 'start': state['active'] = 'active'
        if args[0] == 'is-active': return 'failed' if state['fail'] else state['active']
        if args[0] == 'is-enabled': return state['enabled']
        return ''
    monkeypatch.setattr(timer, 'run', run)
    # Production owner checks stay enabled; test fixtures belong to the runner.
    if timer.os.name == 'posix':
        # CI runner is not root: substitute only stat uid, never system calls.
        original = Path.lstat
        def root_stat(path):
            info = original(path)
            values = list(info); values[4] = 0
            return timer.os.stat_result(values)
        monkeypatch.setattr(Path, 'lstat', root_stat)
    return tmp_path, calls, state


def test_preflight_is_read_only_then_install_checks_timer_without_cleanup(boundary):
    root, calls, state = boundary
    assert set(timer.validate_units(root, SHA).values()) == {None}
    assert list(root.iterdir()) == []
    timer.install(root, SHA)
    assert timer.validate_units(root, SHA) == timer.definitions(SHA)
    assert state['active'] == 'active'
    assert not any(args[0] == 'start' and timer.SERVICE in args for args in calls)
    assert set(p.name for p in root.iterdir()) == {timer.SERVICE, timer.TIMER}


def test_foreign_or_partial_unit_cannot_be_overwritten(boundary):
    root, _, _ = boundary
    path = root / timer.SERVICE
    path.write_text('foreign service', encoding='utf-8')
    with pytest.raises(ValueError): timer.install(root, SHA)
    assert path.read_text() == 'foreign service'
    path.write_text(timer.definitions(OLD)[timer.SERVICE], encoding='utf-8')
    with pytest.raises(ValueError, match='partial_installation'): timer.install(root, SHA)


def test_failed_first_install_removes_only_own_new_units(boundary):
    root, _, state = boundary
    other = root / 'other-project.service'; other.write_text('unchanged')
    state['fail'] = True
    with pytest.raises(ValueError, match='timer_postcheck'): timer.install(root, SHA)
    assert list(root.iterdir()) == [other]
    assert state['active'] == 'inactive' and state['enabled'] == 'disabled'


def test_failed_update_restores_previous_units_and_timer_state(boundary):
    root, _, state = boundary
    previous = timer.definitions(OLD)
    for name, content in previous.items(): (root / name).write_text(content, encoding='utf-8')
    state.update(active='active', enabled='enabled', fail=True)
    with pytest.raises(ValueError): timer.install(root, SHA)
    assert timer.validate_units(root, OLD) == previous
    assert state['active'] == 'active' and state['enabled'] == 'enabled'
