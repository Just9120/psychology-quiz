"""Private copy retention starts only after an explicit operator delivery receipt."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT=Path(__file__).resolve().parents[1]
DATA=Path('/data/learning-copies') if ROOT==Path('/app') else ROOT/'data/learning-copies'


def private(path, directory=False):
    info=path.lstat()
    valid=stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid or (not directory and info.st_nlink!=1):
        raise ValueError('ordinary_copy_path_required')
    if os.name=='posix' and (info.st_uid!=os.geteuid() or info.st_mode & 0o077):
        raise ValueError('private_copy_owner_required')


def timestamp(value):
    result=datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset()!=timedelta(0):
        raise ValueError('utc_delivery_time_required')
    return result


def digest(path):
    sha=hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda:stream.read(1024*1024),b''): sha.update(part)
    return sha.hexdigest()


def complete_copy(path):
    private(path)
    with path.open(encoding='utf-8') as stream: data=json.load(stream)
    scopes={1:'learning_data_copy',2:'profile_and_learning_data_copy'}
    if (not isinstance(data,dict) or type(data.get('schema_version')) is not int
            or data.get('complete') is not True or data.get('scope')!=scopes.get(data.get('schema_version'))
            or not isinstance(data.get('tables'),dict) or not isinstance(data.get('row_counts'),dict)
            or set(data['tables'])!=set(data['row_counts'])):
        raise ValueError('complete_learning_copy_required')
    for name, rows in data['tables'].items():
        if not isinstance(rows,list) or type(data['row_counts'][name]) is not int or len(rows)!=data['row_counts'][name]:
            raise ValueError('complete_learning_copy_required')
    return digest(path)


def record_path(root, filename):
    return root/'.delivery-receipts'/(hashlib.sha256(filename.encode('utf-8')).hexdigest()+'.json')


def mark_delivered(root, path, *, now=None):
    root, path=Path(root),Path(path)
    private(root,True)
    if path.parent!=root or path.suffix.lower()!='.json':
        raise ValueError('owned_learning_copy_required')
    now=now or datetime.now(timezone.utc)
    timestamp(now.isoformat())
    sha=complete_copy(path)
    target=record_path(root,path.name)
    if not target.parent.exists() and not target.parent.is_symlink(): target.parent.mkdir(mode=0o700)
    private(target.parent,True)
    record={'format':'psychology-copy-retention-v1','filename':path.name,'sha256':sha,
            'delivered_at':now.isoformat(),'expires_at':(now+timedelta(days=7)).isoformat()}
    # Repeating delivery cannot reset the timer. Changed/incomplete files never
    # acquire an apparently successful receipt; no sending is done here.
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:
        json.dump(record,stream,sort_keys=True); stream.flush(); os.fsync(stream.fileno())
    return record


def cleanup(root, *, apply=False, now=None):
    root=Path(root)
    if not root.exists() and not root.is_symlink(): return {'expired_count':0,'removed_count':0}
    private(root,True)
    now=now or datetime.now(timezone.utc)
    timestamp(now.isoformat())
    receipts=root/'.delivery-receipts'
    if not receipts.exists() and not receipts.is_symlink(): return {'expired_count':0,'removed_count':0}
    private(receipts,True)
    pending=[]
    for receipt in sorted(receipts.iterdir()):
        private(receipt)
        with receipt.open(encoding='utf-8') as stream: record=json.load(stream)
        filename=record.get('filename')
        if (not isinstance(record,dict) or record.get('format')!='psychology-copy-retention-v1' or not isinstance(filename,str)
                or Path(filename).name!=filename or filename in ('.','..')
                or Path(filename).suffix.lower()!='.json' or record_path(root,filename)!=receipt):
            raise ValueError('unknown_delivery_receipt')
        delivered,expires=timestamp(record['delivered_at']),timestamp(record['expires_at'])
        if delivered>now or expires!=delivered+timedelta(days=7):
            raise ValueError('invalid_delivery_window')
        path=root/filename
        private(path)
        if digest(path)!=record.get('sha256'):
            raise ValueError('delivered_copy_changed')
        if now>=expires: pending.append((path,receipt,record))
    # Validate the entire set before deleting any file. Unknown/unreceived
    # copies, unrelated artifacts and all database state are never candidates.
    removed=0
    if apply:
        for path,receipt,record in pending:
            private(path); private(receipt)
            with receipt.open(encoding='utf-8') as stream: fresh=json.load(stream)
            if fresh!=record or digest(path)!=record['sha256']:
                raise ValueError('delivery_state_changed')
            path.unlink(); receipt.unlink(); removed+=1
    return {'expired_count':len(pending),'removed_count':removed}


def locked_cleanup(root=DATA, *, apply=False):
    root=Path(root)
    if not root.exists() and not root.is_symlink(): return {'expired_count':0,'removed_count':0}
    private(root,True)
    import fcntl
    fd=os.open(root/'.retention.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        private(root/'.retention.lock')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return cleanup(root,apply=apply)
    finally: os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mark-delivered',type=Path)
    parser.add_argument('--confirmed-transfer',action='store_true')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        if args.mark_delivered:
            if not args.confirmed_transfer or args.apply:
                raise ValueError('explicit_completed_transfer_required')
            private(DATA,True)
            import fcntl
            fd=os.open(DATA/'.retention.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
            try:
                private(DATA/'.retention.lock')
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                mark_delivered(DATA,args.mark_delivered)
            finally: os.close(fd)
            print('COPY_DELIVERY_RECORDED; cleanup due seven days after transfer')
        else:
            if args.confirmed_transfer:
                raise ValueError('explicit_copy_required')
            print(json.dumps(locked_cleanup(apply=args.apply),sort_keys=True))
    except (OSError,ValueError,TypeError,KeyError):
        print('COPY_RETENTION_STOP: preserve private files; inspect delivery receipt',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__': raise SystemExit(main())
