"""Render reviewed source knowledge; historical command name retained.

No question, homework or literature loader participates in this projection.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.audit_public_assets import audit_assets, known_source_ids
from scripts.obsidian_vault import VaultError, valid_generated_name, write_vault

ENTRY = 'База знаний.md'
LEGACY_STATE_SHA256 = '7bf9cb0ddcb88c0874624f4ca58e30734e22bbbcc6e2b3c87cc0d30fe5fcd886'
REVIEWED_NOTES_SHA256 = 'fccd7208d77fb75d09823b0d4aec6f18612471aae8682a01a3f6bd9fda47abaf'
RETIRED_NOTE = ('# Заметка предыдущей редакции\n\n'
                'Эта заметка больше не входит в проверенный пакет. '
                'Содержимое не переопубликовано; имя сохранено для личных ссылок.\n\n'
                '[[База знаний]]\n').encode('utf-8')


def prepared_notes():
    payload = (ROOT / 'content/vault-notes.json').read_bytes()
    if hashlib.sha256(payload).hexdigest() != REVIEWED_NOTES_SHA256:
        raise VaultError('prepared_note_source_review_required')
    manifest = json.loads(payload)
    if set(manifest) != {'schema_version', 'notes', 'coverage'} or manifest['schema_version'] != 2:
        raise VaultError('invalid_knowledge_manifest')
    if (not isinstance(manifest['notes'], list) or not manifest['notes']
            or not isinstance(manifest['coverage'], dict)
            or set(manifest['coverage']) != {'summaries', 'statement'}
            or not isinstance(manifest['coverage']['summaries'], dict)
            or not isinstance(manifest['coverage']['statement'], str)
            or len(manifest['coverage']['statement'].strip()) < 80):
        raise VaultError('knowledge_coverage_required')
    return manifest


def render_published() -> tuple[dict[str, bytes], dict[str, int]]:
    manifest = prepared_notes()
    files, sections = {}, {}
    for item in manifest['notes']:
        if not isinstance(item, dict) or set(item) != {'title', 'section', 'body', 'links', 'sources'}:
            raise VaultError('knowledge_fields_required')
        title, section, body = item['title'], item['section'], item['body']
        if (not isinstance(title, str) or not valid_generated_name(title + '.md')
                or not re.search(r'[А-Яа-яЁё]', title)
                or title in {'База знаний', 'Границы базы'} or not isinstance(section, str)
                or not valid_generated_name(section + '.md') or not isinstance(body, str)
                or len(body.strip()) < 80 or not isinstance(item['links'], dict) or not item['links']
                or not isinstance(item['sources'], list) or not item['sources']):
            raise VaultError('invalid_knowledge_note')
        if re.search(r'(?im)^\s*(?:##?\s*)?(?:вопрос|варианты|ответ и пояснение)\s*$', body):
            raise VaultError('quiz_dump_forbidden')
        if any(not isinstance(k, str) or k == title or not valid_generated_name(k + '.md')
               or not isinstance(v, str) or not v.strip() or '\n' in v or '\r' in v
               for k, v in item['links'].items()):
            raise VaultError('semantic_relation_required')
        lines = [f'# {title}', '', body.strip(), '', '## Связи', '']
        lines += [f'- [[{target}]] — {relation}' for target, relation in item['links'].items()]
        if any(not isinstance(v, str) or not v.strip() or '\n' in v or '\r' in v
               for v in item['sources']):
            raise VaultError('source_title_required')
        lines += ['', '## Основание', ''] + ['- ' + value for value in item['sources']]
        name = title + '.md'
        if name.casefold() in {v.casefold() for v in files}:
            raise VaultError('duplicate_knowledge_title')
        files[name] = ('\n'.join(line.rstrip() for line in lines) + '\n').encode('utf-8')
        sections.setdefault(section, []).append(title)
    if set(manifest['coverage']['summaries']) != set(sections):
        raise VaultError('section_coverage_mismatch')
    for section, titles in sections.items():
        name = section + '.md'
        if name.casefold() in {v.casefold() for v in files}:
            raise VaultError('section_note_title_collision')
        overview = manifest['coverage']['summaries'].get(section)
        if not isinstance(overview, str) or len(overview.strip()) < 80:
            raise VaultError('section_summary_required')
        lines = [f'# {section}', '', overview.strip(), '', '## Понятия и связи', '']
        lines += [f'- [[{title}]]' for title in sorted(titles)]
        lines += ['', '[[База знаний]]', '']
        files[name] = '\n'.join(lines).encode('utf-8')
    lines = ['# База знаний', '',
             'Самостоятельные заметки по понятиям, механизмам и моделям. '
             'Смысловые связи объясняют отношения между знаниями. '
             'Тематические обзоры помогают выбрать точку входа.', '', '## Темы', '']
    lines += [f'- [[{section}]]' for section in sorted(sections)]
    lines += ['', '[[Границы базы]] описывает покрытие источников и ограничения.', '']
    files[ENTRY] = '\n'.join(lines).encode('utf-8')
    files['Границы базы.md'] = ('# Границы базы\n\n' + manifest['coverage']['statement'].strip()
                                + '\n\n[[База знаний]]\n').encode('utf-8')
    validate_links(files)
    return files, {'atomic_notes': len(manifest['notes']), 'summaries': len(sections),
                   'markdown_files': len(files)}


def validate_links(files):
    targets = {name.removesuffix('.md') for name in files}
    if len({name.casefold() for name in files}) != len(files):
        raise VaultError('duplicate_knowledge_title')
    for name, content in files.items():
        if not valid_generated_name(name):
            raise VaultError('invalid_generated_name')
        for target in re.findall(r'\[\[([^\]|]+)(?:\|[^\]]*)?\]\]', content.decode('utf-8')):
            if target not in targets:
                raise VaultError('public_vault_link_missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', type=Path, default=ROOT / 'vault')
    parser.add_argument('--repository-vault', action='store_true')
    parser.add_argument('--replace-catalogue', action='store_true',
                        help='Replace only the unchanged fingerprinted PR347 catalogue')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    files, counts = render_published()
    if args.check:
        generated = args.vault / 'generated'
        if generated.is_symlink() or any(p.is_symlink() or not p.is_file()
                or (p.name != '.psychology-atlas-generated.json'
                    and not valid_generated_name(p.name)) for p in generated.iterdir()):
            raise VaultError('unowned_generated_file')
        actual = {p.name: p.read_bytes() for p in generated.glob('*.md')}
        if any(actual.get(name) != content for name, content in files.items()):
            raise VaultError('public_vault_outdated')
        if any(data != RETIRED_NOTE for name, data in actual.items() if name not in files):
            raise VaultError('public_vault_unreviewed_note')
        validate_links(actual)
        state = json.loads((generated / '.psychology-atlas-generated.json').read_text(encoding='utf-8'))
        if (state.get('schema_version') != 1
                or state.get('files') != {name: hashlib.sha256(data).hexdigest() for name, data in actual.items()}):
            raise VaultError('invalid_generated_state')
    else:
        write_vault(args.vault, files, repository_vault=args.repository_vault,
                    published_content=True, replace_catalogue=args.replace_catalogue)
    audit_assets([args.vault / 'generated'], known_source_ids())
    print('KNOWLEDGE_VAULT_OK', counts)


if __name__ == '__main__':
    main()
