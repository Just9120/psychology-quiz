from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from scripts.runtime_log import DailyLog, supervise

NOW = datetime(2026,10,7,12,tzinfo=timezone.utc)


def test_daily_logs_private_redacted_and_retention_leaves_foreign_files(tmp_path):
    log=DailyLog(tmp_path/'logs','api')
    log.write('https://api.telegram.org/botsecret-token/sendMessage\n',now=NOW)
    log.write('expired\n',now=NOW-timedelta(days=14))
    log.write('retain\n',now=NOW-timedelta(days=13))
    (log.root/'unknown.log').write_text('keep')
    other=DailyLog(log.root,'bot')
    other.write('other\n',now=NOW-timedelta(days=20))
    log.prune(now=NOW)
    assert not (log.root/'api-2026-09-23.log').exists()
    assert (log.root/'api-2026-09-24.log').read_text()=='retain\n'
    assert 'secret-token' not in (log.root/'api-2026-10-07.log').read_text()
    assert (log.root/'bot-2026-09-17.log').exists()
    assert (log.root/'unknown.log').exists()
    if os.name=='posix':
        assert (log.root/'api-2026-10-07.log').stat().st_mode & 0o077==0
        assert log.root.stat().st_mode & 0o077==0


def test_child_stdout_stderr_and_failure_status_are_preserved(tmp_path):
    log=DailyLog(tmp_path/'logs','api')
    result=supervise([sys.executable,'-c',"import sys; print('stdout'); print('stderr',file=sys.stderr); sys.exit(7)"],log)
    assert result==7
    content=''.join(p.read_text() for p in log.root.glob('api-*.log'))
    assert 'stdout' in content and 'stderr' in content


@pytest.mark.skipif(os.name!='posix',reason='Real Linux process-group lifecycle; required in CI')
def test_real_wrapper_forwards_sigterm_and_waits_for_service(tmp_path):
    import signal
    ready=tmp_path/'ready'
    done=tmp_path/'done'
    code="import signal,time; from pathlib import Path; signal.signal(signal.SIGTERM,lambda *_:(Path(%r).write_text('stopped'),exit(0))); Path(%r).write_text('ready'); time.sleep(30)"%(str(done),str(ready))
    wrapper="from scripts.runtime_log import DailyLog,supervise; raise SystemExit(supervise(%r,DailyLog(%r,'api')))"%([sys.executable,'-c',code],str(tmp_path/'logs'))
    proc=subprocess.Popen([sys.executable,'-c',wrapper])
    try:
        deadline=time.monotonic()+5
        while not ready.exists() and time.monotonic()<deadline: time.sleep(0.02)
        assert ready.exists()
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=5)==0
        assert done.read_text()=='stopped'
    finally:
        if proc.poll() is None: proc.kill(); proc.wait()


def test_log_hardlink_is_not_written_or_pruned(tmp_path):
    log=DailyLog(tmp_path/'logs','api')
    target=tmp_path/'private'
    target.write_text('keep')
    if os.name=='posix': target.chmod(0o600)
    alias=log.root/'api-2026-10-07.log'
    os.link(target,alias)
    with pytest.raises(ValueError): log.write('overwrite',now=NOW)
    assert target.read_text()=='keep'
    with pytest.raises(ValueError): log.prune(now=NOW+timedelta(days=14))
    assert alias.exists() and target.read_text()=='keep'
