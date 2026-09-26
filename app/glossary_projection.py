"""Stable quiz presentation of already published glossary entries.

This is a derived view of the approved glossary, not an independent source of
learning facts. A failed source/publication lookup stops projection entirely.
"""
from dataclasses import asdict
import random

from app.content_publication import fingerprint
from app.glossary import GLOSSARY_TOPICS, build_glossary_quiz_question, load_glossary_entries


def projected_questions() -> list[dict]:
    questions = []
    for topic_id, title in GLOSSARY_TOPICS:
        entries = load_glossary_entries(topic_id)
        if not entries or len(entries) < 4:
            raise ValueError(f"Published glossary topic unavailable: {topic_id}")
        for entry in entries:
            if entry.topic_id != topic_id or not entry.source_refs:
                raise ValueError(f"Invalid published glossary entry: {topic_id}")
            # Published topic content fixes the choice layout at seed time.
            # Existing attempt snapshots retain their old options after reseed.
            rng = random.Random(fingerprint(asdict(entry)))
            choice = build_glossary_quiz_question(entries, entry, rng=rng)
            if choice is None:
                raise ValueError(f"Cannot build published glossary question: {topic_id}:{entry.id}")
            questions.append({
                "id": f"glossary:{topic_id}:{entry.id}",
                "category": title,
                "question": f"Что означает «{entry.term}»?",
                "options": list(choice.options),
                "correct_option_index": choice.correct_option_index,
                "explanation": entry.definition,
                "source_ref": entry.source_refs[0],
                "difficulty": entry.difficulty,
                "kind": "glossary",
                "status": "approved",
            })
    if len({item["id"] for item in questions}) != len(questions):
        raise ValueError("Duplicate published glossary question ID")
    return questions
