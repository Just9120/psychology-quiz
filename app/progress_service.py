"""Personal practice evidence, read from shared attempts rather than a second store.

The transport supplies a verified users.id and owns the transaction. Public
payloads never accept an actor. All detail pages expose answered questions only.
"""
from __future__ import annotations

import random

from app.attempt_content import capture_question, get_attempt_content
from app.database import begin_write, is_postgres
from app.quiz_service import PreparedQuiz, start_prepared_quiz

PAGE_SIZE = 20
DAY_COUNT = 14


class ProgressError(ValueError):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def positive_id(value, *, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ProgressError("invalid_payload")
    return value


def counts(answered, correct):
    answered, correct = int(answered or 0), int(correct or 0)
    return {"answered": answered, "correct": correct,
            "accuracy": round(100 * correct / answered, 1) if answered else None}


def overview(conn, actor: int) -> dict:
    # Group by the topic of the recorded edition, even if today's bank changed.
    topic = "sq.content_snapshot::jsonb->>'category'" if is_postgres(conn) else "json_extract(sq.content_snapshot, '$.category')"
    evidence = f"""SELECT a.is_correct, substr(a.answered_at,1,10) AS day,
                          COALESCE({topic}, 'Тема не указана') AS topic
                   FROM quiz_sessions s JOIN quiz_answers a ON a.session_id=s.id
                   JOIN quiz_session_questions sq ON sq.session_id=a.session_id AND sq.question_id=a.question_id
                   WHERE s.user_id=?"""
    summary = conn.execute(f"SELECT count(*),sum(is_correct) FROM ({evidence}) evidence", (actor,)).fetchone()
    attempts = conn.execute("""SELECT count(*),sum(CASE WHEN status='finished' THEN 1 ELSE 0 END)
                                FROM quiz_sessions WHERE user_id=?""", (actor,)).fetchone()
    topics = [{"topic": row[0], **counts(row[1], row[2]), "days": []} for row in conn.execute(
        f"SELECT topic,count(*),sum(is_correct) FROM ({evidence}) evidence GROUP BY topic ORDER BY topic", (actor,))]
    by_topic = {item["topic"]: item for item in topics}
    # SQL aggregates the full history; only the last 14 active UTC days per topic
    # cross the DB boundary. There is no silent truncation of the total counts.
    for row in conn.execute(f"""WITH evidence AS ({evidence}), daily AS (
        SELECT topic,day,count(*) AS answered,sum(is_correct) AS correct FROM evidence GROUP BY topic,day
    ), ranked AS (SELECT *,row_number() OVER (PARTITION BY topic ORDER BY day DESC) AS pos FROM daily)
    SELECT topic,day,answered,correct FROM ranked WHERE pos<=? ORDER BY day""", (actor, DAY_COUNT)):
        by_topic[row[0]]["days"].append({"day": row[1], **counts(row[2], row[3])})
    days = [{"day": row[0], **counts(row[1], row[2])} for row in conn.execute(f"""
        SELECT day,count(*),sum(is_correct) FROM ({evidence}) evidence
        GROUP BY day ORDER BY day DESC LIMIT ?""", (actor, DAY_COUNT))]
    topics.sort(key=lambda item: (item["accuracy"], -item["answered"], item["topic"]))
    return {"ok": True, "summary": {**counts(*summary), "attempts": int(attempts[0]),
            "finished": int(attempts[1] or 0)}, "topics": topics, "days": list(reversed(days))}


def _session(row) -> dict:
    return {"session_id": row["id"], "status": row["status"], "started_at": row["started_at"],
            "finished_at": row["finished_at"], "total_questions": int(row["planned"]),
            **counts(row["answered"], row["correct"])}


SESSION_SELECT = """SELECT s.*,
                    (SELECT count(*) FROM quiz_session_questions WHERE session_id=s.id) AS planned,
                    count(a.id) AS answered,COALESCE(sum(a.is_correct),0) AS correct
                    FROM quiz_sessions s LEFT JOIN quiz_answers a ON a.session_id=s.id"""


def history(conn, actor: int, before=None) -> dict:
    before = positive_id(before, nullable=True)
    condition = " AND s.id<?" if before is not None else ""
    params = (actor, before, PAGE_SIZE + 1) if before is not None else (actor, PAGE_SIZE + 1)
    rows = conn.execute(f"""{SESSION_SELECT} WHERE s.user_id=?{condition}
                            GROUP BY s.id ORDER BY s.id DESC LIMIT ?""", params).fetchall()
    return {"ok": True, "items": [_session(row) for row in rows[:PAGE_SIZE]],
            "next_before": rows[PAGE_SIZE - 1]["id"] if len(rows) > PAGE_SIZE else None}


def answer_detail(conn, row) -> dict:
    content = get_attempt_content(conn, row["session_id"], row["question_id"])
    if content is None:
        raise ValueError("Missing attempt edition")
    selected = next((opt["option_text"] for opt in content["options"]
                     if opt["option_index"] == row["selected_option_index"]), None)
    correct = next((opt["option_text"] for opt in content["options"] if opt["is_correct"]), None)
    return {"answer_id": row["id"], "question_id": row["question_id"], "session_id": row["session_id"],
            "answered_at": row["answered_at"], "is_correct": bool(row["is_correct"]),
            "question_text": content["question_text"], "topic": content["category"],
            "selected_option_text": selected, "correct_option_text": correct,
            "explanation": content["explanation"], "snapshot_provenance": content["snapshot_provenance"],
            "content_sha256": content["content_sha256"]}


def attempt(conn, actor: int, session_id, after=None) -> dict:
    session_id, after = positive_id(session_id), positive_id(after, nullable=True)
    row = conn.execute(f"{SESSION_SELECT} WHERE s.user_id=? AND s.id=? GROUP BY s.id", (actor, session_id)).fetchone()
    if row is None:
        # The same response for a missing ID and another user's attempt.
        raise ProgressError("attempt_not_found", 404)
    rows = conn.execute("""SELECT a.*,sq.order_index FROM quiz_answers a
        JOIN quiz_session_questions sq ON sq.session_id=a.session_id AND sq.question_id=a.question_id
        WHERE a.session_id=? AND sq.order_index>? ORDER BY sq.order_index LIMIT ?""",
        (session_id, after or 0, PAGE_SIZE + 1)).fetchall()
    return {"ok": True, "attempt": _session(row),
            "items": [answer_detail(conn, item) for item in rows[:PAGE_SIZE]],
            "next_after": rows[PAGE_SIZE - 1]["order_index"] if len(rows) > PAGE_SIZE else None}


def _mistakes(conn, actor: int):
    # Identity is (question, immutable edition, provenance). Backfilled content
    # cannot prove that a legacy correct answer resolved a captured edition.
    rows = conn.execute("""WITH ranked AS (
        SELECT a.*,sq.content_sha256,sq.snapshot_provenance,q.status AS question_status,
               row_number() OVER (PARTITION BY a.question_id,sq.content_sha256,sq.snapshot_provenance
                                  ORDER BY a.id DESC) AS pos
        FROM quiz_sessions s JOIN quiz_answers a ON a.session_id=s.id
        JOIN quiz_session_questions sq ON sq.session_id=a.session_id AND sq.question_id=a.question_id
        JOIN questions q ON q.id=a.question_id WHERE s.user_id=?
    ) SELECT * FROM ranked WHERE pos=1 ORDER BY id DESC""", (actor,)).fetchall()
    current = {}
    recorded = {(row["question_id"], row["content_sha256"]): bool(row["is_correct"])
                for row in rows if row["snapshot_provenance"] == "captured"}
    mistakes, trainable = [], set()
    for row in rows:
        if row["is_correct"]:
            continue
        qid = row["question_id"]
        if qid not in current:
            current[qid] = capture_question(conn, qid)[1] if row["question_status"] == "approved" else None
        edition = current[qid]
        can_train = edition is not None and recorded.get((qid, edition)) is not True
        if can_train:
            trainable.add(qid)
        state = "retired" if edition is None else "current" if edition == row["content_sha256"] else "changed"
        mistakes.append((row, {"edition_state": state, "trainable": can_train}))
    return mistakes, trainable


def errors(conn, actor: int, before=None) -> dict:
    before = positive_id(before, nullable=True)
    # Keep live-bank eligibility consistent with snapshot capture/content sync.
    begin_write(conn, "content")
    mistakes, trainable = _mistakes(conn, actor)
    page = [(row, flags) for row, flags in mistakes if before is None or row["id"] < before][:PAGE_SIZE + 1]
    latest = conn.execute("SELECT id,status FROM quiz_sessions WHERE user_id=? ORDER BY id DESC LIMIT 1", (actor,)).fetchone()
    return {"ok": True, "items": [{**answer_detail(conn, row), **flags} for row, flags in page[:PAGE_SIZE]],
            "total": len(mistakes), "trainable_count": len(trainable),
            "next_before": page[PAGE_SIZE - 1][0]["id"] if len(page) > PAGE_SIZE else None,
            "latest_session_id": latest["id"] if latest else None,
            "has_active_attempt": bool(latest and latest["status"] == "in_progress")}


def train_errors(conn, actor: int, payload: dict) -> dict:
    if "expected_session_id" not in payload or type(payload.get("replace_active")) is not bool:
        raise ProgressError("invalid_payload")
    expected = positive_id(payload["expected_session_id"], nullable=True)
    count = payload.get("question_count")
    if count is not None and (type(count) is not int or count not in (5, 10, 15)):
        raise ProgressError("invalid_payload")
    begin_write(conn, f"actor:{actor}")
    latest = conn.execute("SELECT id,status FROM quiz_sessions WHERE user_id=? ORDER BY id DESC LIMIT 1", (actor,)).fetchone()
    if (latest["id"] if latest else None) != expected:
        # A replay, another client or a lost reply cannot create a second attempt.
        raise ProgressError("practice_changed", 409)
    if latest and latest["status"] == "in_progress" and not payload["replace_active"]:
        raise ProgressError("active_attempt", 409)
    begin_write(conn, "content")
    _, trainable = _mistakes(conn, actor)
    questions = sorted(trainable)
    if not questions:
        raise ProgressError("no_errors", 409)
    random.shuffle(questions)
    if count is not None:
        questions = questions[:count]
    prepared = PreparedQuiz(None, (), None, tuple(questions))
    return {"ok": True, "runner_state": start_prepared_quiz(conn, actor_user_id=actor, prepared=prepared)}
