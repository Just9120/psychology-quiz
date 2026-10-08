from copy import deepcopy
from urllib.parse import urlsplit

import pytest

from app.literature import load_literature_items, list_reading_topic_payloads, _valid_offer_target
from app.literature_topics import load_reading_topics
from app.literature_reading import reading_order
from app import literature_chat


def test_entire_public_catalog_has_standalone_topics_without_changing_identity():
    items = load_literature_items()
    topics, mapping = load_reading_topics()
    assert len({item['work_id'] for item in items}) == 281
    assert set(mapping) == {item['work_id'] for item in items}
    assert not any(word in topic['title'].lower() for topic in topics
                   for word in ('лекция', 'практика', 'урок', 'модуль', 'бонус'))
    for topic in list_reading_topic_payloads():
        expected = {item['work_id'] for item in items
                    if any(link['id'] == topic['topic_id'] for link in item['reading_topics'])}
        assert topic['item_count'] == len(expected)
    # The pedagogical source-list placement is not the reading classification.
    parenting = next(item for item in items if item['id'] == 'lit_gordon_effective_parent_training')
    assert parenting['topic_id'] == 'fiziologiya_vnd'
    assert parenting['reading_topics'] == [{'id': 'reading_family', 'title': 'Семья, отношения и воспитание'}]
    fiction = next(item for item in items if item['id'] == 'lit_bulgakov_heart_of_a_dog')
    assert fiction['reading_topics'][0]['id'] == 'reading_fiction'


def test_route_respects_work_dependencies_before_levels_deduplicates_and_rejects_unknown_cycles():
    base = {'reading_level': 'core', 'importance': 'basic', 'importance_source': 'agent',
            'why_read': 'Confirmed purpose', 'prerequisites': []}
    foundation = {**base, 'id': 'z', 'work_id': 'foundation', 'reading_level': 'advanced'}
    alias = {**foundation, 'id': 'alias'}
    dependent = {**base, 'id': 'a', 'work_id': 'dependent', 'prerequisites': ['alias']}
    missing = {**base, 'id': 'missing', 'prerequisites': ['unknown']}
    first = {**base, 'id': 'cycle1', 'prerequisites': ['cycle2']}
    second = {**base, 'id': 'cycle2', 'prerequisites': ['cycle1']}
    items = [dependent, foundation, alias, missing, first, second]
    before = deepcopy(items)
    order = reading_order(items)
    assert [row['item']['id'] for row in order] == ['z', 'a']
    assert order[1]['prerequisites'] == [alias]
    assert items == before
    assert reading_order([dependent], items)[0]['prerequisites'] == [alias]


def test_real_route_and_telegram_pages_are_bounded_and_link_to_real_items():
    items = load_literature_items()
    known = {item['id']: item for item in items}
    for topic in list_reading_topic_payloads():
        scoped = [item for item in items if any(link['id'] == topic['topic_id'] for link in item['reading_topics'])]
        order = reading_order(scoped, items)
        keys = [row['item']['work_id'] for row in order]
        assert len(keys) == len(set(keys))
        for pos, row in enumerate(order):
            for required in row['prerequisites']:
                assert required['id'] in known
                if required['work_id'] in keys:
                    assert keys.index(required['work_id']) < pos
        for page in range(max(1, (len(order) + literature_chat.PAGE_SIZE - 1) // literature_chat.PAGE_SIZE)):
            text, keyboard = literature_chat._reading_view(items, literature_chat._token(topic['topic_id']), page)
            assert len(text) <= 4096
            assert 'Рекомендация агента' in text
            for button in (button for row in keyboard.inline_keyboard for button in row):
                assert literature_chat.CALLBACK_PATTERN.fullmatch(button.callback_data)
                assert len(button.callback_data.encode()) <= 64


@pytest.mark.parametrize('provider,fmt,url,valid', [
    ('MyBook', 'text', 'https://mybook.ru/author/exact-author/exact-book/', True),
    ('MyBook', 'audio', 'https://mybook.ru/author/exact-author/exact-audio/', True),
    ('MyBook', 'text', 'https://mybook.ru/author/exact-author/exact-book/read/', False),
    ('MyBook', 'text', 'https://mybook.ru.evil.test/author/a/b/', False),
    ('MyBook', 'text', 'https://mybook.ru/author/a/b/?redirect=evil', False),
    ('Яндекс Книги', 'text', 'https://books.yandex.ru/books/JIUJ6mpq', True),
    ('Яндекс Книги', 'audio', 'https://books.yandex.ru/audiobooks/dyglJKi1', True),
    ('Яндекс Книги', 'text', 'https://books.yandex.ru/books/abc/read-online', False),
    ('Яндекс Книги', 'audio', 'https://books.yandex.ru/books/abc', False),
    ('Яндекс Книги', 'text', 'https://user:secret@books.yandex.ru/books/abc', False),
    ('Яндекс Книги', 'text', 'https://books.yandex.ru/books/abc#fragment', False),
    ('Яндекс Книги', 'text', 'http://books.yandex.ru/books/abc', False),
])
def test_provider_cards_are_finite_https_targets(provider, fmt, url, valid):
    assert _valid_offer_target(provider, fmt, urlsplit(url)) is valid
