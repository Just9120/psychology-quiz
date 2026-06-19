#!/usr/bin/env python3
"""Operator tool to abandon in-progress quiz sessions before content replacement."""
from __future__ import annotations
import argparse, sqlite3
from pathlib import Path

def _ids(conn):
    return [int(r[0]) for r in conn.execute("SELECT id FROM quiz_sessions WHERE status = 'in_progress' ORDER BY id")]

def run(db_path: str, apply: bool=False) -> dict:
    conn=sqlite3.connect(Path(db_path))
    try:
        conn.isolation_level=None
        conn.execute('BEGIN')
        before=_ids(conn)
        if apply and before:
            conn.execute("UPDATE quiz_sessions SET status='abandoned', finished_at=CURRENT_TIMESTAMP WHERE status='in_progress'")
        after=_ids(conn)
        if apply: conn.execute('COMMIT')
        else: conn.execute('ROLLBACK')
        return {'mode':'apply' if apply else 'dry-run','before_count':len(before),'before_session_ids':before,'after_count':len(after),'after_session_ids':after,'abandoned_count':len(before)-len(after) if apply else 0}
    except Exception:
        conn.execute('ROLLBACK'); raise
    finally:
        conn.close()

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--db-path',required=True); p.add_argument('--apply',action='store_true')
    a=p.parse_args(); r=run(a.db_path,a.apply)
    print(f"Mode: {r['mode']}"); print(f"Before in-progress sessions: {r['before_count']} {r['before_session_ids']}")
    print(f"After in-progress sessions: {r['after_count']} {r['after_session_ids']}"); print(f"Marked abandoned: {r['abandoned_count']}")
    if not a.apply: print('Dry run only; rerun with --apply to mutate.')
if __name__=='__main__': main()
