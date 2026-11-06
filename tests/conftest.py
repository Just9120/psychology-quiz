"""Opt-in synthetic fixtures; private knowledge bodies are never needed in CI."""
import hashlib
import json

import pytest


@pytest.fixture
def vault_reviewed_payload(monkeypatch):
    from scripts import obsidian_catalogue as catalogue
    manifest = {'schema_version': 2, 'notes': [
        {'title': 'Уточнение запроса', 'section': 'Основы консультирования',
         'body': 'Уточнение запроса позволяет согласовать предмет работы с клиентом. '
                 'Предположение консультанта требует проверки, а не замены слов клиента.',
         'links': {'Рабочая гипотеза': 'Предположение уточняется совместно с клиентом.'},
         'sources': ['Синтетическое основание проверки: уточнение запроса.']},
        {'title': 'Рабочая гипотеза', 'section': 'Основы консультирования',
         'body': 'Рабочая гипотеза описывает проверяемое предположение о ситуации клиента. '
                 'Она уточняется по новым данным и не является готовым диагнозом.',
         'links': {'Уточнение запроса': 'Запрос определяет предмет проверки гипотезы.'},
         'sources': ['Синтетическое основание проверки: проверка гипотез.']},
    ], 'coverage': {'summaries': {'Основы консультирования':
        'Согласование предмета работы и проверка предположений связаны между собой. '
        'Эти заметки показывают ограничения вывода и не заменяют полный учебный курс.'},
        'statement': 'Проверены отдельные фрагменты учебных лекций. Наличие заметок не '
        'подтверждает весь источник, научные удержания сохраняются. Это не полный пересказ курса.'}}
    payload = json.dumps(manifest, ensure_ascii=False).encode()
    # Only this fixture's bytes pass the actual pinned-review gate in its test.
    monkeypatch.setattr(catalogue, 'REVIEWED_NOTES_SHA256', hashlib.sha256(payload).hexdigest())
    return payload
