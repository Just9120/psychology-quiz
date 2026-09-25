"""Durable glossary for a verified learning actor; caller owns transaction.

One actor lock serializes setup, answers, advances and learning reset across all
clients. Questions/options/definitions are captured once, never regenerated on
resume. JSON documents belong to one bounded attempt, not the shared bank.
"""
from dataclasses import asdict
from datetime import datetime, timezone
import json
import random
import secrets

from app.database import begin_write
from app.glossary import GLOSSARY_TOPICS, build_glossary_quiz_question, load_glossary_entries


class GlossaryError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def _encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def topics():
    return {'topics': [{'topic_id': key, 'title': title, 'available_count': len(load_glossary_entries(key) or [])}
                       for key, title in GLOSSARY_TOPICS], 'question_count_choices': [5, 10, 'all']}


def _load(conn, actor, sid, *, allow_abandoned=False):
    if not isinstance(sid, str) or not 1 <= len(sid) <= 64:
        raise GlossaryError('invalid_glossary_session', 400)
    row = conn.execute('SELECT * FROM glossary_sessions WHERE id=? AND user_id=?', (sid, actor)).fetchone()
    if row is None or (row['status'] == 'abandoned' and not allow_abandoned):
        raise GlossaryError('glossary_changed')
    return row, json.loads(row['snapshot']), json.loads(row['state'])


def _question(row, snapshot, step):
    item = snapshot['questions'][step - 1]
    topic_id = item['entry']['topic_id']
    return {'session_id': row['id'], 'step_id': step, 'topic_id': topic_id,
            'topic_title': snapshot.get('topic_titles', {}).get(topic_id, row['topic_title']),
            'order_index': step, 'total_questions': len(snapshot['questions']), 'term': item['entry']['term'],
            'options': [{'option_index': index, 'option_text': text} for index, text in enumerate(item['options'])]}


def _public(row, snapshot, state):
    common = {'session_id': row['id'], 'topic_id': row['topic_id'], 'topic_title': row['topic_title']}
    if snapshot.get('topics'):
        common['topic_ids'] = snapshot['topics']
    if row['status'] == 'completed':
        return {**common, 'state': 'completed', 'result': {'score': state['score'], 'total_questions': len(snapshot['questions'])}}
    step = state['step']
    answer = state['answers'].get(str(step))
    if answer is not None:
        return {**common, **answer['response'], 'current_question': _question(row, snapshot, step)}
    return {**common, 'state': 'in_progress', 'current_question': _question(row, snapshot, step)}


def state(conn, actor, sid=None):
    begin_write(conn, f'actor:{actor}')
    if sid is None:
        row = conn.execute("""SELECT id FROM glossary_sessions WHERE user_id=? AND status!='abandoned'
            ORDER BY CASE WHEN status='in_progress' THEN 0 ELSE 1 END,created_at DESC,id DESC LIMIT 1""", (actor,)).fetchone()
        if row is None:
            return {'state': 'idle'}
        sid = row['id']
    return _public(*_load(conn, actor, sid))


def _save(conn, row, value, status=None):
    conn.execute('UPDATE glossary_sessions SET state=?,status=?,updated_at=? WHERE id=? AND user_id=?',
                 (_encode(value), status or row['status'], _now(), row['id'], row['user_id']))


def start(conn, actor, topic_id, count, *, expected_session_id=None, replace_active=False,
          selected_entry_ids=None):
    known = dict(GLOSSARY_TOPICS)
    topic_ids = [topic_id] if isinstance(topic_id, str) else topic_id
    if (not isinstance(topic_ids, list) or not 1 <= len(topic_ids) <= len(known)
            or any(not isinstance(item, str) or item not in known for item in topic_ids)
            or len(set(topic_ids)) != len(topic_ids)
            or (selected_entry_ids is not None and len(topic_ids) != 1)):
        raise GlossaryError('invalid_glossary_setup', 400)
    if count not in (None, 'all') and (type(count) is not int or count not in (5, 10)):
        raise GlossaryError('invalid_glossary_setup', 400)
    begin_write(conn, f'actor:{actor}')
    active = conn.execute("SELECT id FROM glossary_sessions WHERE user_id=? AND status='in_progress'", (actor,)).fetchone()
    if (active['id'] if active else None) != expected_session_id:
        raise GlossaryError('glossary_changed')
    if active and replace_active is not True:
        raise GlossaryError('active_glossary')
    by_topic = {item: load_glossary_entries(item) for item in topic_ids}
    if any(not by_topic[item] or len(by_topic[item]) < 4 or
           any(entry.topic_id != item for entry in by_topic[item]) for item in topic_ids):
        raise GlossaryError('glossary_unavailable')
    entries = [entry for item in topic_ids for entry in (by_topic[item] or [])]
    if selected_entry_ids is None:
        limit = len(entries) if count in (None, 'all') else min(count, len(entries))
        if len(topic_ids) > 1 and limit < len(entries):
            # A mixed attempt always shows more than one selected topic even
            # when a small sample is drawn from a much larger corpus.
            guaranteed = [random.choice(by_topic[item]) for item in random.sample(topic_ids, 2)]
            selected = guaranteed + random.sample([entry for entry in entries if entry not in guaranteed], limit - 2)
            random.shuffle(selected)
        else:
            selected = random.sample(entries, limit)
    else:
        requested = set(selected_entry_ids)
        selected = [entry for entry in entries if entry.id in requested]
        if not selected or len(selected) != len(requested):
            raise GlossaryError('glossary_changed')
        random.shuffle(selected)
    questions = [build_glossary_quiz_question(by_topic[entry.topic_id], entry) for entry in selected]
    if any(item is None for item in questions):
        raise GlossaryError('glossary_unavailable')
    snapshot = {'version': 2, 'topics': topic_ids, 'topic_titles': {item: known[item] for item in topic_ids},
                'questions': [asdict(item) for item in questions]}
    value = {'version': 1, 'step': 1, 'score': 0, 'answers': {}, 'advances': {}, 'restarted': None}
    sid, now = secrets.token_urlsafe(16), _now()
    if active:
        conn.execute("UPDATE glossary_sessions SET status='abandoned',updated_at=? WHERE id=?", (now, active['id']))
    stored_topic = topic_ids[0] if len(topic_ids) == 1 else '__mixed__'
    stored_title = known[stored_topic] if len(topic_ids) == 1 else 'Несколько тем'
    conn.execute("INSERT INTO glossary_sessions VALUES(?,?,?,?,?,?,?,?,?)",
                 (sid, actor, stored_topic, stored_title, 'in_progress', _encode(snapshot), _encode(value), now, now))
    return state(conn, actor, sid)


