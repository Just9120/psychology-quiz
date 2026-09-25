"""Read-only, actor-independent evidence for manual difficulty review.

Each captured question edition contributes at most its first saved answer per
learning actor. The report never returns actor identities or edits metadata.
"""
from __future__ import annotations

import hashlib
import json
from math import sqrt
from statistics import NormalDist

from app.attempt_content import capture_question


Z_95 = NormalDist().inv_cdf(0.975)


def wilson_error_interval(errors: int, sample_size: int) -> list[float] | None:
    """95% Wilson interval in percent; sampling bias is not measured here."""
    if sample_size == 0:
        return None
    z2 = Z_95 * Z_95
    rate = errors / sample_size
    denominator = 1 + z2 / sample_size
    center = (rate + z2 / (2 * sample_size)) / denominator
    margin = Z_95 * sqrt(rate * (1 - rate) / sample_size + z2 / (4 * sample_size**2)) / denominator
    return [round(100 * max(0.0, center - margin), 1),
            round(100 * min(1.0, center + margin), 1)]


def report(conn) -> dict:
    # All actor IDs remain inside SQL. Backfilled editions cannot prove what
    # the learner actually saw and therefore cannot calibrate difficulty.
    observed = conn.execute("""WITH ranked AS (
        SELECT a.question_id, sq.content_sha256, sq.content_snapshot, a.is_correct,
               row_number() OVER (
                   PARTITION BY s.user_id, a.question_id, sq.content_sha256
                   ORDER BY a.answered_at, a.id
               ) AS first_answer
        FROM quiz_answers a
        JOIN quiz_sessions s ON s.id=a.session_id
        JOIN quiz_session_questions sq
          ON sq.session_id=a.session_id AND sq.question_id=a.question_id
        WHERE sq.snapshot_provenance='captured'
    ) SELECT question_id, content_sha256, min(content_snapshot),
             count(*), sum(is_correct)
      FROM ranked WHERE first_answer=1
      GROUP BY question_id, content_sha256""").fetchall()
    editions = {}
    for question_id, digest, encoded, size, correct in observed:
        if not encoded or hashlib.sha256(encoded.encode()).hexdigest() != digest:
            raise ValueError("Captured attempt content is missing or corrupt")
        snapshot = json.loads(encoded)
        if snapshot.get("version") != 1:
            raise ValueError("Unsupported attempt content version")
        editions[(question_id, digest)] = (snapshot, int(size), int(correct or 0))

    current = set()
    for question_id, external_id in conn.execute(
        "SELECT id,external_id FROM questions WHERE status='approved' ORDER BY external_id"
    ):
        _, digest = capture_question(conn, question_id)
        current.add((question_id, digest))
        if (question_id, digest) not in editions:
            editions[(question_id, digest)] = ({"external_id": external_id}, 0, 0)

    items = []
    for key, (snapshot, size, correct) in editions.items():
        errors = size - correct
        items.append({
            "question_id": snapshot["external_id"],
            "edition_sha256": key[1],
            "current_approved_edition": key in current,
            "independent_answers": size,
            "errors": errors,
            "error_rate_pct": round(100 * errors / size, 1) if size else None,
            "error_rate_wilson95_pct": wilson_error_interval(errors, size),
        })
    items.sort(key=lambda item: (item["question_id"], not item["current_approved_edition"],
                                 item["edition_sha256"]))
    return {
        "method": "first_saved_answer_per_actor_and_captured_question_edition",
        "uncertainty": "95% Wilson interval for observed error proportion; not a representative-population estimate",
        "metadata_changed": False,
        "items": items,
    }
