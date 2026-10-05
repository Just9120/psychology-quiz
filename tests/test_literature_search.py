from urllib.parse import parse_qs, urlsplit

from app.literature import literature_search, load_literature_items
from app.literature_chat import _item_view


def test_search_preserves_unicode_title_authors_and_encodes_query_without_private_refs():
    entry = {'title': 'Смысл & язык? #1', 'authors': ['И. Автор', 'A. Writer'],
             'source_refs': [{'source_id': 'PRIVATE_SOURCE_SHOULD_NOT_LEAK'}]}
    search = literature_search(entry)
    assert search['query'] == '"Смысл & язык? #1" И. Автор, A. Writer скачать'
    assert parse_qs(urlsplit(search['url']).query) == {'q': [search['query']]}
    assert 'PRIVATE' not in str(search)
    assert literature_search({'title': 'Без автора', 'authors': []})['query'] == '"Без автора" скачать'


def test_every_published_association_has_matching_query_and_telegram_escapes_it():
    items = load_literature_items()
    assert items
    for item in items:
        assert item['book_search'] == literature_search(item)
    item = {**items[0], 'title': '<Название>', 'authors': ['Автор & соавтор']}
    item['book_search'] = literature_search(item)
    text, keyboard = _item_view(item, None)
    assert '&lt;Название&gt;' in text and 'Автор &amp; соавтор' in text
    assert '<Название>' not in text
    assert any(button.url == item['book_search']['url'] for row in keyboard.inline_keyboard for button in row)