def answer(conn, actor, sid, selected, step):
    if type(step) is not int or step < 1 or type(selected) is not int:
        raise GlossaryError('invalid_glossary_answer', 400)
    begin_write(conn, f'actor:{actor}')
    row, snapshot, value = _load(conn, actor, sid)
    previous = value['answers'].get(str(step))
    if previous:
        if previous['selected'] != selected:
            raise GlossaryError('glossary_changed')
        return previous['response']
    if row['status'] != 'in_progress' or step != value['step'] or step > len(snapshot['questions']):
        raise GlossaryError('glossary_changed')
    question = snapshot['questions'][step - 1]
    if not 0 <= selected < len(question['options']):
        raise GlossaryError('invalid_glossary_answer', 400)
    correct = question['correct_option_index']
    feedback = {'step_id': step, 'is_correct': selected == correct, 'selected_option_index': selected,
                'selected_option_text': question['options'][selected], 'correct_option_index': correct,
                'correct_option_text': question['options'][correct], 'explanation': question['entry']['definition'],
                'answered_count': step, 'total_questions': len(snapshot['questions']), 'has_next': step < len(snapshot['questions'])}
    result = {'state': 'feedback', 'feedback': feedback}
    answered_at = _now()
    value['answers'][str(step)] = {'selected': selected, 'response': result, 'answered_at': answered_at}
    value['score'] += int(selected == correct)
    _save(conn, row, value)
    if conn.execute("""SELECT 1 FROM user_review_sessions
            WHERE user_id=? AND session_kind='glossary' AND session_key=?""", (actor, sid)).fetchone():
        conn.execute("""INSERT INTO user_review_events(user_id,answer_kind,answer_key,answered_at)
            VALUES(?,'glossary',?,?) ON CONFLICT(user_id,answer_kind,answer_key) DO NOTHING""",
            (actor, f'{sid}:{step}', answered_at))
    return result


def advance(conn, actor, sid, step):
    if type(step) is not int or step < 1:
        raise GlossaryError('invalid_glossary_session', 400)
    begin_write(conn, f'actor:{actor}')
    row, snapshot, value = _load(conn, actor, sid)
    if str(step) in value['advances']:
        return value['advances'][str(step)]
    if row['status'] != 'in_progress' or step != value['step']:
        raise GlossaryError('glossary_changed')
    if str(step) not in value['answers']:
        return _public(row, snapshot, value)
    value['step'] += 1
    status = 'completed' if value['step'] > len(snapshot['questions']) else 'in_progress'
    result = _public({**dict(row), 'status': status}, snapshot, value)
    value['advances'][str(step)] = result
    _save(conn, row, value, status)
    return result


def restart(conn, actor, sid):
    begin_write(conn, f'actor:{actor}')
    row, snapshot, value = _load(conn, actor, sid, allow_abandoned=True)
    if value['restarted']:
        # A reset/replacement never revives the old attempt or removed questions.
        return state(conn, actor, value['restarted'])
    if row['status'] == 'abandoned':
        raise GlossaryError('glossary_changed')
    active = conn.execute("SELECT id FROM glossary_sessions WHERE user_id=? AND status='in_progress'", (actor,)).fetchone()
    if active and active['id'] != sid:
        raise GlossaryError('glossary_changed')
    count = len(snapshot['questions'])
    result = start(conn, actor, snapshot.get('topics', [row['topic_id']]), count if count in (5, 10) else 'all',
                   expected_session_id=active['id'] if active else None, replace_active=True)
    value['restarted'] = result['session_id']
    _save(conn, row, value, 'completed' if row['status'] == 'completed' else 'abandoned')
    return result
