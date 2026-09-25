"""Statistical evidence never mutates questions or treats retries as new people."""
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys

from app.attempt_content import capture_question
from app.db import create_or_load_user, get_connection, start_quiz_session, upsert_approved_questions
from app.difficulty_calibration import report, wilson_error_interval
from app.quiz_service import answer_quiz
from tests.test_attempt_content import bank, NEW, OTHER
from tests.test_progress import record


def test_independent_first_answer_isolated_by_actor_and_captured_edition(bank):
    with closing(get_connection(str(bank))) as conn, conn:
        original_snapshot, original_sha = capture_question(conn, 1)
        before = [tuple(row) for row in conn.execute(
            "SELECT id,external_id,difficulty FROM questions ORDER BY id"
        )]
        record(conn, choices=(1,))  # Actor 1: first old edition answer is wrong.
        record(conn, choices=(0,))  # A later correct retry does not add evidence.
        actor2 = create_or_load_user(conn, 91, None, None, None)["id"]
        record(conn, actor=actor2, choices=(0,))
        record(conn, actor=actor2, choices=(1,))
        upsert_approved_questions(conn, [NEW, OTHER])
        record(conn, choices=(1,))  # Same actor, genuinely new edition.

        legacy = start_quiz_session(conn, 1, None)
        conn.execute("""INSERT INTO quiz_session_questions
            (session_id,question_id,order_index,content_snapshot,content_sha256,snapshot_provenance)
            VALUES (?,1,1,?,?,'legacy_backfill_current')""", (legacy, original_snapshot, original_sha))
        answer_quiz(conn, actor_user_id=1, session_id=legacy, question_id=1, selected_option_index=1)

        before_answers = conn.execute("SELECT count(*) FROM quiz_answers").fetchone()[0]
        result = report(conn)
        rows = [item for item in result["items"] if item["question_id"] == NEW["id"]]
        assert len(rows) == 2
        old = next(row for row in rows if row["edition_sha256"] == original_sha)
        latest = next(row for row in rows if row["current_approved_edition"])
        assert (old["independent_answers"], old["errors"], old["current_approved_edition"]) == (2, 1, False)
        assert (latest["independent_answers"], latest["errors"], latest["error_rate_pct"]) == (1, 0, 0.0)
        assert old["error_rate_wilson95_pct"] == wilson_error_interval(1, 2)
        assert latest["error_rate_wilson95_pct"][1] > 50  # One success is weak evidence.
        empty = next(item for item in result["items"] if item["question_id"] == OTHER["id"])
        assert (empty["independent_answers"], empty["error_rate_pct"], empty["error_rate_wilson95_pct"]) == (0, None, None)
        assert result["metadata_changed"] is False
        assert "user_id" not in json.dumps(result)
        assert [tuple(row) for row in conn.execute(
            "SELECT id,external_id,difficulty FROM questions ORDER BY id"
        )] == before
        assert conn.execute("SELECT count(*) FROM quiz_answers").fetchone()[0] == before_answers


def test_private_sqlite_command_reads_existing_database_only(bank, tmp_path):
    environment = {**os.environ, "DB_PATH": str(bank), "DATABASE_URL": ""}
    command = [sys.executable, "-m", "scripts.report_difficulty_evidence"]
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1],
                               env=environment, capture_output=True, text=True, check=True)
    assert json.loads(completed.stdout)["items"]
    missing = tmp_path / "missing.sqlite3"
    environment["DB_PATH"] = str(missing)
    rejected = subprocess.run(command, cwd=Path(__file__).resolve().parents[1],
                              env=environment, capture_output=True, text=True)
    assert rejected.returncode != 0 and not missing.exists()
