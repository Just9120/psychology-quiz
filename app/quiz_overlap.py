"""Reviewed conceptual-overlap hints for diverse, finite quiz selection.

The groups do not retire questions or alter the meaning of captured attempts.
When unique concepts cannot fill a requested count, defer to the established
count contract and include postponed items. An explicit `all` includes every
approved ID; editorial consolidation remains a separate review decision.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path


GROUPS_PATH = Path(__file__).resolve().parents[1] / "content/quiz-overlap-groups.json"


@lru_cache(maxsize=1)
def memberships() -> dict[str, frozenset[int]]:
    data = json.loads(GROUPS_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("groups"), list):
        raise ValueError("Invalid quiz overlap catalog")
    result: dict[str, set[int]] = {}
    for number, group in enumerate(data["groups"]):
        ids = group.get("question_ids") if isinstance(group, dict) else None
        if (not isinstance(ids, list) or len(ids) < 2 or len(set(ids)) != len(ids)
                or any(not isinstance(item, str) or not item for item in ids)):
            raise ValueError("Invalid quiz overlap group")
        for external_id in ids:
            result.setdefault(external_id, set()).add(number)
    return {key: frozenset(value) for key, value in result.items()}


def diverse_first(candidates: list[tuple[int, str]], limit: int | None) -> list[int]:
    if limit is None:
        return [question_id for question_id, _ in candidates]
    by_id = memberships()
    selected: list[int] = []
    postponed: list[int] = []
    occupied: set[int] = set()
    for question_id, external_id in candidates:
        overlaps = by_id.get(external_id, frozenset())
        if overlaps & occupied:
            postponed.append(question_id)
        else:
            selected.append(question_id)
            occupied.update(overlaps)
        if len(selected) >= limit:
            break
    return (selected + postponed)[:limit]


def balanced_diverse_first(buckets: dict[int, list[tuple[int, str]]],
                           order: list[int], limit: int | None) -> list[int]:
    """Deal distinct concepts by topic before filling unavoidable overlap.

    Each topic gets one turn per round. An overlapping item is deferred within
    its topic so that a later distinct item from the same topic is not hidden
    behind it. The explicit all-mode keeps every approved question.
    """
    remaining = {topic: list(buckets[topic]) for topic in order}
    if limit is None:
        result = []
        while any(remaining.values()):
            for topic in order:
                if remaining[topic]:
                    result.append(remaining[topic].pop()[0])
        return result

    selected: list[int] = []
    occupied: set[int] = set()
    by_id = memberships()
    while len(selected) < limit:
        progress = False
        for topic in order:
            candidates = remaining[topic]
            for index in range(len(candidates) - 1, -1, -1):
                question_id, external_id = candidates[index]
                overlap = by_id.get(external_id, frozenset())
                if overlap & occupied:
                    continue
                candidates.pop(index)
                selected.append(question_id)
                occupied.update(overlap)
                progress = True
                break
            if len(selected) == limit:
                return selected
        if not progress:
            break

    while len(selected) < limit and any(remaining.values()):
        for topic in order:
            if remaining[topic]:
                selected.append(remaining[topic].pop()[0])
            if len(selected) == limit:
                break
    return selected


def balanced_kinds_diverse_first(candidates: list[tuple[int, str, int, str]],
                                 topics: list[int], requested_kinds: list[str],
                                 limit: int) -> list[int]:
    """Balance a finite mixed quiz after filtering its requested content kinds.

    Reserve an available kind when there is room, then prefer distinct concepts
    in the least represented topic. Overlap is used only when no distinct item
    can fill the remaining count (or a requested kind otherwise disappears).
    """
    if limit < 1:
        return []
    by_id = memberships()
    remaining = list(candidates)
    counts = {topic: 0 for topic in topics}
    order = {topic: index for index, topic in enumerate(topics)}
    selected: list[int] = []
    occupied: set[int] = set()

    def take(index: int) -> None:
        question_id, external_id, topic, _ = remaining.pop(index)
        selected.append(question_id)
        counts[topic] += 1
        occupied.update(by_id.get(external_id, frozenset()))

    available_kinds = [kind for kind in requested_kinds
                       if any(item[3] == kind for item in remaining)]
    if limit >= len(available_kinds):
        for kind in available_kinds:
            options = [(index, item) for index, item in enumerate(remaining)
                       if item[3] == kind]
            if not options:
                continue
            # Reserve flexible topics for kinds unavailable elsewhere. With a
            # short quiz, taking the only kind from a narrow topic first can
            # keep both kind coverage and topic balance achievable.
            topic_kind_counts = {
                topic: len({item[3] for item in remaining
                            if item[2] == topic and item[3] in available_kinds})
                for topic in topics
            }
            index, _ = min(options, key=lambda pair: (
                bool(by_id.get(pair[1][1], frozenset()) & occupied),
                counts[pair[1][2]], topic_kind_counts[pair[1][2]],
                order[pair[1][2]], pair[0]))
            take(index)

    while remaining and len(selected) < limit:
        unique = [(index, item) for index, item in enumerate(remaining)
                  if not by_id.get(item[1], frozenset()) & occupied]
        options = unique or list(enumerate(remaining))
        index, _ = min(options, key=lambda pair: (
            counts[pair[1][2]], order[pair[1][2]], pair[0]))
        take(index)
    return selected
