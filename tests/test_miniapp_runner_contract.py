import base64
import json
import sqlite3
import unittest

from app.db import abandon_in_progress_sessions_for_user, create_or_load_user, start_quiz_session, store_session_questions
from app.main import (
    MAX_MINIAPP_URL_LENGTH,
    _parse_miniapp_answer_payload,
    _build_compact_runner_question_payload,
    build_miniapp_setup_context,
    build_miniapp_url,
    build_miniapp_url_with_fallback,
    build_miniapp_open_keyboard,
    build_post_setup_miniapp_prompt,
)
from app.miniapp_runner import build_miniapp_runner_state, get_current_miniapp_question_snapshot, submit_miniapp_answer_event


def _setup_schema(conn: sqlite3.Connection) -> None:
    with open("sql/schema.sql", "r", encoding="utf-8") as f:
        conn.executescript(f.read())


class MiniAppRunnerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        _setup_schema(self.conn)

        self.conn.execute("INSERT INTO categories (slug, name) VALUES ('cat-1', 'Category 1')")
        self.conn.execute(
            "INSERT INTO questions (external_id, category_id, source_ref, difficulty, status, question_text, explanation) VALUES ('q1', 1, 'src', 'easy', 'approved', 'Q1?', 'E1')"
        )
        self.conn.execute(
            "INSERT INTO questions (external_id, category_id, source_ref, difficulty, status, question_text, explanation) VALUES ('q2', 1, 'src', 'easy', 'approved', 'Q2?', 'E2')"
        )
        self.conn.execute(
            "INSERT INTO question_options (question_id, option_index, option_text, is_correct) VALUES (1, 0, 'A', 1), (1, 1, 'B', 0), (2, 0, 'A', 0), (2, 1, 'B', 1)"
        )

        user = create_or_load_user(self.conn, 1001, "u1", "U", None)
        self.user_id = int(user["id"])
        self.session_id = start_quiz_session(self.conn, self.user_id, 1)
        store_session_questions(self.conn, self.session_id, [1, 2])

    def tearDown(self) -> None:
        self.conn.close()

    def test_valid_answer_transition(self):
        result = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        self.assertEqual("accepted", result.status)
        self.assertTrue(result.is_correct)

    def test_invalid_option_rejected(self):
        result = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=99,
        )
        self.assertEqual("invalid_option", result.status)

    def test_stale_question_rejected(self):
        accepted = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        self.assertEqual("accepted", accepted.status)
        stale = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        self.assertEqual("stale_question", stale.status)
        self.assertEqual(2, stale.expected_question_id)

    def test_duplicate_submission_handled_safely(self):
        first = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        self.assertEqual("accepted", first.status)
        duplicate = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        self.assertIn(duplicate.status, {"stale_question", "duplicate"})

    def test_wrong_user_rejected(self):
        other = create_or_load_user(self.conn, 2002, "u2", "U2", None)
        result = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=int(other["id"]),
            question_id=1,
            selected_option_index=0,
        )
        self.assertEqual("forbidden", result.status)

    def test_snapshot_for_authorized_user(self):
        result = get_current_miniapp_question_snapshot(
            self.conn,
            actor_user_id=self.user_id,
            session_id=self.session_id,
        )
        self.assertEqual("ok", result.status)
        self.assertEqual(1, result.question_id)
        self.assertEqual(1, result.order_index)
        self.assertEqual(2, result.total_questions)
        self.assertTrue(result.options)
        self.assertNotIn("is_correct", result.options[0])



    def test_runner_state_in_progress_contains_server_progress(self):
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        self.assertEqual("in_progress", state.get("state"))
        self.assertTrue(state.get("server_derived"))
        progress = state.get("progress", {})
        self.assertEqual(1, progress.get("current_question_number"))
        self.assertEqual(2, progress.get("total_questions"))
        self.assertEqual(0, progress.get("answered_count"))
        self.assertEqual(2, progress.get("remaining_count"))

    def test_runner_progress_changes_after_accepted_answer(self):
        submit_miniapp_answer_event(self.conn, session_id=self.session_id, actor_user_id=self.user_id, question_id=1, selected_option_index=0)
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        progress = state.get("progress", {})
        self.assertEqual(1, progress.get("answered_count"))
        self.assertEqual(1, progress.get("remaining_count"))

    def test_runner_state_completed_contains_result(self):
        submit_miniapp_answer_event(self.conn, session_id=self.session_id, actor_user_id=self.user_id, question_id=1, selected_option_index=0)
        submit_miniapp_answer_event(self.conn, session_id=self.session_id, actor_user_id=self.user_id, question_id=2, selected_option_index=1)
        self.conn.execute("UPDATE quiz_sessions SET status='finished', score=2, total_questions=2 WHERE id = ?", (self.session_id,))
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        self.assertEqual("completed", state.get("state"))
        self.assertEqual("finished", state.get("status"))
        result = state.get("result", {})
        self.assertEqual(2, result.get("score"))
        self.assertEqual(2, result.get("total_questions"))
        self.assertEqual(100, result.get("percent"))
        self.assertNotIn("stats", state)

    def test_runner_state_no_active_session_returns_setup(self):
        user = create_or_load_user(self.conn, 3003, "u3", "U3", None)
        state = build_miniapp_runner_state(self.conn, actor_user_id=int(user["id"]))
        self.assertEqual("setup", state.get("state"))

    def test_runner_state_wrong_user_forbidden(self):
        other = create_or_load_user(self.conn, 2002, "u2", "U2", None)
        state = build_miniapp_runner_state(self.conn, actor_user_id=int(other["id"]), session_id=self.session_id)
        self.assertEqual("forbidden", state.get("state"))

    def test_runner_state_without_session_id_uses_latest_finished_result(self):
        submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=2,
            selected_option_index=1,
        )
        self.conn.execute(
            "UPDATE quiz_sessions SET status='finished', score=2, total_questions=2 WHERE id = ?",
            (self.session_id,),
        )
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id)
        self.assertEqual("completed", state.get("state"))
        self.assertEqual(2, state.get("result", {}).get("score"))

    def test_runner_state_prefers_in_progress_over_older_finished(self):
        self.conn.execute(
            "UPDATE quiz_sessions SET status='finished', score=1, total_questions=2 WHERE id = ?",
            (self.session_id,),
        )
        newer_session_id = start_quiz_session(self.conn, self.user_id, 1)
        store_session_questions(self.conn, newer_session_id, [1, 2])

        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id)
        self.assertEqual("in_progress", state.get("state"))
        self.assertEqual(newer_session_id, state.get("session", {}).get("session_id"))
    def test_parse_valid_miniapp_answer_payload(self):
        parsed = _parse_miniapp_answer_payload({
            "type": "quiz_answer",
            "session_id": self.session_id,
            "question_id": 1,
            "selected_option_index": 0,
        })
        self.assertEqual((self.session_id, 1, 0), parsed)

    def test_parse_malformed_miniapp_answer_payload(self):
        self.assertIsNone(_parse_miniapp_answer_payload({"type": "quiz_answer", "session_id": "1"}))
        self.assertIsNone(_parse_miniapp_answer_payload({"type": "quiz_answer", "session_id": 0, "question_id": 1, "selected_option_index": 0}))

    def test_snapshot_moves_to_next_question_after_accepted_answer(self):
        accepted = submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        self.assertEqual("accepted", accepted.status)
        snapshot = get_current_miniapp_question_snapshot(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        self.assertEqual("ok", snapshot.status)
        self.assertEqual(2, snapshot.question_id)

    def test_snapshot_wrong_user_forbidden(self):
        other = create_or_load_user(self.conn, 2002, "u2", "U2", None)
        result = get_current_miniapp_question_snapshot(
            self.conn,
            actor_user_id=int(other["id"]),
            session_id=self.session_id,
        )
        self.assertEqual("forbidden", result.status)

    def test_snapshot_finished_session_safe_status(self):
        submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=1,
            selected_option_index=0,
        )
        submit_miniapp_answer_event(
            self.conn,
            session_id=self.session_id,
            actor_user_id=self.user_id,
            question_id=2,
            selected_option_index=1,
        )
        self.conn.execute("UPDATE quiz_sessions SET status = 'finished' WHERE id = ?", (self.session_id,))
        result = get_current_miniapp_question_snapshot(
            self.conn,
            actor_user_id=self.user_id,
            session_id=self.session_id,
        )
        self.assertEqual("session_not_in_progress", result.status)

    def test_parse_bool_values_rejected_in_answer_payload(self):
        self.assertIsNone(_parse_miniapp_answer_payload({
            "type": "quiz_answer",
            "session_id": True,
            "question_id": 1,
            "selected_option_index": 0,
        }))

    def test_runner_state_current_question_does_not_expose_correctness_flags(self):
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        current_question = state.get("current_question", {})
        self.assertNotIn("is_correct", current_question)
        options = current_question.get("options", [])
        self.assertTrue(options)
        self.assertNotIn("is_correct", options[0])

    def test_runner_state_without_session_id_prefers_in_progress_over_newer_finished(self):
        self.conn.execute(
            "UPDATE quiz_sessions SET status='finished', score=1, total_questions=2, finished_at=CURRENT_TIMESTAMP WHERE id = ?",
            (self.session_id,),
        )
        in_progress_id = start_quiz_session(self.conn, self.user_id, 1)
        store_session_questions(self.conn, in_progress_id, [1, 2])

        newer_finished_id = start_quiz_session(self.conn, self.user_id, 1)
        store_session_questions(self.conn, newer_finished_id, [1, 2])
        self.conn.execute(
            "UPDATE quiz_sessions SET status='finished', score=2, total_questions=2, finished_at=CURRENT_TIMESTAMP WHERE id = ?",
            (newer_finished_id,),
        )

        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id)
        self.assertEqual("in_progress", state.get("state"))
        self.assertEqual(in_progress_id, state.get("session", {}).get("session_id"))

    def test_context_builder_does_not_duplicate_question_payload_by_default(self):
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        categories = [{"id": 1, "name": "Category 1"}]
        context = build_miniapp_setup_context(categories, runner_state=state)
        self.assertIn("runner_state", context)
        self.assertNotIn("current_question_snapshot", context)

    def test_full_context_with_large_question_can_exceed_limit(self):
        long_text = "X" * 2400
        self.conn.execute("UPDATE questions SET question_text = ? WHERE id = 1", (long_text,))
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        categories = [{"id": 1, "name": "Category 1"}]
        url = build_miniapp_url("https://example.com/ui", build_miniapp_setup_context(categories, runner_state=state))
        self.assertGreater(len(url), MAX_MINIAPP_URL_LENGTH)


    def test_in_progress_context_omits_categories(self):
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        url, used_fallback = build_miniapp_url_with_fallback("https://example.com/ui", [{"id": 1, "name": "Category 1"}], state)
        self.assertFalse(used_fallback)
        self.assertIsNotNone(url)
        encoded = url.split("context=", 1)[1]
        padded = encoded + ("=" * ((4 - len(encoded) % 4) % 4))
        ctx = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        self.assertEqual("runner", ctx.get("mode"))
        self.assertEqual([], ctx.get("categories"))

    def test_completed_context_omits_categories(self):
        self.conn.execute("UPDATE quiz_sessions SET status='finished', score=2, total_questions=2 WHERE id = ?", (self.session_id,))
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        url, _ = build_miniapp_url_with_fallback("https://example.com/ui", [{"id": 1, "name": "Category 1"}], state)
        encoded = url.split("context=", 1)[1]
        padded = encoded + ("=" * ((4 - len(encoded) % 4) % 4))
        ctx = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        self.assertEqual("completed", ctx.get("mode"))
        self.assertEqual([], ctx.get("categories"))

    def test_setup_context_still_includes_categories(self):
        user = create_or_load_user(self.conn, 3333, "u4", "U4", None)
        state = build_miniapp_runner_state(self.conn, actor_user_id=int(user["id"]))
        url, _ = build_miniapp_url_with_fallback("https://example.com/ui", [{"id": 1, "name": "Category 1"}], state)
        encoded = url.split("context=", 1)[1]
        padded = encoded + ("=" * ((4 - len(encoded) % 4) % 4))
        ctx = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        self.assertEqual("setup", ctx.get("mode"))
        self.assertEqual(1, len(ctx.get("categories", [])))

    def test_compact_runner_payload_omits_categories_contains_question_and_no_correctness(self):
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        payload = _build_compact_runner_question_payload(state)
        self.assertEqual("runner", payload.get("m"))
        self.assertNotIn("categories", payload)
        self.assertIsInstance(payload.get("qt"), str)
        self.assertTrue(payload.get("o"))
        self.assertNotIn("is_correct", json.dumps(payload, ensure_ascii=False))

    def test_compact_runner_payload_shorter_than_verbose(self):
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        compact = json.dumps(_build_compact_runner_question_payload(state), ensure_ascii=False, separators=(",", ":"))
        verbose = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        self.assertLess(len(compact), len(verbose))

    def test_runner_url_prefers_compact_question_payload_and_fits(self):
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        url, used_fallback = build_miniapp_url_with_fallback(
            "https://example.com/ui",
            [{"id": 1, "name": "Category 1"}],
            state,
            api_base_url="https://api.example.com",
        )
        self.assertFalse(used_fallback)
        self.assertLessEqual(len(url), MAX_MINIAPP_URL_LENGTH)
        ctx = json.loads(base64.urlsafe_b64decode((url.split("context=", 1)[1] + "=" * ((4 - len(url.split("context=", 1)[1]) % 4) % 4)).encode("ascii")).decode("utf-8"))
        self.assertIn("runner_q", ctx)
        self.assertEqual([], ctx.get("categories"))
        self.assertEqual("https://api.example.com", ctx.get("api_base_url"))

    def test_context_omits_api_base_when_not_configured(self):
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        url, _ = build_miniapp_url_with_fallback(
            "https://example.com/ui",
            [{"id": 1, "name": "Category 1"}],
            state,
            api_base_url=None,
        )
        ctx = json.loads(base64.urlsafe_b64decode((url.split("context=", 1)[1] + "=" * ((4 - len(url.split("context=", 1)[1]) % 4) % 4)).encode("ascii")).decode("utf-8"))
        self.assertNotIn("api_base_url", ctx)

    def test_extreme_long_question_falls_back_to_progress_only(self):
        long_text = "Y" * 2400
        long_option = "Z" * 1600
        self.conn.execute("UPDATE questions SET question_text = ? WHERE id = 1", (long_text,))
        self.conn.execute("UPDATE question_options SET option_text = ? WHERE question_id = 1", (long_option,))
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        url, used_fallback = build_miniapp_url_with_fallback("https://example.com/ui", [{"id": 1, "name": "Category 1"}], state)
        self.assertTrue(used_fallback)
        self.assertIsNotNone(url)
        ctx = json.loads(base64.urlsafe_b64decode((url.split("context=", 1)[1] + "=" * ((4 - len(url.split("context=", 1)[1]) % 4) % 4)).encode("ascii")).decode("utf-8"))
        self.assertTrue(ctx.get("runner_state", {}).get("compact_progress_only"))
        self.assertNotIn("runner_q", ctx)

    def test_force_setup_context_overrides_active_session(self):
        setup_state = {"state": "setup", "status": "force_setup", "server_derived": True}
        url, _ = build_miniapp_url_with_fallback(
            "https://example.com/ui",
            [{"id": 1, "name": "Category 1"}],
            setup_state,
            abandons_active_session=True,
        )
        encoded = url.split("context=", 1)[1]
        padded = encoded + ("=" * ((4 - len(encoded) % 4) % 4))
        ctx = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        self.assertEqual("setup", ctx.get("mode"))
        self.assertEqual(1, len(ctx.get("categories", [])))
        self.assertTrue(ctx.get("force_setup"))
        self.assertTrue(ctx.get("abandons_active_session"))

    def test_normal_setup_context_has_no_abandon_marker(self):
        user = create_or_load_user(self.conn, 4444, "u5", "U5", None)
        state = build_miniapp_runner_state(self.conn, actor_user_id=int(user["id"]))
        url, _ = build_miniapp_url_with_fallback("https://example.com/ui", [{"id": 1, "name": "Category 1"}], state)
        encoded = url.split("context=", 1)[1]
        padded = encoded + ("=" * ((4 - len(encoded) % 4) % 4))
        ctx = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        self.assertNotIn("force_setup", ctx)
        self.assertNotIn("abandons_active_session", ctx)

    def test_abandon_old_in_progress_before_new_session(self):
        newer_session = start_quiz_session(self.conn, self.user_id, 1)
        store_session_questions(self.conn, newer_session, [1, 2])
        updated = abandon_in_progress_sessions_for_user(self.conn, self.user_id)
        self.assertGreaterEqual(updated, 2)
        replacement = start_quiz_session(self.conn, self.user_id, 1)
        store_session_questions(self.conn, replacement, [1, 2])
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id)
        self.assertEqual(replacement, state.get("session", {}).get("session_id"))

    def test_open_keyboard_can_include_setup_button(self):
        kb = build_miniapp_open_keyboard("https://example.com/ui?context=x", force_setup_url="https://example.com/ui?context=y")
        self.assertEqual(3, len(kb.keyboard))


    def test_post_setup_prompt_returns_open_miniapp_keyboard(self):
        state = build_miniapp_runner_state(self.conn, actor_user_id=self.user_id, session_id=self.session_id)
        categories = [{"id": 1, "name": "Category 1"}]
        text, keyboard = build_post_setup_miniapp_prompt("https://example.com/ui", categories, state)
        self.assertIn("Откройте Mini App", text)
        self.assertIn("/quiz", text)
        self.assertIsNotNone(keyboard)
        self.assertEqual("🧪 Продолжить в Mini App", keyboard.keyboard[0][0].text)


if __name__ == "__main__":
    unittest.main()
