"""Exercise the buttons users receive against real session selection/storage."""
import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import classic_quiz_handlers as classic, main
from app.identity_schema import migrate_identity_schema
from app.learning_schema import migrate_learning_schema


SCOPES = [
    ("qcnt", 1, classic.question_count_callback, classic.difficulty_mode_callback),
    ("qcntall", None, classic.question_count_mix_callback, classic.difficulty_mode_all_callback),
    ("qcntselmix", None, classic.question_count_selected_mix_callback, classic.difficulty_mode_selected_mix_callback),
]


@pytest.fixture
def quiz(tmp_path, monkeypatch):
    path = tmp_path / "quiz.sqlite3"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(Path("sql/schema.sql").read_text(encoding="utf-8"))
        migrate_identity_schema(conn)
        migrate_learning_schema(conn)
        for category in (1, 2):
            conn.execute("INSERT INTO categories(id,slug,name) VALUES(?,?,?)", (category, f"c{category}", f"Category {category}"))
            for mode in ("easy", "medium", "hard"):
                qid = conn.execute(
                    "INSERT INTO questions(external_id,category_id,source_ref,difficulty,status,question_text,explanation) "
                    "VALUES(?,?,?,?,'approved',?,?)",
                    (f"q{category}-{mode}", category, "fixture", mode, f"Question {mode}", "Explanation"),
                ).lastrowid
                conn.executemany("INSERT INTO question_options(question_id,option_index,option_text,is_correct) VALUES(?,?,?,?)",
                                 [(qid, 0, "A", 1), (qid, 1, "B", 0)])
    settings = SimpleNamespace(db_path=str(path))
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"settings": settings}),
                              user_data={"selected_mix_categories": {1}})
    sent = AsyncMock()
    monkeypatch.setattr(main, "send_current_question", sent)
    monkeypatch.setattr(main, "remove_main_menu_for_active_quiz", AsyncMock())
    return path, context, sent


def tap(data, handler, context):
    query = SimpleNamespace(data=data, answer=AsyncMock(), edit_message_text=AsyncMock())
    update = SimpleNamespace(callback_query=query,
                             effective_user=SimpleNamespace(id=123, username="fixture", first_name="F", last_name=None))
    asyncio.run(handler(update, context))
    query.answer.assert_awaited_once()
    return query


def stored(path):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(
            "SELECT q.category_id,q.difficulty FROM quiz_session_questions sq JOIN questions q ON q.id=sq.question_id"
        ).fetchall()


@pytest.mark.parametrize("prefix,category,count_handler,start_handler", SCOPES)
def test_count_starts_immediately_with_any_difficulty(quiz, prefix, category, count_handler, start_handler):
    path, context, sent = quiz
    keyboard = classic.build_question_count_keyboard(prefix, category)
    # 'All available' goes directly from count choice to a persisted quiz.
    query = tap(keyboard.inline_keyboard[3][0].callback_data, start_handler, context)
    sent.assert_awaited_once()
    query.edit_message_text.assert_not_awaited()
    rows = stored(path)
    assert {mode for _, mode in rows} == {"easy", "medium", "hard"}
    assert {cat for cat, _ in rows} == ({1, 2} if prefix == "qcntall" else {1})


@pytest.mark.parametrize("prefix,category,count_handler,start_handler", SCOPES)
@pytest.mark.parametrize("mode", ["any", "easy", "medium", "hard"])
def test_optional_filter_keeps_scope_and_waits_for_count(quiz, prefix, category, count_handler, start_handler, mode):
    path, context, sent = quiz
    initial = classic.build_question_count_keyboard(prefix, category)
    query = tap(initial.inline_keyboard[-1][0].callback_data, count_handler, context)
    filters = query.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard
    button = next(row[0] for row in filters if row[0].callback_data.endswith(":" + mode))
    query = tap(button.callback_data, start_handler, context)
    assert stored(path) == []
    sent.assert_not_awaited()
    counts = query.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard
    tap(counts[3][0].callback_data, start_handler, context)
    sent.assert_awaited_once()
    rows = stored(path)
    assert {value for _, value in rows} == ({"easy", "medium", "hard"} if mode == "any" else {mode})
    assert {cat for cat, _ in rows} == ({1, 2} if prefix == "qcntall" else {1})


@pytest.mark.parametrize("prefix,category,count_handler,start_handler", SCOPES)
def test_old_count_callback_still_allows_filter_and_start(quiz, prefix, category, count_handler, start_handler):
    path, context, sent = quiz
    scope = "" if category is None else f"{category}:"
    query = tap(f"{prefix}:{scope}5", count_handler, context)
    buttons = query.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard
    tap(buttons[-1][0].callback_data, start_handler, context)
    sent.assert_awaited_once()
    assert {mode for _, mode in stored(path)} == {"hard"}


@pytest.mark.parametrize("prefix,category,count_handler,start_handler", SCOPES)
@pytest.mark.parametrize("suffix", ["choose:invalid", "0:any", "-1:any", "oops:any", "5:any:extra"])
def test_invalid_callback_cannot_start_or_write(quiz, prefix, category, count_handler, start_handler, suffix):
    path, context, sent = quiz
    scope = "" if category is None else f"{category}:"
    mode_prefix = {"qcnt": "qmode", "qcntall": "qmodeall", "qcntselmix": "qmodeselmix"}[prefix]
    query = tap(f"{mode_prefix}:{scope}{suffix}", start_handler, context)
    sent.assert_not_awaited()
    query.edit_message_text.assert_awaited_once()
    assert stored(path) == []


def test_lost_selected_topics_does_not_fall_back_to_all(quiz):
    path, context, sent = quiz
    keyboard = classic.build_question_count_keyboard("qcntselmix")
    context.user_data.clear()
    query = tap(keyboard.inline_keyboard[0][0].callback_data, classic.difficulty_mode_selected_mix_callback, context)
    assert "Сначала выберите темы" in query.edit_message_text.call_args.args[0]
    assert stored(path) == []
    sent.assert_not_awaited()
