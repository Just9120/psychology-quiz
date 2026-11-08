from app import literature_chat
from app.literature import load_literature_items
from app.literature_navigation import reading_paths, reading_nodes, path_token, select_reading_scope


def test_actual_published_entries_all_remain_reachable_without_invented_topic_bindings():
    items = load_literature_items()
    records = reading_paths(items)
    assert {record['item']['id'] for record in records} == {item['id'] for item in items}
    for record in records:
        item = record['item']
        bindings = item.get('reading_topics') or []
        if bindings:
            assert record['path'][2] in {topic['id'] for topic in bindings}
        else:
            assert record['path'][2] == 'general:' + item['topic_id']
    root = literature_chat._course_navigation(items)
    assert 'Модуль 1' in root[0]
    assert all(literature_chat.CALLBACK_PATTERN.fullmatch(button.callback_data)
               for row in root[1].inline_keyboard for button in row)


def test_course_scope_uses_exact_module_association_and_keeps_general_reading_separate():
    first = {'id': 'one', 'topic_id': 'synthetic', 'topic_title': 'Общая дисциплина', 'module': 'module1',
             'reading_topics': [{'id': 't_first', 'title': 'Первая тема'}],
             'curriculum_topics': [{'id': 'old_lesson', 'title': 'Практика №2'}]}
    second = {**first, 'id': 'two', 'module': 'module3'}
    general = {**first, 'id': 'general', 'reading_topics': []}
    items = [first, second, general]
    key = path_token(('module1', 'synthetic', 't_first'))
    node, selected = select_reading_scope(items, key)
    assert node['labels'] == ('Модуль 1', 'Общая дисциплина', 'Первая тема')
    assert [item['id'] for item in selected] == ['one']
    assert [item['id'] for item in select_reading_scope(items, path_token(('module3', 'synthetic', 't_first')))[1]] == ['two']
    assert [item['id'] for item in select_reading_scope(items, path_token(('module1', 'synthetic', 'general:synthetic')))[1]] == ['general']
    assert select_reading_scope(items, path_token(('module2', 'synthetic', 't_first'))) is None
    assert 'Практика №2' not in literature_chat._course_navigation(items, path_token(('module1', 'synthetic')))[0]


def test_course_navigation_paging_and_full_titles_keep_every_leaf_available():
    items = [{'id': str(index), 'topic_id': 'synthetic', 'module': 'module1',
              'reading_topics': [{'id': f't_{index}', 'title': 'Полное длинное название темы для проверки навигации ' + str(index)}]}
             for index in range(12)]
    parent = path_token(('module1', 'synthetic'))
    nodes = reading_nodes(reading_paths(items))
    seen = set()
    for page in range(3):
        text, markup = literature_chat._course_navigation(items, parent, page)
        for row in markup.inline_keyboard:
            for button in row:
                assert literature_chat.CALLBACK_PATTERN.fullmatch(button.callback_data)
                assert len(button.callback_data.encode()) <= 64
                if button.callback_data.startswith('lit:c:'):
                    key = button.callback_data.split(':')[2]
                    assert nodes[key]['labels'][-1] in text
                    seen.add(key)
    assert seen == {key for key, node in nodes.items() if len(node['path']) == 3}
    assert literature_chat._course_navigation(items, parent, 3) is None
