import json
from copy import deepcopy
from pathlib import Path

import pytest

from app import glossary, glossary_service


def test_registry_discovers_new_contour_without_publishing_unreviewed_terms(tmp_path, monkeypatch):
    declared = [
        {'id': 'new_topic', 'title': 'Новая тема', 'status': 'active', 'available_contours': ['glossary']},
        {'id': 'not_glossary', 'title': 'Вопросы', 'status': 'active', 'available_contours': ['questions']},
        {'id': 'draft_topic', 'title': 'Черновик', 'status': 'draft', 'available_contours': ['glossary']},
    ]
    registry = tmp_path / 'topics.json'
    registry.write_text(json.dumps(declared, ensure_ascii=False), encoding='utf-8')
    topics = glossary._load_glossary_topics(registry)
    assert topics == (('new_topic', 'Новая тема'),)
    original = json.loads((glossary._GLOSSARY_DIR / 'cognitive_behavioral_therapy.json').read_text(encoding='utf-8'))[0]
    unreviewed = {**deepcopy(original), 'id': 'new_unreviewed', 'topic_id': 'new_topic'}
    (tmp_path / 'new_topic.json').write_text(json.dumps([unreviewed]), encoding='utf-8')
    monkeypatch.setattr(glossary, 'GLOSSARY_TOPICS', topics)
    monkeypatch.setattr(glossary, '_GLOSSARY_DIR', tmp_path)
    assert glossary.load_glossary_entries('new_topic') == []
    assert glossary.load_glossary_entries('draft_topic') is None


@pytest.mark.parametrize('document', [
    {}, [None],
    [{'id': '../outside', 'title': 'Unsafe', 'status': 'active', 'available_contours': ['glossary']}],
    [{'id': 'x', 'title': 'One', 'status': 'active', 'available_contours': ['glossary']}] * 2,
    [{'id': 'x', 'title': 'One', 'status': 'active', 'available_contours': 'glossary'}],
])
def test_invalid_registry_cannot_select_glossary_files(tmp_path, document):
    path = tmp_path / 'topics.json'
    path.write_text(json.dumps(document), encoding='utf-8')
    assert glossary._load_glossary_topics(path) == ()
    assert glossary._load_glossary_topics(tmp_path / 'missing.json') == ()


def test_legacy_callbacks_and_new_topic_callbacks_remain_stable_and_bounded():
    legacy = {
        'vvp': 'vvedenie_v_professiyu', 'op': 'obschaya_psihologiya',
        'fch': 'fiziologiya_cheloveka', 'vnd': 'fiziologiya_vnd',
        'psyf': 'psihofiziologiya', 'kmi': 'kachestvennye_metody_issledovaniya',
        'oep': 'osnovy_eksperimentalnoy_psihologii', 'pc': 'psychological_consulting',
    }
    for token, identity in legacy.items():
        assert glossary.callback_token_to_topic_id(token) == identity
        assert glossary.GLOSSARY_TOPIC_ID_TO_TOKEN[identity] == token
    assert glossary._glossary_topic_tokens(glossary.GLOSSARY_TOPICS) == glossary.GLOSSARY_TOPIC_CALLBACK_TOKENS
    payload = {row['topic_id']: row for row in glossary_service.topics()['topics']}
    for identity, count in [('cognitive_behavioral_therapy', 16), ('counseling_supervision', 10), ('social_psychology', 10)]:
        assert payload[identity]['available_count'] == count
        token = glossary.GLOSSARY_TOPIC_ID_TO_TOKEN[identity]
        assert glossary.callback_token_to_topic_id(token) == identity
        callbacks = [button.callback_data for row in glossary.build_glossary_count_keyboard(identity, count).inline_keyboard for button in row]
        callbacks += [f'glsq:replace:{"s" * 22}:{token}:all']
        assert all(len(value.encode('utf-8')) <= 64 for value in callbacks)
    assert glossary.callback_token_to_topic_id('unregistered') is None
