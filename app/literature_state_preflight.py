"""Aggregate-only preview of legacy reading state before work-level migration."""
from collections import defaultdict


def summarize(rows, items):
    identities = {item['id']: item['work_id'] for item in items}
    groups = defaultdict(list)
    unknown = legacy = total = 0
    for row in rows:
        total += 1
        work = identities.get(row['literature_id'])
        if work is None:
            unknown += 1
            continue
        groups[(row['user_id'], work)].append(row['reading_status'])
        if row['progress_percent'] is not None:
            legacy += 1
    return {
        'ok': True,
        'reading_rows': total,
        'actor_work_pairs': len(groups),
        'multiple_associations': sum(len(statuses) > 1 for statuses in groups.values()),
        'conflicting_statuses': sum(len(set(statuses)) > 1 for statuses in groups.values()),
        'legacy_progress_rows': legacy,
        'unknown_association_rows': unknown,
    }


def inspect(conn, items):
    rows = conn.execute('SELECT user_id,literature_id,reading_status,progress_percent FROM user_literature_progress').fetchall()
    return summarize(rows, items)
