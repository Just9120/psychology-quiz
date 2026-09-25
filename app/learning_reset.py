"""Explicit, actor-scoped quiz/glossary reset; caller owns the transaction.

Preview fingerprints the current practice, including unanswered attempts. An
answer/setup/reset serialized on the same actor invalidates that confirmation.
Only learning rows are removed: the bank, identity and literature are untouched.
"""
from collections import defaultdict
import hashlib
import hmac
import json
import re

from app.database import begin_write, timestamp_sql
from app.progress_service import ProgressError


def _glossary_topics(row):
    snapshot = json.loads(row['snapshot'])
    cleared = set(json.loads(row['state']).get('cleared_topics', []))
    titles = snapshot.get('topic_titles', {})
    return {titles.get(item['entry']['topic_id'], row['topic_title'])
            for item in snapshot['questions'] if item['entry']['topic_id'] not in cleared}


def _glossary_steps(row, topic):
    snapshot = json.loads(row['snapshot'])
    state = json.loads(row['state'])
    titles = snapshot.get('topic_titles', {})
    return {str(step) for step, item in enumerate(snapshot['questions'], 1)
            if titles.get(item['entry']['topic_id'], row['topic_title']) == topic
            and item['entry']['topic_id'] not in state.get('cleared_topics', [])}


def _scope(payload):
    mode, topic = payload.get("scope"), payload.get("topic")
    if mode not in ("all", "topic") or (mode == "all" and topic is not None):
        raise ProgressError("invalid_reset_scope")
    if mode == "topic" and (not isinstance(topic, str) or not topic or len(topic) > 500):
        raise ProgressError("invalid_reset_scope")
    return mode, topic


