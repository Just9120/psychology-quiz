"""Reviewed reading associations as source-free module/discipline/topic paths."""
from __future__ import annotations

import hashlib
import json
import re
from app.literature import load_topic_registry


def module_key(value):
    if not isinstance(value, str):
        return 'unmapped'
    match = re.fullmatch(r'(?:module|Модуль\s+)([1-9][0-9]*)', value or '')
    return 'module' + match[1] if match else 'other' if value in {'other', 'Другое'} else 'unmapped'


def module_label(value):
    return 'Модуль ' + value[6:] if re.fullmatch(r'module[1-9][0-9]*', value) else (
        'Дополнительные материалы' if value == 'other' else 'Без модуля')


def path_token(path):
    return hashlib.sha256(('study:' + json.dumps(path, ensure_ascii=False, separators=(',', ':'))).encode()).hexdigest()[:12]


def node_order(node):
    module = node['path'][0]
    return (0, int(module[6:]), node['labels'][1:]) if re.fullmatch(r'module[1-9][0-9]*', module) else (1, 0, node['labels'])


def reading_paths(items):
    registry = load_topic_registry()
    records = []
    for item in items:
        identity = item['topic_id']
        discipline = registry.get(identity, {})
        title = discipline.get('title') or item.get('topic_title') or 'Другие материалы'
        modules = ([module_key(item['module'])] if item.get('module') else
                   discipline.get('modules', [module_key(discipline.get('module'))])) or ['other']
        topics = item.get('curriculum_topics') or [{'id': 'general:' + identity, 'title': 'Общее чтение дисциплины'}]
        for module in modules:
            for topic in topics:
                records.append({'path': (module, identity, topic['id']),
                                'labels': (module_label(module), title, topic['title']), 'item': item})
    return records


def reading_nodes(records):
    nodes = {}
    for record in records:
        for depth in (1, 2, 3):
            path, labels = record['path'][:depth], record['labels'][:depth]
            token = path_token(path)
            if token in nodes and nodes[token]['path'] != path:
                raise ValueError('reading_navigation_collision')
            nodes[token] = {'path': path, 'labels': labels}
    return nodes


def select_reading_scope(items, token):
    records = reading_paths(items)
    node = reading_nodes(records).get(token)
    if node is None or len(node['path']) != 3:
        return None
    selected = list({record['item']['id']: record['item'] for record in records if record['path'] == node['path']}.values())
    return node, selected
