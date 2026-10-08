"""Independent reading navigation; course provenance stays in the source catalog."""
import json
import re
from functools import lru_cache
from pathlib import Path

TOPICS_FILE = Path(__file__).resolve().parents[1] / "content/literature-topics.json"


@lru_cache(maxsize=1)
def load_reading_topics() -> tuple[list[dict], dict[str, list[str]]]:
    raw = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
    if set(raw) != {"schema_version", "topics", "works"} or raw["schema_version"] != 1:
        raise ValueError("Invalid reading topics catalog")
    topics, works = raw["topics"], raw["works"]
    if not isinstance(topics, list) or not isinstance(works, dict):
        raise ValueError("Invalid reading topics catalog")
    ids = set()
    for topic in topics:
        if (not isinstance(topic, dict) or set(topic) != {"id", "title"}
                or not isinstance(topic["id"], str) or not re.fullmatch(r"reading_[a-z_]+", topic["id"])
                or topic["id"] in ids or not isinstance(topic["title"], str) or not topic["title"].strip()):
            raise ValueError("Invalid reading topic")
        ids.add(topic["id"])
    for work, links in works.items():
        if (not isinstance(work, str) or not work or not isinstance(links, list) or not links
                or any(not isinstance(link, str) or link not in ids for link in links)
                or len(set(links)) != len(links)):
            raise ValueError("Invalid reading work topics")
    return topics, works


def reading_topics_for(work_id: str) -> list[dict]:
    topics, works = load_reading_topics()
    if work_id not in works:
        raise ValueError("Published work has no reading topic")
    selected = set(works[work_id])
    return [dict(topic) for topic in topics if topic["id"] in selected]
