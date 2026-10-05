import copy
import json

import pytest

from app import homework
from app.curriculum import load_catalog as load_curriculum
from app.literature import load_topic_registry


def test_published_homework_and_literature_share_reviewed_discipline_names_and_modules():
    catalog = load_curriculum()
    for topic in load_topic_registry().values():
        if 'literature' not in topic.get('available_contours', []):
            continue
        discipline = catalog['disciplines'][topic['id']]
        assert topic['title'] == discipline['title']
        assert topic.get('modules', [topic['module']]) == (discipline['modules'] or ['other'])
    for assignment in homework.load_catalog():
        topic = catalog['topics'][assignment['topic_id']]
        assert topic['discipline_id'] == assignment['discipline_id']
        assert assignment['module'] in [value.replace('module', 'Модуль ')
                                       for value in catalog['disciplines'][assignment['discipline_id']]['modules']]


def test_homework_rejects_wrong_module_before_serving_shared_client_catalog(tmp_path, monkeypatch):
    original = json.loads(homework.CATALOG_PATH.read_text(encoding='utf-8'))
    path = tmp_path / 'homework.json'
    changed = copy.deepcopy(original)
    changed['assignments'][0]['module'] = 'Модуль 6'
    path.write_text(json.dumps(changed, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(homework, 'CATALOG_PATH', path)
    homework.load_catalog.cache_clear()
    try:
        with pytest.raises(ValueError, match='module does not match curriculum'):
            homework.load_catalog()
        path.write_text(json.dumps(original, ensure_ascii=False), encoding='utf-8')
        assert len(homework.load_catalog()) == len(original['assignments'])
    finally:
        homework.load_catalog.cache_clear()


def test_cross_module_assignment_can_use_either_verified_module_without_inventing_one(tmp_path, monkeypatch):
    original = json.loads(homework.CATALOG_PATH.read_text(encoding='utf-8'))
    catalog = copy.deepcopy(load_curriculum())
    first = original['assignments'][0]
    catalog['disciplines'][first['discipline_id']].update(module=None, modules=['module1', 'module3'])
    monkeypatch.setattr(homework, 'load_curriculum', lambda: catalog)
    path = tmp_path / 'homework.json'
    monkeypatch.setattr(homework, 'CATALOG_PATH', path)
    try:
        for module in ('Модуль 1', 'Модуль 3'):
            first['module'] = module
            path.write_text(json.dumps(original, ensure_ascii=False), encoding='utf-8')
            homework.load_catalog.cache_clear()
            assert homework.load_catalog()[0]['module'] == module
        first['module'] = 'Модуль 2'
        path.write_text(json.dumps(original, ensure_ascii=False), encoding='utf-8')
        homework.load_catalog.cache_clear()
        with pytest.raises(ValueError, match='module does not match curriculum'):
            homework.load_catalog()
    finally:
        homework.load_catalog.cache_clear()
