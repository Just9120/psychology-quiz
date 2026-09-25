"""Reviewed curriculum identities; historical answers are never rewritten.

Only captured editions with an explicit mapping acquire a nested topic. A
current question ID or a backfilled snapshot is insufficient evidence.
"""
from functools import lru_cache
import json
from pathlib import Path
import re

from app.database import is_postgres

ROOT = Path(__file__).resolve().parents[1]
UNMAPPED = "unmapped"


def validate_catalog(data):
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Invalid curriculum schema")
    disciplines, topics, editions = (data.get(key) for key in ("disciplines", "topics", "editions"))
    if not all(isinstance(part, dict) for part in (disciplines, topics, editions)):
        raise ValueError("Invalid curriculum records")
    for key, item in disciplines.items():
        if not re.fullmatch(r"[a-z0-9_]+", key) or not isinstance(item.get("title"), str) or not item["title"]:
            raise ValueError("Invalid discipline")
    if len({x["title"] for x in disciplines.values()}) != len(disciplines):
        raise ValueError("Ambiguous discipline title")
    for key, item in topics.items():
        if (not re.fullmatch(r"t_[a-f0-9]{12}", key) or item.get("discipline_id") not in disciplines
                or not isinstance(item.get("title"), str) or not item["title"]):
            raise ValueError("Invalid curriculum topic")
        source = item.get("source", {})
        if not all(isinstance(source.get(k), str) and source[k] for k in ("source_id", "modified_time", "snapshot_sha256")):
            raise ValueError("Missing curriculum source")
    for digest, item in editions.items():
        if (not re.fullmatch(r"[a-f0-9]{64}", digest) or item.get("topic_id") not in topics
                or not all(isinstance(item.get(k), str) and item[k] for k in ("external_id", "item_sha256", "locator"))):
            raise ValueError("Invalid curriculum edition")
    return data


@lru_cache(maxsize=1)
def load_catalog():
    return validate_catalog(json.loads((ROOT / "content/curriculum.json").read_text(encoding="utf-8")))


def scopes():
    catalog = load_catalog()
    return {UNMAPPED, *["discipline:" + x for x in catalog["disciplines"]],
            *["topic:" + x for x in catalog["topics"]]}


def scope_condition(scope, alias="e"):
    if scope is None:
        return "1=1", ()
    if not isinstance(scope, str) or scope not in scopes():
        raise ValueError("invalid_curriculum_scope")
    if scope == UNMAPPED:
        return f"{alias}.topic_id IS NULL", ()
    kind, key = scope.split(":", 1)
    return f"{alias}.{kind}_id=?", (key,)


def evidence_cte(conn, actor):
    catalog = load_catalog()
    # JSON parameters avoid SQL variable limits as the reviewed bank grows.
    disciplines = json.dumps([[k, v["title"]] for k, v in catalog["disciplines"].items()])
    editions = json.dumps([[k, v["topic_id"], catalog["topics"][v["topic_id"]]["discipline_id"]]
                           for k, v in catalog["editions"].items()])
    if is_postgres(conn):
        disc = "SELECT value->>0 AS discipline_id,value->>1 AS title FROM jsonb_array_elements(?::jsonb)"
        mapped = "SELECT value->>0 AS sha,value->>1 AS topic_id,value->>2 AS discipline_id FROM jsonb_array_elements(?::jsonb)"
        category = "sq.content_snapshot::jsonb->>'category'"
    else:
        disc = "SELECT json_extract(value,'$[0]') AS discipline_id,json_extract(value,'$[1]') AS title FROM json_each(?)"
        mapped = "SELECT json_extract(value,'$[0]') AS sha,json_extract(value,'$[1]') AS topic_id,json_extract(value,'$[2]') AS discipline_id FROM json_each(?)"
        category = "json_extract(sq.content_snapshot,'$.category')"
    sql = f"""WITH disciplines AS ({disc}), editions AS ({mapped}), evidence AS (
        SELECT a.id,a.session_id,a.is_correct,substr(a.answered_at,1,10) AS day,d.discipline_id,m.topic_id
        FROM quiz_sessions s JOIN quiz_answers a ON a.session_id=s.id
        JOIN quiz_session_questions sq ON sq.session_id=a.session_id AND sq.question_id=a.question_id
        LEFT JOIN disciplines d ON d.title={category} AND sq.snapshot_provenance='captured'
        LEFT JOIN editions m ON m.sha=sq.content_sha256 AND m.discipline_id=d.discipline_id
        WHERE s.user_id=?
    )"""
    return sql, (disciplines, editions, actor)


def classification(content):
    catalog = load_catalog()
    discipline = None
    if content["snapshot_provenance"] == "captured":
        discipline = next((key for key, value in catalog["disciplines"].items()
                           if value["title"] == content["category"]), None)
    edition = catalog["editions"].get(content["content_sha256"]) if discipline else None
    topic = catalog["topics"].get(edition["topic_id"]) if edition else None
    if topic and topic["discipline_id"] != discipline:
        topic = None
    return {"discipline_id": discipline, "discipline_title": catalog["disciplines"][discipline]["title"] if discipline else None,
            "topic_id": edition["topic_id"] if topic else None, "topic_title": topic["title"] if topic else None}


def overview(conn, actor):
    from app.progress_service import counts, DAY_COUNT

    catalog = load_catalog()
    cte, params = evidence_cte(conn, actor)
    cte += """, groups AS (
        SELECT 'discipline:' || discipline_id AS scope,day,is_correct FROM evidence WHERE discipline_id IS NOT NULL
        UNION ALL SELECT CASE WHEN topic_id IS NULL THEN 'unmapped' ELSE 'topic:' || topic_id END,day,is_correct FROM evidence
    )"""
    stats = {}
    for row in conn.execute(cte + " SELECT scope,count(*),sum(is_correct) FROM groups GROUP BY scope", params):
        stats[row[0]] = {**counts(row[1], row[2]), "days": []}
    for row in conn.execute(cte + """, daily AS (
        SELECT scope,day,count(*) AS answered,sum(is_correct) AS correct FROM groups GROUP BY scope,day
    ), ranked AS (SELECT *,row_number() OVER (PARTITION BY scope ORDER BY day DESC) AS pos FROM daily)
    SELECT scope,day,answered,correct FROM ranked WHERE pos<=? ORDER BY day""", (*params, DAY_COUNT)):
        stats[row[0]]["days"].append({"day": row[1], **counts(row[2], row[3])})

    def result(scope, title):
        return {"scope": scope, "title": title, **stats.get(scope, {**counts(0, 0), "days": []})}

    result_disciplines = []
    for key, value in catalog["disciplines"].items():
        topics = [result("topic:" + t, item["title"]) for t, item in catalog["topics"].items() if item["discipline_id"] == key]
        topics.sort(key=lambda x: (x["accuracy"] is None, x["accuracy"] or 0, -x["answered"], x["title"]))
        item = result("discipline:" + key, value["title"])
        item["topics"] = topics
        item["unmapped_answers"] = item["answered"] - sum(t["answered"] for t in topics)
        result_disciplines.append(item)
    return {"disciplines": result_disciplines, "unmapped": result(UNMAPPED, "Без подтверждённой темы")}
