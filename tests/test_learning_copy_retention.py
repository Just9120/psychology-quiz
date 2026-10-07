from datetime import datetime,timedelta,timezone
import json
import os

import pytest
from scripts.learning_copy_retention import mark_delivered,cleanup

NOW=datetime(2026,10,7,tzinfo=timezone.utc)


def copy(root,name='copy.json',complete=True):
    root.mkdir(mode=0o700,exist_ok=True)
    path=root/name
    path.write_text(json.dumps({'schema_version':1,'scope':'learning_data_copy','complete':complete,
                              'tables':{'quiz_answers':[]},'row_counts':{'quiz_answers':0}}))
    if os.name=='posix': path.chmod(0o600)
    return path


def test_seven_days_start_after_transfer_and_no_receipt_copy_stays(tmp_path):
    root=tmp_path/'copies';path=copy(root)
    unknown=copy(root,'not-transferred.json')
    assert cleanup(root,apply=True,now=NOW+timedelta(days=90))['removed_count']==0
    mark_delivered(root,path,now=NOW)
    assert cleanup(root,apply=True,now=NOW+timedelta(days=6,hours=23))['removed_count']==0
    assert cleanup(root,now=NOW+timedelta(days=7))=={'expired_count':1,'removed_count':0}
    assert path.exists()
    assert cleanup(root,apply=True,now=NOW+timedelta(days=7))['removed_count']==1
    assert not path.exists() and unknown.exists()


def test_incomplete_and_foreign_copies_cannot_get_receipt(tmp_path):
    root=tmp_path/'copies';path=copy(root,complete=False)
    with pytest.raises(ValueError,match='complete_learning'):
        mark_delivered(root,path,now=NOW)
    foreign=copy(tmp_path/'foreign')
    with pytest.raises(ValueError,match='owned_learning'):
        mark_delivered(root,foreign,now=NOW)
    assert path.exists() and foreign.exists()


def test_repeated_delivery_cannot_extend_timer_and_changed_copy_is_preserved(tmp_path):
    root=tmp_path/'copies';path=copy(root)
    mark_delivered(root,path,now=NOW)
    with pytest.raises(FileExistsError): mark_delivered(root,path,now=NOW+timedelta(days=1))
    path.write_text('changed')
    with pytest.raises(ValueError,match='delivered_copy_changed'):
        cleanup(root,apply=True,now=NOW+timedelta(days=8))
    assert path.exists()


def test_unsafe_receipt_is_not_a_path_escape(tmp_path):
    root=tmp_path/'copies';path=copy(root)
    mark_delivered(root,path,now=NOW)
    receipt=next((root/'.delivery-receipts').glob('*.json'))
    data=json.loads(receipt.read_text());data['filename']='../foreign.json';receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='unknown_delivery'):
        cleanup(root,apply=True,now=NOW+timedelta(days=8))
    assert path.exists()


def test_unknown_receipt_root_is_rejected_without_removing_copy(tmp_path):
    root = tmp_path / 'copies'; root.mkdir(mode=0o700)
    receipts = root / '.delivery-receipts'; receipts.mkdir(mode=0o700)
    receipt = receipts / 'unknown.json'; receipt.write_text('[]')
    if os.name == 'posix': receipt.chmod(0o600)
    copy = root / 'unreceived.json'; copy.write_text('preserve')
    with pytest.raises(ValueError, match='unknown_delivery_receipt'):
        cleanup(root, apply=True)
    assert copy.read_text() == 'preserve'