def _read(conn, actor, payload):
    mode, topic = _scope(payload)
    begin_write(conn, f"actor:{actor}")
    sessions = conn.execute("SELECT * FROM quiz_sessions WHERE user_id=? ORDER BY id", (actor,)).fetchall()
    questions = conn.execute("""SELECT sq.* FROM quiz_session_questions sq
        JOIN quiz_sessions s ON s.id=sq.session_id WHERE s.user_id=? ORDER BY sq.id""", (actor,)).fetchall()
    answers = conn.execute("""SELECT a.* FROM quiz_answers a
        JOIN quiz_sessions s ON s.id=a.session_id WHERE s.user_id=? ORDER BY a.id""", (actor,)).fetchall()
    topics = {row["id"]: json.loads(row["content_snapshot"])["category"] for row in questions}
    glossary = conn.execute('SELECT * FROM glossary_sessions WHERE user_id=? ORDER BY id', (actor,)).fetchall()
    available = sorted(set(topics.values()) | {title for row in glossary for title in _glossary_topics(row)})
    if mode == "topic" and topic not in available:
        raise ProgressError("reset_changed", 409)
    selected = [row for row in questions if mode == "all" or topics[row["id"]] == topic]
    pairs = {(row["session_id"], row["question_id"]) for row in selected}
    affected = {row["session_id"] for row in selected} if mode == "topic" else {row["id"] for row in sessions}
    selected_glossary = [row for row in glossary if mode == 'all' or topic in _glossary_topics(row)]
    state = [actor, mode, topic, *[[list(row) for row in rows] for rows in (sessions, questions, answers, glossary)]]
    revision = hashlib.sha256(json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    preview = {"ok": True, "scope": mode, "topic": topic, "topics": available,
               "revision": revision, "questions": len(selected),
               "answers": sum((row["session_id"], row["question_id"]) in pairs for row in answers),
               "attempts": len(affected) + len(selected_glossary),
               "glossary_attempts": len(selected_glossary),
               "glossary_answers": sum(len(json.loads(row['state'])['answers']) if mode == 'all'
                   else len(_glossary_steps(row, topic) & set(json.loads(row['state'])['answers']))
                   for row in selected_glossary),
               "active_attempts": sum(row["id"] in affected and row["status"] == "in_progress" for row in sessions)
                   + sum(row['status'] == 'in_progress' for row in selected_glossary)}
    return preview, selected, affected


def preview(conn, actor, payload):
    return _read(conn, actor, payload)[0]


def confirm(conn, actor, payload):
    revision = payload.get("expected_revision")
    if payload.get("confirm") is not True or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
        raise ProgressError("reset_confirmation_required")
    current, selected, affected = _read(conn, actor, payload)
    if not hmac.compare_digest(current["revision"], revision):
        raise ProgressError("reset_changed", 409)
    if not current['attempts']:
        raise ProgressError("nothing_to_reset", 409)
    if current["scope"] == "all":
        # FK cascades are restricted to this actor's learning attempts.
        conn.execute("DELETE FROM user_achievements WHERE user_id=?", (actor,))
        conn.execute("DELETE FROM user_review_events WHERE user_id=?", (actor,))
        conn.execute("DELETE FROM user_review_sessions WHERE user_id=?", (actor,))
        conn.execute("DELETE FROM quiz_sessions WHERE user_id=?", (actor,))
        conn.execute('DELETE FROM glossary_sessions WHERE user_id=?', (actor,))
    else:
        # Awards are evidence-derived. Reconcile them from surviving attempts
        # on the next read instead of keeping awards for deliberately erased work.
        conn.execute("DELETE FROM user_achievements WHERE user_id=?", (actor,))
        selected_pairs = {(row["session_id"], row["question_id"]) for row in selected}
        for answer_id, session_id, question_id in conn.execute("""SELECT a.id,a.session_id,a.question_id
            FROM quiz_answers a JOIN quiz_sessions s ON s.id=a.session_id WHERE s.user_id=?""", (actor,)):
            if (session_id, question_id) in selected_pairs:
                conn.execute("""DELETE FROM user_review_events WHERE user_id=?
                    AND answer_kind='quiz' AND answer_key=?""", (actor, str(answer_id)))
        for session_id in affected:
            conn.execute("""DELETE FROM user_review_sessions WHERE user_id=?
                AND session_kind='quiz' AND session_key=?""", (actor, str(session_id)))
        for row in conn.execute("SELECT * FROM glossary_sessions WHERE user_id=?", (actor,)).fetchall():
            steps = _glossary_steps(row, current['topic'])
            if not steps:
                continue
            session_id = row['id']
            for step in steps:
                conn.execute("""DELETE FROM user_review_events WHERE user_id=? AND answer_kind='glossary'
                    AND answer_key=?""", (actor, f'{session_id}:{step}'))
            conn.execute("""DELETE FROM user_review_sessions WHERE user_id=?
                AND session_kind='glossary' AND session_key=?""", (actor, session_id))
            snapshot, state = json.loads(row['snapshot']), json.loads(row['state'])
            removed_ids = {snapshot['questions'][int(step) - 1]['entry']['topic_id'] for step in steps}
            cleared_ids = set(state.get('cleared_topics', [])) | removed_ids
            if all(item['entry']['topic_id'] in cleared_ids for item in snapshot['questions']):
                conn.execute('DELETE FROM glossary_sessions WHERE id=? AND user_id=?', (session_id, actor))
                continue
            for step in steps:
                state['answers'].pop(step, None)
            state['advances'] = {}
            state['score'] = sum(bool(answer['response']['feedback']['is_correct'])
                                 for answer in state['answers'].values())
            state['cleared_topics'] = sorted(cleared_ids)
            # Keep surviving history for review/mastery, but reject delayed
            # operations against the original mixed attempt after a reset.
            conn.execute("""UPDATE glossary_sessions SET state=?,status='abandoned'
                WHERE id=? AND user_id=?""", (json.dumps(state, ensure_ascii=False), session_id, actor))
        by_session = defaultdict(list)
        for row in selected:
            by_session[row["session_id"]].append(row["question_id"])
        for sid, question_ids in by_session.items():
            for offset in range(0, len(question_ids), 400):
                chunk = question_ids[offset:offset + 400]
                condition = "session_id=? AND question_id IN (" + ",".join("?" for _ in chunk) + ")"
                conn.execute("DELETE FROM quiz_answers WHERE " + condition, (sid, *chunk))
                conn.execute("DELETE FROM quiz_session_questions WHERE " + condition, (sid, *chunk))
            remaining = conn.execute("SELECT count(*) FROM quiz_session_questions WHERE session_id=?", (sid,)).fetchone()[0]
            if not remaining:
                conn.execute("DELETE FROM quiz_sessions WHERE id=? AND user_id=?", (sid, actor))
                continue
            # Other topics retain original snapshots/answers and ordering. A
            # partially cleared active attempt cannot accept a delayed answer.
            conn.execute(f"""UPDATE quiz_sessions SET total_questions=?,
                score=(SELECT COALESCE(sum(is_correct),0) FROM quiz_answers WHERE session_id=?),
                finished_at=CASE WHEN status='in_progress' THEN {timestamp_sql(conn)} ELSE finished_at END,
                status=CASE WHEN status='in_progress' THEN 'abandoned' ELSE status END
                WHERE id=? AND user_id=?""", (remaining, sid, sid, actor))
    return {"ok": True, "deleted_answers": current["answers"], "deleted_questions": current["questions"],
            "deleted_glossary_answers": current['glossary_answers']}
