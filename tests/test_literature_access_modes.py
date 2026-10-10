import copy
import pytest
from app import literature
from app.literature_chat import _item_view


def test_offer_review_validates_known_modes_and_retains_unverified_legacy(monkeypatch):
    base = {'format': 'text', 'provider': 'Литрес', 'url': 'https://www.litres.ru/book/author/book-1/', 'access': 'provider_terms', 'checked_at': '2026-10-03'}
    raw = {'schema_version': 1, 'works': {'work': [base]}}
    monkeypatch.setattr(literature, '_load_json_file', lambda path: raw)
    try:
        literature.load_access_links.cache_clear()
        assert literature.literature_access_label(literature.load_access_links()['work'][0]) == 'Условия доступа не подтверждены'
        for modes in [['free'], ['subscription'], ['purchase'], ['purchase', 'subscription'], []]:
            offer = {**base, 'access_modes': modes, 'access_review': 'Reviewed this exact format offer block'}
            raw['works']['work'] = [offer]; literature.load_access_links.cache_clear()
            assert literature.load_access_links()['work'] == [offer]
        invalid = [
            {**base, 'access_modes': ['free']},
            {**base, 'access_review': 'No modes'},
            {**base, 'access_modes': ['free'], 'access_review': ''},
            {**base, 'access_modes': ['owned'], 'access_review': 'Unproven entitlement'},
            {**base, 'access_modes': ['free', 'free'], 'access_review': 'Duplicate'},
        ]
        for offer in invalid:
            raw['works']['work'] = [offer]; literature.load_access_links.cache_clear()
            with pytest.raises(ValueError):literature.load_access_links()
    finally:literature.load_access_links.cache_clear()


def test_telegram_displays_distinct_text_audio_conditions_without_changing_personal_state():
    item=copy.deepcopy(literature.load_literature_items()[0])
    base={'provider':'Литрес','checked_at':'2026-10-03','access':'provider_terms'}
    item['access_links']=[{**base,'format':'text','url':'https://www.litres.ru/book/exact/','access_modes':['purchase','subscription']}, {**base,'format':'audio','url':'https://www.litres.ru/audiobook/exact/','access_modes':[]}]
    state={'reading_status':'read'};before=copy.deepcopy(state)
    text,_=_item_view(item,state)
    assert 'Текст · Литрес: Отдельная покупка · По подписке' in text
    assert 'Аудио · Литрес: Условия доступа не подтверждены' in text
    assert state==before


def test_yandex_virtual_reader_is_reviewed_audio_and_cannot_be_mislabeled(monkeypatch):
    offer = {'format': 'audio', 'narration': 'synthetic', 'provider': 'Яндекс Книги',
             'url': 'https://books.yandex.ru/audio/Ab12Cd34', 'access': 'provider_terms',
             'checked_at': '2026-10-11', 'access_modes': [],
             'access_review': 'Exact book card offers a Virtual Reader; full-access terms unknown.'}
    raw = {'schema_version': 1, 'works': {'work': [offer]}}
    monkeypatch.setattr(literature, '_load_json_file', lambda path: raw)
    try:
        literature.load_access_links.cache_clear()
        checked = literature.load_access_links()['work'][0]
        item = {'id': 'book', 'topic_id': 'topic', 'title': 'Книга', 'authors': [],
                'access_links': [checked]}
        state = {'reading_status': 'read'}
        text, keyboard = _item_view(item, state)
        assert 'Автоозвучка · Яндекс Книги: Условия доступа не подтверждены' in text
        button = next(button for row in keyboard.inline_keyboard for button in row if button.url)
        assert button.text == 'Автоозвучка · Яндекс Книги'
        assert button.url == offer['url'] and state == {'reading_status': 'read'}
        invalid = [{key: value for key, value in offer.items() if key != 'narration'},
                   {**offer, 'narration': 'human'}, {**offer, 'format': 'text'},
                   {**offer, 'url': offer['url'] + '/quotes'},
                   {**offer, 'url': offer['url'] + '?token=secret'},
                   {**offer, 'url': 'https://books.yandex.ru.example.org/audio/Ab12Cd34'}]
        for value in invalid:
            raw['works']['work'] = [value]; literature.load_access_links.cache_clear()
            with pytest.raises(ValueError):
                literature.load_access_links()
    finally:
        literature.load_access_links.cache_clear()
