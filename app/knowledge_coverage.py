"""Source-free preparation counts, separate from scientific source review."""
from collections import defaultdict
import json
import hashlib
from pathlib import Path

from app.curriculum import load_reviewed_catalog

ROOT = Path(__file__).resolve().parents[1]
PROJECTION_SHA256 = 'eeac873961d1a778721449c80660aeff972323ba471e56eeeaf48847a4ba08c6'


def project(manifest, curriculum, registry):
    """Only exact, unambiguous reviewed source titles acquire a lesson.

    Practice labels in the published notes explicitly include the discipline.
    Neither fuzzy matching nor section names establish a source binding.
    Counts describe this published package, never a personal Vault or the
    current scientific acceptability of an entire source.
    """
    sources = {source['id']: source for source in registry['sources']}
    labels = defaultdict(set)
    current = set()
    for key, topic in curriculum['topics'].items():
        source = sources.get(topic['source']['source_id'])
        if source is None:
            continue
        if all(source.get(field) == topic['source'][field]
               for field in ('modified_time', 'snapshot_sha256')):
            current.add(key)
        title = source['title']
        labels[title].add(key)
        discipline = curriculum['disciplines'][topic['discipline_id']]['title']
        labels[discipline + ' — ' + title].add(key)
    lessons = {key: set() for key in curriculum['topics']}
    disciplines = defaultdict(set)
    sections = defaultdict(int)
    unmapped = 0
    for index, note in enumerate(manifest['notes']):
        sections[note['section']] += 1
        matched = set()
        for label in note['sources']:
            candidates = labels.get(label, set())
            if len(candidates) == 1 and candidates <= current:
                matched.update(candidates)
        if not matched:
            unmapped += 1
        for key in matched:
            lessons[key].add(index)
            disciplines[curriculum['topics'][key]['discipline_id']].add(index)
    return {'state': 'PUBLISHED', 'atomic_notes': len(manifest['notes']),
            'unmapped_notes': unmapped,
            'sections': [{'title': key, 'notes': value} for key, value in sections.items()],
            'lessons': {key: len(value) for key, value in lessons.items()},
            'disciplines': {key: len(value) for key, value in disciplines.items()}}


def published_knowledge():
    # Runtime ships only counts: the note bodies and private inputs remain
    # excluded from Docker. A focused test reproduces this reviewed projection.
    try:
        payload = (ROOT / 'content/knowledge-coverage.json').read_bytes()
        if hashlib.sha256(payload).hexdigest() != PROJECTION_SHA256:
            raise ValueError('knowledge_projection_review_required')
        return json.loads(payload)
    except (OSError, ValueError, KeyError, TypeError):
        return {'state': 'UNSET', 'reason': 'knowledge_package_requires_review'}
