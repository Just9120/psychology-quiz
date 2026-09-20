"""Telegram adapter for durable glossary; identity comes from verified initData."""
from contextlib import closing

from app import glossary_service as service
from app.db import create_or_load_user, get_connection

list_glossary_topics_payload = service.topics


def run(db_path, telegram_user_id, operation, *args, **kwargs):
    with closing(get_connection(db_path)) as conn, conn:
        actor = conn.execute('SELECT id FROM users WHERE telegram_user_id=?', (telegram_user_id,)).fetchone()
        if actor is None:
            actor = create_or_load_user(conn, telegram_user_id, None, None, None)
        return operation(conn, actor['id'], *args, **kwargs)


def start_glossary_session(telegram_user_id, topic_id, count, *, db_path, expected_session_id=None, replace_active=False):
    return run(db_path, telegram_user_id, service.start, topic_id, count,
               expected_session_id=expected_session_id, replace_active=replace_active)


def answer_glossary_session(telegram_user_id, session_id, selected_option_index, step_id, *, db_path):
    return run(db_path, telegram_user_id, service.answer, session_id, selected_option_index, step_id)


def next_glossary_session(telegram_user_id, session_id, step_id, *, db_path):
    return run(db_path, telegram_user_id, service.advance, session_id, step_id)


def restart_glossary_session(telegram_user_id, session_id, *, db_path):
    return run(db_path, telegram_user_id, service.restart, session_id)
