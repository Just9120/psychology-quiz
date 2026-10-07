from pathlib import Path
import os

import pytest
from scripts import export_learning_data as export


def runtime(monkeypatch,tmp_path):
    data=tmp_path/'data'
    data.mkdir()
    monkeypatch.setattr(export,'ROOT',Path('/app'))
    monkeypatch.setattr(export,'RUNTIME_DATA',data)
    return data


def test_runtime_export_uses_persistent_private_mount_without_git(monkeypatch,tmp_path):
    data=runtime(monkeypatch,tmp_path)
    path=export.export_target(data/'learning-copies/copy.json')
    assert path==data/'learning-copies/copy.json'
    if os.name=='posix': assert path.parent.stat().st_mode & 0o077==0
    for foreign in (tmp_path/'copy.json',data/'copy.json',data/'learning-copies/file.txt'):
        with pytest.raises(ValueError,match='persistent_private'):
            export.export_target(foreign)


def test_host_checkout_keeps_existing_ignored_target_policy(monkeypatch,tmp_path):
    monkeypatch.setattr(export,'ROOT',tmp_path)
    called=[]
    monkeypatch.setattr(export,'private_json_target',lambda raw,root:(called.append((raw,root)),raw)[1])
    target=tmp_path/'data/copy.json'
    assert export.export_target(target)==target
    assert called==[(target,tmp_path)]
