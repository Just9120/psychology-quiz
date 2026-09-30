from contextlib import closing
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import literature_service
from app.db import get_connection
from app.literature import load_literature_items
from tests.test_attempt_content import bank, TOKEN
from tests.test_miniapp_api import _make_init_data
from tests.test_web_auth import web, post, register, login


def linked(web):
    register(web)
    csrf = login(web)
    code = post(web, 'link/start', csrf=csrf).json()['code']
    web.auth.propose_telegram_link(code, SimpleNamespace(id=42, username=None, first_name=None, last_name=None))
    web.auth.confirm_telegram_link(code, 42)
    assert post(web, 'link/complete', csrf=csrf).status_code == 200
    return csrf


def rows(web):
    with closing(get_connection(str(web.db))) as conn:
        return {table: [tuple(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY user_id').fetchall()]
                for table in ('user_literature_progress', 'user_literature_work_progress')}


def test_reading_shared_actor_preserves_distinct_lists_private_notes_and_other_actor(web):
    assert web.client.get('/web/literature/catalog').status_code == 401
    csrf = linked(web)
    catalog = web.client.get('/web/literature/catalog')
    assert catalog.status_code == 200 and catalog.headers['cache-control'] == 'no-store'
    works = catalog.json()['works']
    assert len(works) == len({item['work_id'] for item in load_literature_items()})
    assert len(works) < len(load_literature_items())
    assert all(set(entry['source']) == {'citation'}
               for work in works for entry in work['entries'])
    corpus = json.loads((Path(__file__).resolve().parents[1] / 'content/source-corpus.json').read_text(encoding='utf-8'))
    assert not any(source['id'] in catalog.text for source in corpus['sources'])
    pair = next(work['entries'] for work in works if len(work['entries']) == 2)
    first, second = pair[0]['id'], pair[1]['id']
    with closing(get_connection(str(web.db))) as conn, conn:
        conn.execute("INSERT INTO user_literature_progress(user_id,literature_id,reading_status,updated_at,private_note,remind_at) VALUES(1,?,'not_started','2026-01-01','private retained history','2030-01-01')", (first,))
    history = rows(web)['user_literature_progress']
    body = {'literature_id': first, 'reading_status': 'in_progress', 'progress_percent': None, 'actor': 999}
    assert post(web, 'literature/progress', body).status_code == 403
    assert post(web, 'literature/progress', body, csrf=csrf, headers={'Origin':'https://foreign.test'}).status_code == 403
    assert post(web, 'literature/progress', body, csrf=csrf).status_code == 200
    headers = {'Authorization': 'tma ' + _make_init_data(TOKEN, {'id':42})}
    other = {'Authorization': 'tma ' + _make_init_data(TOKEN, {'id':99})}
    state = web.client.get('/miniapp/literature/state', headers=headers).json()['literature_state']
    assert next(row for row in state if row['literature_id'] == first)['progress_percent'] is None
    assert not any(row['literature_id'] == 'lit' for row in state)
    assert next(row for row in state if row['literature_id'] == second)['reading_status'] == 'in_progress'
    assert web.client.get('/miniapp/literature/state', headers=other).json()['literature_state'] == []
    response = web.client.post('/miniapp/literature/progress', headers=headers, json={**body, 'literature_id':second, 'reading_status':'read'})
    assert response.status_code == 200
    assert web.client.post('/miniapp/literature/progress', headers=headers,
                           json={**body, 'literature_id':second, 'progress_percent':37}).status_code == 400
    loaded = web.client.get('/web/literature/catalog')
    assert 'private' not in loaded.text
    entries = {entry['id']:entry for work in loaded.json()['works'] for entry in work['entries']}
    assert entries[first]['user_state']['progress_percent'] is None
    assert entries[second]['user_state']['progress_percent'] is None
    assert entries[first]['user_state']['reading_status'] == entries[second]['user_state']['reading_status'] == 'read'
    assert post(web, 'literature/progress', {**body, 'reading_status':'read'}, csrf=csrf).status_code == 200
    with closing(get_connection(str(web.db))) as conn:
        row = conn.execute('SELECT private_note, remind_at FROM user_literature_progress WHERE literature_id=?', (first,)).fetchone()
        assert tuple(row) == ('private retained history', '2030-01-01')
    assert rows(web)['user_literature_progress'] == history


@pytest.mark.parametrize('patch', [dict(literature_id='missing'), dict(reading_status='bad'), dict(progress_percent=True), dict(progress_percent=-1), dict(progress_percent=37), dict(progress_percent=101), dict(progress_percent='30')])
def test_invalid_reading_payload_does_not_write(web, patch):
    csrf = linked(web)
    before = rows(web)
    body = dict(literature_id=load_literature_items()[0]['id'], reading_status='in_progress', progress_percent=None)
    assert post(web, 'literature/progress', {**body, **patch}, csrf=csrf).status_code == 400
    assert rows(web) == before


def test_reading_write_rollback_and_identity_required(web):
    register(web)
    csrf = login(web)
    assert web.client.get('/web/literature/catalog').status_code == 409
    assert post(web, 'identity/new', csrf=csrf).status_code == 200
    before = rows(web)
    with closing(get_connection(str(web.db))) as conn:
        actor = conn.execute('SELECT user_id FROM web_accounts').fetchone()[0]
        with pytest.raises(RuntimeError), conn:
            literature_service.save_progress(conn, actor, load_literature_items()[0]['id'], 'read', None)
            raise RuntimeError('rollback')
    assert rows(web) == before
