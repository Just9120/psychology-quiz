"""Visible reading route built from reviewed metadata, never source-list position."""
STAGES = {"foundation": "Начать с основ", "core": "Основное чтение",
          "applied": "Применение", "deepening": "Углубление",
          "advanced": "Продвинутый уровень", "reference": "Справочные материалы"}
IMPORTANCE = {"basic": 0, "important": 1, "additional": 2, "advanced": 3}


def reading_order(items: list[dict], all_items: list[dict] | None = None) -> list[dict]:
    known = {item["id"]: item for item in (all_items if all_items is not None else items)}
    candidates = {}
    for item in items:
        refs = item.get("prerequisites")
        if (item.get("reading_level") not in STAGES or item.get("importance") not in IMPORTANCE
                or item.get("importance_source") not in {"agent", "teacher"}
                or not isinstance(item.get("why_read"), str) or not item["why_read"].strip()
                or not isinstance(refs, list)
                or any(not isinstance(ref, str) or ref not in known for ref in refs)):
            continue
        key = item.get("work_id", item["id"])
        candidates.setdefault(key, item)
    stages = list(STAGES)
    def rank(key):
        item = candidates[key]
        return (IMPORTANCE[item["importance"]], stages.index(item["reading_level"]), item["id"])
    dependencies = {key: {known[ref].get("work_id", ref) for ref in item["prerequisites"]}
                    for key, item in candidates.items()}
    remaining = set(candidates)
    result = []
    while remaining:
        ready = [key for key in remaining if not dependencies[key].intersection(remaining)]
        if not ready:
            break  # A cycle never becomes an invented recommendation.
        key = min(ready, key=rank)
        result.append({"item": candidates[key], "stage": STAGES[candidates[key]["reading_level"]],
                       "prerequisites": [known[ref] for ref in candidates[key]["prerequisites"]]})
        remaining.remove(key)
    return result
