"""Private Drive metadata inventory; discovery never approves publication.

The caller supplies complete, paginated direct-child listings. A missing page
is an error, not an empty folder. Persist snapshots only in ignored private
operator storage, never among public content or static assets.
"""
from __future__ import annotations

from collections import Counter, deque
import re


class InventoryError(ValueError):
    pass


def complete_listing(pages: list[dict]) -> dict:
    """Join one folder's direct-child pages only when the token chain ends.

    A truncated page sequence must never be interpreted as a complete folder.
    Page tokens are connector cursors, not content identities or revisions.
    """
    if not isinstance(pages, list) or not pages:
        raise InventoryError("incomplete_folder_listing")
    expected, children, tokens, child_ids = None, [], set(), set()
    for index, page in enumerate(pages):
        if (not isinstance(page, dict) or page.get("page_token") != expected
                or not isinstance(page.get("children"), list)):
            raise InventoryError("invalid_page_chain")
        for child in page["children"]:
            child_id = child.get("id") if isinstance(child, dict) else None
            if not isinstance(child_id, str) or not child_id:
                raise InventoryError("invalid_child")
            if child_id in child_ids:
                raise InventoryError("duplicate_page_child")
            child_ids.add(child_id)
            children.append(child)
        token = page.get("next_page_token")
        if token is None:
            if index != len(pages) - 1:
                raise InventoryError("invalid_page_chain")
            return {"complete": True, "children": children}
        if not isinstance(token, str) or not token or token in tokens:
            raise InventoryError("invalid_page_chain")
        tokens.add(token)
        expected = token
    raise InventoryError("incomplete_folder_listing")


def _revision(item: dict) -> tuple[str, str, str]:
    return item["modified_time"], item["title"], item["mime_type"]


def scan(root_id: str, listings: dict[str, dict]) -> dict:
    if not isinstance(root_id, str) or not root_id:
        raise InventoryError("root_required")
    queue, seen_folders, files, paths = deque([(root_id, ())]), {}, {}, {}
    while queue:
        parent, breadcrumb = queue.popleft()
        if parent in seen_folders:
            if seen_folders[parent] != breadcrumb:
                raise InventoryError("ambiguous_folder_paths")
            continue
        listing = listings.get(parent)
        if not isinstance(listing, dict) or listing.get("complete") is not True:
            raise InventoryError("incomplete_folder_listing")
        children = listing.get("children")
        if not isinstance(children, list):
            raise InventoryError("invalid_folder_listing")
        seen_folders[parent] = breadcrumb
        for item in children:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                raise InventoryError("invalid_child")
            parents = item.get("parent_ids")
            if not isinstance(parents, list) or parent not in parents:
                raise InventoryError("parent_mismatch")
            if item.get("file_or_folder") == "folder":
                if not isinstance(item.get("title"), str) or not item["title"]:
                    raise InventoryError("incomplete_folder_metadata")
                queue.append((item["id"], (*breadcrumb, item["title"])))
                continue
            if item.get("file_or_folder") != "file":
                raise InventoryError("unknown_child_kind")
            if any(not isinstance(item.get(key), str) or not item[key]
                   for key in ("title", "mime_type", "modified_time")):
                raise InventoryError("incomplete_file_metadata")
            previous = files.get(item["id"])
            if previous is not None and _revision(previous) != _revision(item):
                raise InventoryError("conflicting_file_metadata")
            files[item["id"]] = {key: item[key] for key in
                                  ("id", "title", "mime_type", "modified_time")}
            paths.setdefault(item["id"], set()).add((*breadcrumb, item["title"]))
    return {"root_id": root_id, "folders": len(seen_folders), "files": files,
            "paths": {file_id: [list(path) for path in sorted(found)]
                      for file_id, found in paths.items()}}


def reconcile(previous: dict, current: dict) -> dict:
    if previous.get("root_id") != current.get("root_id"):
        raise InventoryError("root_changed")
    old, new = previous["files"], current["files"]
    changes = {"new": [], "changed": [], "relocated": [], "unchanged": [], "missing": []}
    for file_id, item in new.items():
        if file_id not in old:
            changes["new"].append(file_id)
        elif _revision(old[file_id]) != _revision(item):
            changes["changed"].append(file_id)
        elif previous["paths"].get(file_id) != current["paths"].get(file_id):
            changes["relocated"].append(file_id)
        else:
            changes["unchanged"].append(file_id)
    changes["missing"] = sorted(old.keys() - new.keys())
    return {name: sorted(ids) for name, ids in changes.items()}


