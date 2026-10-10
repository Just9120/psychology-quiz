"""Reproducible Obsidian knowledge graph from the published, reviewed bank.

No Drive fetch, private dossier export, runtime data or generated assertions.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.content_publication import fingerprint, load_policy
from app.curriculum import load_catalog
from app.homework import load_catalog as load_homework
from app.literature import load_literature_items, literature_access_label
from app.literature_reading import reading_order
from app.literature_topics import load_reading_topics
from scripts.audit_public_assets import audit_assets, known_source_ids
from scripts.obsidian_vault import VaultError, write_vault
from scripts.owner_source_summary import published_glossary, published_questions

RETIRED_NOTE = ('# Заметка предыдущего пакета\n\n'
                'Эта редакция больше не входит в опубликованный банк. '
                'Прежнее имя сохранено для ссылок; учебное содержимое не переопубликовано.\n\n'
                '[[index|К текущей базе]]\n').encode('utf-8')
# Exact source-reviewed notes from the saved private manifest. Editing this
# digest requires a renewed source review; status alone grants no publication.
REVIEWED_NOTES_SHA256 = '6e42340ec5d0bd5ea418c0731818e42c9d038b45bc754d0ff769cd6595941187'


def prepared_notes():
    payload = (ROOT / 'content/vault-notes.json').read_bytes()
    if hashlib.sha256(payload).hexdigest() != REVIEWED_NOTES_SHA256:
        raise VaultError('prepared_note_source_review_required')
    return json.loads(payload)['notes']

def note_id(kind: str, identity: str) -> str:
    return kind + '-' + hashlib.sha256(identity.encode()).hexdigest()[:20]


def text(value: str) -> str:
    # Source text cannot introduce new wikilinks or change a generated alias.
    return value.replace('[', r'\[').replace(']', r'\]').replace('|', r'\|')


def link(kind: str, identity: str, title: str) -> str:
    return f"[[{note_id(kind, identity)}|{text(title)}]]"


def render_published() -> tuple[dict[str, bytes], dict[str, int]]:
    questions = published_questions()
    terms = published_glossary(load_policy())
    books = load_literature_items()
    curriculum = load_catalog()
    homework = load_homework()
    files: dict[str, bytes] = {}
    question_topics = defaultdict(list)
    discipline_questions = defaultdict(list)
    discipline_terms = defaultdict(list)
    editions = {value['item_sha256']: value for value in curriculum['editions'].values()}
    question_ids = {item['id'] for item in questions}
    discipline_titles = {v['title']: k for k, v in curriculum['disciplines'].items()}
    term_ids = {item['id'] for item in terms}
    prepared = prepared_notes()
    prepared_ids = {item['id']: item['title'] for item in prepared}
    unmapped = []

    def add(kind, identity, title, body):
        name = note_id(kind, identity) + '.md'
        if name in files:
            raise VaultError('duplicate_public_note')
        files[name] = ('\n'.join([f'# {text(title)}', '', *body, '', '---',
                                '[[index|К оглавлению]]', '']) ).encode('utf-8')

    for item in prepared:
        def resolve_prepared(match):
            identity, _, alias = match.group(1).partition('|')
            if identity not in prepared_ids:
                raise VaultError('prepared_note_link_missing')
            return link('note', identity, alias or prepared_ids[identity])
        body = [re.sub(r'\[\[([^\]]+)\]\]', resolve_prepared, item['body']), '',
                link('discipline', item['discipline_id'], curriculum['disciplines'][item['discipline_id']]['title'])]
        for field, kind, items, label in (('question_ids', 'question', questions, 'Вопросы'),
                                        ('term_ids', 'term', terms, 'Понятия'),
                                        ('literature_ids', 'book', books, 'Литература')):
            known = {v['id']: v for v in items}
            if any(value not in known for value in item[field]):
                raise VaultError('prepared_note_published_link_missing')
            if item[field]:
                body += ['', '## ' + label, '']
                for key in item[field]:
                    entry = known[key]
                    title = entry.get('term', entry.get('question', entry.get('title')))
                    body += ['- ' + link(kind, entry.get('work_id', key), title)]
        add('note', item['id'], item['title'], body)

    for item in questions:
        edition = editions.get(fingerprint(item))
        topic = curriculum['topics'].get(edition['topic_id']) if edition else None
        discipline = discipline_titles.get(item['category'])
        if topic and topic['discipline_id'] != discipline:
            raise VaultError('public_question_topic_mismatch')
        body = []
        if topic:
            question_topics[edition['topic_id']].append(item)
            body += [link('topic', edition['topic_id'], topic['title']), '']
        else:
            unmapped.append(item)
            body += ['Точная тема не установлена; предметная область: ' + text(item['category']) + '.', '']
        if discipline:
            discipline_questions[discipline].append(item)
        case = item.get('case')
        if item.get('kind') == 'case':
            body += ['## Ситуация', '', text(case['situation']), '',
                     'Подход: ' + text(case['approach']), '', '### Условия', '']
            body += ['- ' + text(value) for value in case['conditions']]
        body += ['', '## Вопрос', '', text(item['question']), '', '## Варианты', '']
        body += [f'{i}. {text(value)}' for i, value in enumerate(item['options'], 1)]
        body += ['', '## Ответ и пояснение', '',
                 text(item['options'][item['correct_option_index']]), '', text(item['explanation'])]
        if item.get('kind') == 'case':
            body += ['', '### Почему другие варианты не подходят', '']
            body += [f'{i}. {text(value)}' for i, value in enumerate(case['option_rationales'], 1)]
            body += ['', '### Границы вывода', '', text(case['ambiguity'])]
        add('question', item['id'], item['question'], body)

    for item in terms:
        discipline_terms[item['topic_id']].append(item)
        body = [text(item['definition']), '', '## Примеры', '']
        body += ['- ' + text(value) for value in item['examples']]
        if item['aliases']:
            body += ['', 'Другие названия: ' + ', '.join(text(v) for v in item['aliases']) + '.']
        related = item['confusable_with']
        if related:
            body += ['', '## Сопоставить понятия', '']
            body += ['- ' + link('term', value, next(t['term'] for t in terms if t['id'] == value))
                     for value in related if value in term_ids]
            body += ['- В опубликованном банке нет самостоятельного определения: `' + value + '`.'
                     for value in related if value not in term_ids]
        if item['topic_id'] in curriculum['disciplines']:
            body += ['', link('discipline', item['topic_id'], curriculum['disciplines'][item['topic_id']]['title'])]
        add('term', item['id'], item['term'], body)

    for identity, topic in sorted(curriculum['topics'].items()):
        items = question_topics[identity]
        body = [link('discipline', topic['discipline_id'], curriculum['disciplines'][topic['discipline_id']]['title']), '',
                '## Разборы', '', 'Ответы и пояснения находятся в самостоятельных заметках ниже.' if items
                else 'В текущем опубликованном банке нет вопросов с подтверждённой связью с этой темой.', '']
        body += ['- ' + link('question', q['id'], q['question']) for q in items]
        add('topic', identity, topic['title'], body)

    for identity, discipline in sorted(curriculum['disciplines'].items()):
        body = ['## Темы', '']
        body += ['- ' + link('topic', key, value['title']) for key, value in curriculum['topics'].items()
                 if value['discipline_id'] == identity]
        body += ['', '## Понятия', '']
        body += ['- ' + link('note', item['id'], item['title']) for item in prepared if item['discipline_id'] == identity]
        body += ['- ' + link('term', t['id'], t['term']) for t in discipline_terms[identity]]
        body += ['', '## Все разборы предметной области', '']
        body += ['- ' + link('question', q['id'], q['question']) for q in discipline_questions[identity]]
        add('discipline', identity, discipline['title'], body)

    work_groups = defaultdict(list)
    for item in books:
        work_groups[item['work_id']].append(item)
    by_entry = {item['id']: item for item in books}
    for identity, entries in sorted(work_groups.items()):
        item = entries[0]
        body = [', '.join(text(a) for a in item['authors']), '',
                'Год: ' + (str(item['year']) if item['year'] else 'не установлен'), '',
                'Это библиографическая карточка, а не конспект прочитанной книги.', '', '## Темы чтения', '']
        body += ['- ' + link('reading', t['id'], t['title']) for t in item['reading_topics']]
        body += ['', '## Рекомендация по чтению', '', text(item['why_read'])]
        prerequisites = {ref for entry in entries for ref in entry['prerequisites']}
        if prerequisites:
            body += ['', 'Предварительное чтение:', '']
            body += ['- ' + link('book', by_entry[ref]['work_id'], by_entry[ref]['title']) for ref in sorted(prerequisites)]
        body += ['', '## Текст и аудио', '']
        for offer in item['access_links']:
            fmt = 'Аудиокнига' if offer['format'] == 'audio' else 'Текст'
            body += [f"- [{fmt} · {offer['provider']}]({offer['url']}) — {literature_access_label(offer)}. Проверено {offer['checked_at']}."]
        if not item['access_links']:
            body += ['Подтверждённых прямых ссылок нет; это не означает отсутствия книги в сервисах.']
        body += ['', 'Доступ к полной версии зависит от условий сервиса и конкретного издания.', '',
                 'Поисковый запрос: ' + text(item['book_search']['query'])]
        if item['metadata_warnings']:
            body += ['', '## Неуточнённые сведения', '']
            body += ['- ' + text(value) for value in item['metadata_warnings']]
        add('book', identity, item['title'], body)

    reading_topics, _ = load_reading_topics()
    for topic in reading_topics:
        selected = [item for item in books if topic['id'] in {t['id'] for t in item['reading_topics']}]
        route = reading_order(selected, books)
        routed = {entry['item']['work_id'] for entry in route}
        body = ['Рекомендация по проверенным метаданным; книги одного этапа без зависимостей можно выбирать по интересу.', '',
                '## Последовательность чтения', '']
        body += [f"{i}. {link('book', entry['item']['work_id'], entry['item']['title'])} — {entry['stage']}."
                 for i, entry in enumerate(route, 1)]
        others = {item['work_id']: item for item in selected if item['work_id'] not in routed}
        if others:
            body += ['', '## Без установленной последовательности', '']
            body += ['- ' + link('book', key, item['title']) for key, item in sorted(others.items())]
        add('reading', topic['id'], topic['title'], body)

    for item in homework:
        if not set(item['question_ids']) <= question_ids:
            raise VaultError('public_homework_question_missing')
        body = [text(item['description']), '',
                'Тест проверяет знания; он не подтверждает выполнение исходного эссе, наблюдения или упражнения.', '',
                'В приложении зачёт требует не менее80% в одной завершённой попытке. Здесь сохраняются только учебные разборы, без личного прогресса.', '',
                '## Вопросы для самопроверки', '']
        body += ['- ' + link('question', key, next(q['question'] for q in questions if q['id'] == key)) for key in item['question_ids']]
        add('homework', item['id'], item['title'], body)

    counts = {'questions': len(questions), 'terms': len(terms), 'works': len(work_groups),
              'prepared_notes': len(prepared),
              'literature_associations': len(books), 'topics': len(curriculum['topics']),
              'topics_with_questions': sum(bool(v) for v in question_topics.values()),
              'unmapped_questions': len(unmapped), 'homework': len(homework),
              'missing_comparison_terms': len({v for t in terms for v in t['confusable_with'] if v not in term_ids}),
              'audio_works': sum(any(o['format'] == 'audio' for o in entries[0]['access_links']) for entries in work_groups.values())}
    index = ['# PsychologyAtlas — база знаний', '',
             'Самостоятельные понятия, учебные разборы и библиография из проверенного опубликованного банка.', '',
             '## Границы и полнота', '',
             f"Вопросы: {counts['questions']}; понятия: {counts['terms']}; произведения: {counts['works']} ({counts['literature_associations']} связей каталога); домашние задания: {counts['homework']}.", '',
             f"Темы: {counts['topics']}; с привязанными вопросами: {counts['topics_with_questions']}; вопросов без точной темы: {counts['unmapped_questions']}.", '',
             f"У {counts['missing_comparison_terms']} упомянутых понятий нет самостоятельного определения в опубликованном глоссарии; это отмечено в заметках без выдуманных ссылок.", '',
             f"Прямые аудиоссылки подтверждены для {counts['audio_works']} произведений. У остальных аудио не подтверждено.", '',
             'Это покрытие текущего банка, не пересказ всех425 исходных материалов. Приватные исходники, досье и личный прогресс сюда не входят. Содержание книг не считается изученным по библиографии.', '',
             '## Предметные области', '']
    index += ['- ' + link('discipline', key, value['title']) for key, value in curriculum['disciplines'].items()]
    index += ['', '## Самостоятельные заметки по материалам', '']
    index += ['- ' + link('note', item['id'], item['title']) for item in prepared]
    index += ['', '## Литература по темам', '']
    index += ['- ' + link('reading', t['id'], t['title']) for t in reading_topics]
    index += ['', '## Домашние задания', '']
    index += ['- ' + link('homework', item['id'], item['title']) for item in homework]
    index += ['', '## Разборы без точной темы', '']
    index += ['- ' + link('question', item['id'], item['question']) for item in unmapped]
    files['index.md'] = ('\n'.join(index) + '\n').encode('utf-8')
    validate_links(files)
    return files, counts


def validate_links(files: dict[str, bytes]) -> None:
    targets = {name[:-3] for name in files}
    for content in files.values():
        for target in re.findall(r'\[\[([^\]|]+)(?:\|[^\]]*)?\]\]', content.decode('utf-8')):
            if target not in targets:
                raise VaultError('public_vault_link_missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', type=Path, default=ROOT / 'vault')
    parser.add_argument('--repository-vault', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    files, counts = render_published()
    if args.check:
        generated = args.vault / 'generated'
        if any((generated / name).read_bytes() != content for name, content in files.items()):
            raise VaultError('public_vault_outdated')
        if any(path.read_bytes() != RETIRED_NOTE for path in generated.glob('*.md') if path.name not in files):
            raise VaultError('public_vault_unreviewed_note')
        validate_links({p.name: p.read_bytes() for p in generated.glob('*.md')})
    else:
        write_vault(args.vault, files, repository_vault=args.repository_vault, published_content=True)
    audit_assets([args.vault / 'generated'], known_source_ids())
    print('PUBLIC_VAULT_OK', counts)


if __name__ == '__main__':
    main()
