"""Source-free study paths derived from reviewed identities and current editions."""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from app import curriculum
from app.attempt_content import capture_questions
from app.db import get_active_categories
from app.literature import load_topic_registry


def discipline_modules(discipline_id: str | None, catalog=None) -> list[str]:
    catalog = catalog if catalog is not None else curriculum.load_catalog()
    record = catalog['disciplines'].get(discipline_id)
    if record is not None and 'modules' in record:
        return list(record['modules']) or ['other']
    record = load_topic_registry().get(discipline_id, {})
    return list(record.get('modules') or ([record['module']] if record.get('module') else ['unmapped']))


def question_scopes(conn) -> tuple[list[dict], dict[str, set[int]]]:
    """Only an exact captured fingerprint assigns a nested curriculum topic.

    Unclassified current editions remain reachable in an explicit leaf. No
    source fields or raw bank/attempt IDs are included in the public paths.
    """
    catalog = curriculum.load_catalog()
    registry = load_topic_registry()
    by_title = defaultdict(set)
    for key, item in [*catalog['disciplines'].items(), *registry.items()]:
        by_title[item['title']].add(key)
    categories = get_active_categories(conn)
    rows = conn.execute("""SELECT id,category_id FROM questions
        WHERE status='approved' ORDER BY id""").fetchall()
    editions = capture_questions(conn, [int(row[0]) for row in rows])
    scopes = defaultdict(set)
    counts = defaultdict(Counter)
    category_by_id = {int(row['id']): str(row['name']) for row in categories}
    for qid, cid in rows:
        encoded, sha = editions[int(qid)]
        content = json.loads(encoded)
        content.update(content_sha256=sha, snapshot_provenance='captured')
        classification = curriculum.classification(content)
        topic = classification['topic_id'] or f'unclassified:{cid}'
        scopes[topic].add(int(qid))
        counts[int(cid)][topic] += 1
    paths = []
    for cid, title in category_by_id.items():
        matches = by_title.get(title, set())
        discipline = next(iter(matches)) if len(matches) == 1 else None
        paths.append({'category_id': cid, 'discipline_id': discipline, 'title': title,
                      'modules': discipline_modules(discipline, catalog),
                      'topics': [{'id': topic, 'title': catalog['topics'][topic]['title']
                                  if topic in catalog['topics'] else 'Без уточнённой темы',
                                  'question_count': count}
                                 for topic, count in counts[cid].items()]})
    return paths, dict(scopes)