def processing_status(snapshot: dict, processed: dict[str, dict]) -> dict[str, str]:
    """Discovery and successful content processing are different records."""
    result = {}
    for file_id, item in snapshot["files"].items():
        record = processed.get(file_id)
        if record is None:
            result[file_id] = "new_unprocessed"
        elif not isinstance(record, dict):
            raise InventoryError("invalid_processing_record")
        else:
            revision = record.get("revision")
            state = record.get("review_state")
            if (not isinstance(revision, (list, tuple)) or len(revision) != 3
                    or any(not isinstance(value, str) or not value for value in revision)
                    or not isinstance(state, str)
                    or state not in {"pending_review", "conflict", "processed"}):
                raise InventoryError("invalid_processing_record")
            if state == "processed" and (
                    not isinstance(record.get("snapshot_kind"), str)
                    or record["snapshot_kind"] not in {"file_bytes", "extracted_text"}
                    or not isinstance(record.get("snapshot_sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", record["snapshot_sha256"]) is None):
                raise InventoryError("unverified_processing_record")
            if state == "conflict" and (not isinstance(record.get("reason"), str)
                                         or not record["reason"].strip()):
                raise InventoryError("invalid_processing_record")
            if tuple(revision) != _revision(item):
                result[file_id] = "changed_unprocessed"
            elif state == "conflict":
                result[file_id] = "conflict_review"
            elif state == "processed":
                result[file_id] = "processed"
            else:
                result[file_id] = "pending_review"
    return result


def link_lessons(snapshot: dict, links: list[dict]) -> dict:
    """Group formats only by explicit editor-confirmed lesson IDs."""
    lessons, seen = {}, set()
    for link in links:
        if not isinstance(link, dict):
            raise InventoryError("invalid_lesson_link")
        source_id, lesson_id, topic_id, format_name = (
            link.get(key) for key in ("source_id", "lesson_id", "topic_id", "format"))
        if (not isinstance(source_id, str) or source_id not in snapshot["files"] or any(
                not isinstance(value, str) or not value.strip()
                for value in (lesson_id, topic_id, format_name))):
            raise InventoryError("invalid_lesson_link")
        key = (source_id, lesson_id, format_name)
        if key in seen:
            raise InventoryError("duplicate_lesson_link")
        seen.add(key)
        lesson = lessons.setdefault(lesson_id, {"topic_id": topic_id, "sources": []})
        if lesson["topic_id"] != topic_id:
            raise InventoryError("conflicting_lesson_topic")
        lesson["sources"].append({"source_id": source_id, "format": format_name})
    return lessons


def reviewed_graph(snapshot: dict, registry: dict, curriculum: dict) -> dict:
    """Aggregate exact metadata and reviewed lesson edges without exposing sources.

    A current Drive timestamp/title does not prove that a source was fully read;
    snapshot hashes belong to the separate content review record. A stale or
    missing Drive file cannot support a *current* lesson edge.
    """
    if (not isinstance(registry, dict) or registry.get("schema_version") != 1
            or registry.get("corpus_root_id") != snapshot.get("root_id")
            or not isinstance(registry.get("sources"), list)
            or not isinstance(curriculum, dict) or curriculum.get("schema_version") != 1
            or not isinstance(curriculum.get("topics"), dict)
            or not isinstance(curriculum.get("disciplines"), dict)):
        raise InventoryError("invalid_reviewed_graph")
    sources = {}
    for source in registry["sources"]:
        if (not isinstance(source, dict) or not isinstance(source.get("id"), str)
                or not source["id"] or source["id"] in sources
                or source.get("kind") not in {"learning_material", "bibliography"}
                or source.get("readable") is not True
                or source.get("snapshot_kind") not in {"file_bytes", "extracted_text"}
                or not isinstance(source.get("corpus_path"), str) or not source["corpus_path"]
                or not all(isinstance(source.get(key), str) and source[key]
                           for key in ("title", "modified_time", "snapshot_sha256", "reviewed_at", "reviewer"))
                or re.fullmatch(r"[0-9a-f]{64}", source["snapshot_sha256"]) is None):
            raise InventoryError("invalid_reviewed_source")
        sources[source["id"]] = source
    states = {}
    formats = Counter()
    for source_id, source in sources.items():
        live = snapshot["files"].get(source_id)
        state = ("missing" if live is None else "changed" if
                 (source["title"], source["modified_time"]) !=
                 (live["title"], live["modified_time"]) else "relocated" if
                 source["corpus_path"] not in
                 ("/".join(path) for path in snapshot["paths"][source_id]) else "current")
        states[source_id] = state
        if state == "current":
            formats[live["mime_type"]] += 1
    linked_ids = Counter()
    link_states = Counter()
    for topic in curriculum["topics"].values():
        if (not isinstance(topic, dict) or topic.get("discipline_id") not in curriculum["disciplines"]
                or not isinstance(topic.get("title"), str) or not topic["title"]
                or not isinstance(topic.get("source"), dict)):
            raise InventoryError("invalid_reviewed_lesson")
        ref = topic["source"]
        source = sources.get(ref.get("source_id"))
        if (source is None or source["kind"] != "learning_material"
                or ref.get("modified_time") != source["modified_time"]
                or ref.get("snapshot_sha256") != source["snapshot_sha256"]):
            raise InventoryError("invalid_reviewed_lesson")
        linked_ids[source["id"]] += 1
        link_states[states[source["id"]]] += 1
    return {
        "tracked_sources": len(sources),
        "source_kinds": dict(sorted(Counter(source["kind"] for source in sources.values()).items())),
        "source_metadata": dict(sorted(Counter(states.values()).items())),
        "current_by_format": dict(sorted(formats.items())),
        "untracked_inventory_files": len(snapshot["files"]) - sum(state != "missing" for state in states.values()),
        "reviewed_lesson_edges": len(curriculum["topics"]),
        "lesson_metadata": dict(sorted(link_states.items())),
        "unique_lesson_files": len(linked_ids),
        "multi_lesson_files": sum(count > 1 for count in linked_ids.values()),
        "reviewed_learning_without_lesson": sum(source["kind"] == "learning_material" and
                                                source["id"] not in linked_ids for source in sources.values()),
    }


def private_review_queue(snapshot: dict, registry: dict, curriculum: dict, *,
                         processed: dict | None = None, previous: dict | None = None,
                         reviews: dict | None = None,
                         quality_reviews: dict | None = None) -> dict:
    """Operator-only file-level queue; never return this from a public route."""
    reviewed_graph(snapshot, registry, curriculum)
    if processed is not None and not isinstance(processed, dict):
        raise InventoryError("invalid_processing_records")
    sources = {source["id"]: source for source in registry["sources"]}
    derivatives: dict[str, set[str]] = {}
    stale_derivatives: dict[str, set[str]] = {}
    quality_items: dict[str, set[str]] = {}
    quality_priority: dict[str, set[str]] = {}
    if quality_reviews is not None:
        if (not isinstance(quality_reviews, dict)
                or quality_reviews.get("schema_version") != 1
                or not isinstance(quality_reviews.get("items"), dict)):
            raise InventoryError("invalid_quality_reviews")
        for derivative_id, review in quality_reviews["items"].items():
            if (not isinstance(derivative_id, str) or not derivative_id
                    or not isinstance(review, dict)
                    or not isinstance(review.get("source_support"), str)
                    or not isinstance(review.get("sources"), list)
                    or not review["sources"]):
                raise InventoryError("invalid_quality_review")
            for ref in review["sources"]:
                source_id = ref.get("source_id") if isinstance(ref, dict) else None
                if not isinstance(source_id, str) or source_id not in sources:
                    raise InventoryError("invalid_quality_review_source")
                quality_items.setdefault(source_id, set()).add(derivative_id)
                source = sources[source_id]
                if (review["source_support"] != "supported"
                        or ref.get("modified_time") != source["modified_time"]
                        or ref.get("snapshot_sha256") != source["snapshot_sha256"]):
                    quality_priority.setdefault(source_id, set()).add(derivative_id)
    if reviews is not None:
        if (not isinstance(reviews, dict) or reviews.get("schema_version") != 1
                or not isinstance(reviews.get("items"), dict)):
            raise InventoryError("invalid_derivative_reviews")
        for derivative_id, review in reviews["items"].items():
            if (not isinstance(derivative_id, str) or not derivative_id
                    or not isinstance(review, dict)):
                raise InventoryError("invalid_derivative_review")
            if review.get("decision") != "approved":
                continue
            if not isinstance(review.get("sources"), list) or not review["sources"]:
                raise InventoryError("invalid_derivative_review")
            for ref in review["sources"]:
                source_id = ref.get("source_id") if isinstance(ref, dict) else None
                if not isinstance(source_id, str) or source_id not in sources:
                    raise InventoryError("invalid_derivative_source")
                derivatives.setdefault(source_id, set()).add(derivative_id)
                source = sources[source_id]
                if (ref.get("modified_time") != source["modified_time"]
                        or ref.get("snapshot_sha256") != source["snapshot_sha256"]):
                    stale_derivatives.setdefault(source_id, set()).add(derivative_id)
    topics = {}
    for topic_id, topic in curriculum["topics"].items():
        topics.setdefault(topic["source"]["source_id"], []).append(topic_id)
    processing = processing_status(snapshot, processed) if processed is not None else None
    changes = reconcile(previous, snapshot) if previous is not None else None
    changed = ({file_id: name for name, ids in changes.items() for file_id in ids}
               if changes is not None else {})
    entries = []
    for file_id, item in snapshot["files"].items():
        source = sources.get(file_id)
        registry_state = ("untracked" if source is None else "changed" if
                          (source["title"], source["modified_time"]) !=
                          (item["title"], item["modified_time"]) else "relocated" if
                          source["corpus_path"] not in
                          ("/".join(path) for path in snapshot["paths"][file_id]) else "current")
        linked_derivatives = derivatives.get(file_id, set())
        explicit_review_problem = (processing is not None and processing[file_id] in
                                   {"pending_review", "conflict_review", "changed_unprocessed"})
        priority_quality = (quality_items.get(file_id, set()) if
                            registry_state in {"changed", "relocated"} or explicit_review_problem
                            else quality_priority.get(file_id, set()))
        affected_derivatives = (linked_derivatives if registry_state in {"changed", "relocated"}
                                or explicit_review_problem
                                else stale_derivatives.get(file_id, set()))
        entries.append({
            "file_id": file_id,
            "title": item["title"],
            "mime_type": item["mime_type"],
            "modified_time": item["modified_time"],
            "paths": snapshot["paths"][file_id],
            "registry_state": registry_state,
            "inventory_change": changed.get(file_id, "unknown_no_previous_snapshot"),
            "processing_state": processing[file_id] if processing is not None
                                else "unknown_no_processing_snapshot",
            "linked_topic_ids": sorted(topics.get(file_id, [])),
            "linked_derivative_ids": sorted(linked_derivatives),
            "derivative_ids_requiring_review": sorted(affected_derivatives),
            "derivative_review_required": bool(affected_derivatives),
            "quality_review_item_ids": sorted(quality_items.get(file_id, set())),
            "quality_review_priority_ids": sorted(priority_quality),
        })
    entries.sort(key=lambda item: (item["paths"], item["file_id"]))
    missing = [{"file_id": file_id, "title": source["title"],
                "linked_topic_ids": sorted(topics.get(file_id, [])),
                "linked_derivative_ids": sorted(derivatives.get(file_id, set())),
                "derivative_ids_requiring_review": sorted(derivatives.get(file_id, set())),
                "derivative_review_required": bool(derivatives.get(file_id)),
                "quality_review_item_ids": sorted(quality_items.get(file_id, set())),
                "quality_review_priority_ids": sorted(quality_items.get(file_id, set()))}
               for file_id, source in sorted(sources.items()) if file_id not in snapshot["files"]]
    # An unreviewed file can disappear before it reaches the canonical registry.
    # Keep its last-seen metadata in the private queue so a missing listing is
    # investigated rather than silently dropping that source from review.
    missing_untracked = []
    if previous is not None:
        prior_processing = processing_status(previous, processed) if processed is not None else None
        for file_id in changes["missing"]:
            if file_id in sources:
                continue  # Already represented in missing_tracked_sources.
            item = previous["files"][file_id]
            missing_untracked.append({
                "file_id": file_id,
                "title": item["title"],
                "mime_type": item["mime_type"],
                "modified_time": item["modified_time"],
                "last_seen_paths": previous["paths"][file_id],
                "inventory_change": "missing",
                "processing_state": "unknown_no_processing_snapshot" if prior_processing is None
                                    else "previously_" + prior_processing[file_id],
                "review_action": "verify_access_or_removal",
            })
    return {"schema_version": 1, "root_id": snapshot["root_id"],
            "files": entries, "missing_tracked_sources": missing,
            "missing_untracked_files": missing_untracked}
