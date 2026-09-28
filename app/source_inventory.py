"""Private Drive metadata inventory; discovery never approves publication.

The caller supplies complete, paginated direct-child listings. A missing page
is an error, not an empty folder. Persist snapshots only in ignored private
operator storage, never among public content or static assets.
"""
from __future__ import annotations

from collections import Counter, deque
from datetime import datetime
import re
import unicodedata

from app.source_evidence import locator_precision_review_required


class InventoryError(ValueError):
    pass


def combine_registries(public: dict, private: dict) -> dict:
    """Extend an operator review without replacing a public source record."""
    if (not isinstance(public, dict) or not isinstance(public.get("sources"), list)
            or not isinstance(private, dict)
            or set(private) != {"schema_version", "corpus_root_id", "sources"}
            or private["schema_version"] != 1
            or not isinstance(private["sources"], list)
            or private["corpus_root_id"] != public.get("corpus_root_id")):
        raise InventoryError("private_registry_root_mismatch")
    public_ids = [item.get("id") for item in public["sources"] if isinstance(item, dict)]
    private_ids = [item.get("id") for item in private["sources"] if isinstance(item, dict)]
    if (len(public_ids) != len(public["sources"]) or len(private_ids) != len(private["sources"])
            or any(not isinstance(value, str) or not value for value in public_ids + private_ids)
            or len(set(public_ids + private_ids)) != len(public_ids) + len(private_ids)):
        raise InventoryError("duplicate_or_invalid_private_source")
    return {**public, "sources": [*public["sources"], *private["sources"]]}


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


def valid_review_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return timestamp.tzinfo is not None and timestamp.utcoffset() is not None


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
                    or re.fullmatch(r"[0-9a-f]{64}", record["snapshot_sha256"]) is None
                    or not isinstance(record.get("reviewer"), str)
                    or not record["reviewer"].strip()
                    or not isinstance(record.get("review_note"), str)
                    or not record["review_note"].strip()
                    or not valid_review_timestamp(record.get("reviewed_at"))):
                raise InventoryError("unverified_processing_record")
            profile = record.get("extraction_profile")
            if profile is not None and (
                    record.get("snapshot_kind") != "extracted_text"
                    or not isinstance(profile, str)
                    or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", profile) is None):
                raise InventoryError("invalid_extraction_profile")
            source_kind = record.get("source_kind")
            if source_kind is not None and (
                    state != "processed"
                    or not isinstance(source_kind, str)
                    or source_kind not in {"learning_material", "bibliography"}):
                raise InventoryError("invalid_reviewed_source_kind")
            if source_kind is not None:
                kind_review = record.get("source_kind_review")
                if (not isinstance(kind_review, dict)
                        or not isinstance(kind_review.get("reviewer"), str)
                        or not kind_review["reviewer"].strip()
                        or not isinstance(kind_review.get("note"), str)
                        or not kind_review["note"].strip()
                        or not valid_review_timestamp(kind_review.get("reviewed_at"))):
                    raise InventoryError("invalid_reviewed_source_kind")
            if state == "conflict" and (not isinstance(record.get("reason"), str)
                                         or not record["reason"].strip()):
                raise InventoryError("invalid_processing_record")
            history = record.get("previous_processed_review")
            seen_history = set()
            while history is not None:
                if (not isinstance(history, dict) or id(history) in seen_history
                        or history.get("review_state") != "processed"
                        or not isinstance(history.get("revision"), (list, tuple))
                        or len(history["revision"]) != 3
                        or any(not isinstance(value, str) or not value
                               for value in history["revision"])
                        or not isinstance(history.get("snapshot_kind"), str)
                        or history["snapshot_kind"] not in {"file_bytes", "extracted_text"}
                        or not isinstance(history.get("snapshot_sha256"), str)
                        or re.fullmatch(r"[0-9a-f]{64}", history["snapshot_sha256"]) is None
                        or not isinstance(history.get("reviewer"), str)
                        or not history["reviewer"].strip()
                        or not isinstance(history.get("review_note"), str)
                        or not history["review_note"].strip()
                        or not valid_review_timestamp(history.get("reviewed_at"))):
                    raise InventoryError("invalid_previous_processed_review")
                seen_history.add(id(history))
                history = history.get("previous_processed_review")
            if "conflict_hold" in record:
                hold = record["conflict_hold"]
                related = hold.get("related_source_ids") if isinstance(hold, dict) else None
                if (state != "pending_review" or not isinstance(hold, dict)
                        or not isinstance(hold.get("reason"), str) or not hold["reason"].strip()
                        or not isinstance(hold.get("locator"), str) or not hold["locator"].strip()
                        or not isinstance(related, list)
                        or any(not isinstance(source_id, str) or not source_id
                               or source_id == file_id for source_id in related)
                        or len(set(related)) != len(related)):
                    raise InventoryError("invalid_conflict_hold")
            if tuple(revision) != _revision(item):
                result[file_id] = "changed_unprocessed"
            elif state == "conflict":
                result[file_id] = "conflict_review"
            elif state == "processed":
                result[file_id] = "processed"
            else:
                result[file_id] = "pending_review"
    return result


def unresolved_related_conflicts(processed: dict[str, dict]) -> set[str]:
    """Sources held by another review cannot be approved as independent evidence."""
    if not isinstance(processed, dict):
        raise InventoryError("invalid_processing_record")
    related_conflicts = set()
    for record in processed.values():
        if not isinstance(record, dict):
            raise InventoryError("invalid_processing_record")
        state = record.get("review_state")
        if state == "conflict":
            related = record.get("related_source_ids", [])
        elif state == "pending_review" and "conflict_hold" in record:
            hold = record["conflict_hold"]
            if not isinstance(hold, dict):
                raise InventoryError("invalid_processing_record")
            related = hold.get("related_source_ids", [])
        else:
            continue
        if (not isinstance(related, list)
                or any(not isinstance(source_id, str) or not source_id for source_id in related)):
            raise InventoryError("invalid_processing_record")
        related_conflicts.update(related)
    return related_conflicts


def link_lessons(snapshot: dict, links: list[dict], *, curriculum_topics: dict | None = None) -> dict:
    """Group formats only by explicit editor-confirmed lesson IDs."""
    if curriculum_topics is not None and not isinstance(curriculum_topics, dict):
        raise InventoryError("invalid_curriculum_topics")
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
        if curriculum_topics is not None and topic_id not in curriculum_topics:
            raise InventoryError("unknown_lesson_topic")
        revision = link.get("revision")
        corpus_path = link.get("corpus_path")
        if (not isinstance(revision, list) or len(revision) != 3
                or any(not isinstance(part, str) or not part for part in revision)
                or not isinstance(corpus_path, str) or not corpus_path
                or not isinstance(link.get("reviewer"), str) or not link["reviewer"].strip()
                or not isinstance(link.get("review_note"), str) or not link["review_note"].strip()
                or not valid_review_timestamp(link.get("reviewed_at"))):
            raise InventoryError("invalid_lesson_link")
        if (tuple(revision) != _revision(snapshot["files"][source_id])
                or corpus_path not in ("/".join(path) for path in snapshot["paths"][source_id])):
            raise InventoryError("stale_lesson_link")
        # One source file can contribute to a lesson only once. A second label
        # must not turn the same file into another format variant.
        key = (source_id, lesson_id)
        if key in seen:
            raise InventoryError("duplicate_lesson_link")
        seen.add(key)
        lesson = lessons.setdefault(lesson_id, {"topic_id": topic_id, "sources": []})
        if lesson["topic_id"] != topic_id:
            raise InventoryError("conflicting_lesson_topic")
        lesson["sources"].append({"source_id": source_id, "format": format_name})
    return lessons


def format_variant_candidates(snapshot: dict) -> list[dict]:
    """Suggest same-folder format variants without merging or approving them."""
    groups: dict[tuple[tuple[str, ...], str], set[str]] = {}
    for file_id, item in snapshot["files"].items():
        title = item["title"]
        if item["mime_type"] == "application/pdf" and title.lower().endswith(".pdf"):
            title = title[:-4]
        elif (item["mime_type"] ==
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              and title.lower().endswith(".docx")):
            title = title[:-5]
        stem = " ".join(unicodedata.normalize("NFKC", title).casefold().split())
        for path in snapshot["paths"][file_id]:
            groups.setdefault((tuple(path[:-1]), stem), set()).add(file_id)
    candidates = []
    for (parent_path, stem), ids in groups.items():
        formats = {snapshot["files"][file_id]["mime_type"] for file_id in ids}
        if len(ids) > 1 and len(formats) > 1:
            candidates.append({"parent_path": list(parent_path), "normalized_stem": stem,
                               "file_ids": sorted(ids), "mime_types": sorted(formats)})
    return sorted(candidates, key=lambda item: (item["parent_path"], item["normalized_stem"]))


def cross_folder_title_review_candidates(snapshot: dict) -> list[dict]:
    """Flag same-titled distinct files in different folders; never infer a link."""
    groups: dict[str, dict[str, set[tuple[str, ...]]]] = {}
    for file_id, item in snapshot["files"].items():
        title = item["title"]
        if item["mime_type"] == "application/pdf" and title.lower().endswith(".pdf"):
            title = title[:-4]
        elif (item["mime_type"] ==
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              and title.lower().endswith(".docx")):
            title = title[:-5]
        stem = " ".join(unicodedata.normalize("NFKC", title).casefold().split())
        parents = {tuple(path[:-1]) for path in snapshot["paths"][file_id]}
        groups.setdefault(stem, {})[file_id] = parents
    candidates = []
    for stem, files in groups.items():
        if len(files) < 2 or len(set().union(*files.values())) < 2:
            continue
        candidates.append({"normalized_stem": stem, "file_ids": sorted(files),
                           "parent_paths": [list(path) for path in
                                            sorted(set().union(*files.values()))]})
    return sorted(candidates, key=lambda item: item["normalized_stem"])


def mixed_format_folder_review_candidates(snapshot: dict) -> list[dict]:
    """Queue small nested folders with mixed formats for human review only.

    Different names in one folder do not establish a common lesson. Large
    discipline folders are omitted so they do not obscure actionable folders.
    """
    folders: dict[tuple[str, ...], set[str]] = {}
    for file_id, paths in snapshot["paths"].items():
        for path in paths:
            parent = tuple(path[:-1])
            if len(parent) >= 2:
                folders.setdefault(parent, set()).add(file_id)
    candidates = []
    for parent, ids in folders.items():
        # A practical lesson in the current corpus can contain six separate
        # handouts. Keep it in the review queue without treating the folder
        # as proof that those files form one approved lesson.
        if not 2 <= len(ids) <= 6:
            continue
        formats = {snapshot["files"][file_id]["mime_type"] for file_id in ids}
        if len(formats) < 2 or any(
                other != parent and other[:len(parent)] == parent for other in folders):
            continue
        # Practice folders can contain homework from the preceding session.
        # The number is only a review hint, never an inferred lesson link.
        parent_number = re.search(r"практик[а-я]*\s*№?\s*(\d{1,3})\b", parent[-1], re.I)
        different_practice_number_file_ids = []
        if parent_number:
            for file_id in sorted(ids):
                title = snapshot["files"][file_id]["title"]
                file_number = re.search(r"практик[а-я]*\s*№?\s*(\d{1,3})\b", title, re.I)
                if file_number and file_number.group(1) != parent_number.group(1):
                    different_practice_number_file_ids.append(file_id)
        candidates.append({"parent_path": list(parent), "file_ids": sorted(ids),
                           "mime_types": sorted(formats),
                           "different_practice_number_file_ids": different_practice_number_file_ids})
    return sorted(candidates, key=lambda item: item["parent_path"])


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
                or source.get("discipline_id") is not None
                or ref.get("modified_time") != source["modified_time"]
                or ref.get("snapshot_sha256") != source["snapshot_sha256"]):
            raise InventoryError("invalid_reviewed_lesson")
        linked_ids[source["id"]] += 1
        link_states[states[source["id"]]] += 1
    discipline_sources = [source for source in sources.values()
                          if source.get("discipline_id") is not None]
    if any(source["kind"] != "learning_material"
           or source["discipline_id"] not in curriculum["disciplines"]
           for source in discipline_sources):
        raise InventoryError("invalid_reviewed_discipline_source")
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
        "reviewed_discipline_sources": len(discipline_sources),
        "reviewed_learning_without_lesson": sum(source["kind"] == "learning_material" and
                                                source["id"] not in linked_ids and
                                                source.get("discipline_id") is None
                                                for source in sources.values()),
    }


def private_review_queue(snapshot: dict, registry: dict, curriculum: dict, *,
                         processed: dict | None = None, previous: dict | None = None,
                         reviews: dict | None = None,
                         quality_reviews: dict | None = None,
                         links: list[dict] | None = None,
                         legacy_derivatives: dict[str, list[str]] | None = None,
                         unmapped_legacy_derivatives: list[str] | None = None) -> dict:
    """Operator-only file-level queue; never return this from a public route."""
    reviewed_graph(snapshot, registry, curriculum)
    if processed is not None and not isinstance(processed, dict):
        raise InventoryError("invalid_processing_records")
    if links is not None and not isinstance(links, list):
        raise InventoryError("invalid_lesson_links")
    if (unmapped_legacy_derivatives is not None
            and (not isinstance(unmapped_legacy_derivatives, list)
                 or any(not isinstance(item_id, str) or not item_id
                        for item_id in unmapped_legacy_derivatives)
                 or len(set(unmapped_legacy_derivatives)) != len(unmapped_legacy_derivatives))):
        raise InventoryError("invalid_unmapped_legacy_derivatives")
    lessons = link_lessons(snapshot, links or [], curriculum_topics=curriculum["topics"])
    lesson_ids_by_file: dict[str, set[str]] = {}
    for lesson_id, lesson in lessons.items():
        for linked in lesson["sources"]:
            lesson_ids_by_file.setdefault(linked["source_id"], set()).add(lesson_id)
    sources = {source["id"]: source for source in registry["sources"]}
    derivatives: dict[str, set[str]] = {}
    stale_derivatives: dict[str, set[str]] = {}
    legacy_by_source: dict[str, set[str]] = {}
    quality_items: dict[str, set[str]] = {}
    quality_priority: dict[str, set[str]] = {}
    quality_evidence: dict[str, dict[str, dict]] = {}
    if quality_reviews is not None:
        if (not isinstance(quality_reviews, dict)
                or quality_reviews.get("schema_version") != 1
                or not isinstance(quality_reviews.get("items"), dict)):
            raise InventoryError("invalid_quality_reviews")
        for derivative_id, review in quality_reviews["items"].items():
            if (not isinstance(derivative_id, str) or not derivative_id
                    or not isinstance(review, dict)
                    or review.get("source_support") not in
                    {"supported", "partial", "unconfirmed", "disputed"}
                    or not isinstance(review.get("sources"), list)
                    or not review["sources"]):
                raise InventoryError("invalid_quality_review")
            for ref in review["sources"]:
                source_id = ref.get("source_id") if isinstance(ref, dict) else None
                if (not isinstance(source_id, str) or source_id not in sources
                        or not isinstance(ref.get("locator"), str)
                        or not ref["locator"].strip()):
                    raise InventoryError("invalid_quality_review_source")
                quality_items.setdefault(source_id, set()).add(derivative_id)
                source = sources[source_id]
                revision_current = (ref.get("modified_time") == source["modified_time"]
                                    and ref.get("snapshot_sha256") == source["snapshot_sha256"])
                precision_review = locator_precision_review_required(ref["locator"])
                quality_evidence.setdefault(source_id, {})[derivative_id] = {
                    "locator": ref["locator"],
                    "source_support": review["source_support"],
                    "revision_current": revision_current,
                    "locator_precision_review_required": precision_review,
                }
                if (review["source_support"] != "supported"
                        or not revision_current or precision_review):
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
    if legacy_derivatives is not None:
        if not isinstance(legacy_derivatives, dict):
            raise InventoryError("invalid_legacy_derivatives")
        for derivative_id, source_ids in legacy_derivatives.items():
            if (not isinstance(derivative_id, str) or not derivative_id
                    or not isinstance(source_ids, list) or not source_ids
                    or any(not isinstance(source_id, str) or source_id not in sources
                           for source_id in source_ids)
                    or len(set(source_ids)) != len(source_ids)):
                raise InventoryError("invalid_legacy_derivatives")
            for source_id in source_ids:
                derivatives.setdefault(source_id, set()).add(derivative_id)
                # Frozen publication preserves old content, not evidence of the
                # source revision. Keep it in review even if metadata is current.
                stale_derivatives.setdefault(source_id, set()).add(derivative_id)
                legacy_by_source.setdefault(source_id, set()).add(derivative_id)
    topics = {}
    for topic_id, topic in curriculum["topics"].items():
        topics.setdefault(topic["source"]["source_id"], []).append(topic_id)
    processing = processing_status(snapshot, processed) if processed is not None else None
    # A newer Drive revision does not resolve an earlier disagreement. Hold
    # both sides until an explicit review replaces the conflict record.
    related_conflicts = unresolved_related_conflicts(processed) if processing is not None else set()
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
        explicit_review_problem = (file_id in related_conflicts or processing is not None and
                                   processing[file_id] in
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
            "related_conflict_review_required": file_id in related_conflicts,
            "linked_topic_ids": sorted(topics.get(file_id, [])),
            "linked_lesson_ids": sorted(lesson_ids_by_file.get(file_id, [])),
            "linked_derivative_ids": sorted(linked_derivatives),
            "legacy_derivative_ids": sorted(legacy_by_source.get(file_id, set())),
            "derivative_ids_requiring_review": sorted(affected_derivatives),
            "derivative_review_required": bool(affected_derivatives),
            "quality_review_item_ids": sorted(quality_items.get(file_id, set())),
            "quality_review_priority_ids": sorted(priority_quality),
            "quality_review_evidence": quality_evidence.get(file_id, {}),
        })
    entries.sort(key=lambda item: (item["paths"], item["file_id"]))
    missing = [{"file_id": file_id, "title": source["title"],
                "linked_topic_ids": sorted(topics.get(file_id, [])),
                "linked_derivative_ids": sorted(derivatives.get(file_id, set())),
                "legacy_derivative_ids": sorted(legacy_by_source.get(file_id, set())),
                "derivative_ids_requiring_review": sorted(derivatives.get(file_id, set())),
                "derivative_review_required": bool(derivatives.get(file_id)),
                "related_conflict_review_required": file_id in related_conflicts,
                "quality_review_item_ids": sorted(quality_items.get(file_id, set())),
                "quality_review_priority_ids": sorted(quality_items.get(file_id, set())),
                "quality_review_evidence": quality_evidence.get(file_id, {})}
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
    variants = format_variant_candidates(snapshot)
    for variant in variants:
        linked = [lesson_ids_by_file.get(file_id, set()) for file_id in variant["file_ids"]]
        variant["link_state"] = "linked" if linked and set.intersection(*linked) else "candidate"
    cross_folder_reviews = cross_folder_title_review_candidates(snapshot)
    folder_reviews = mixed_format_folder_review_candidates(snapshot)
    for folder in folder_reviews:
        linked = [lesson_ids_by_file.get(file_id, set()) for file_id in folder["file_ids"]]
        folder["link_state"] = "linked" if linked and set.intersection(*linked) else "candidate"
    return {"schema_version": 1, "root_id": snapshot["root_id"],
            "files": entries, "missing_tracked_sources": missing,
            "missing_untracked_files": missing_untracked,
            "unmapped_legacy_derivative_ids": sorted(unmapped_legacy_derivatives or []),
            "format_variant_candidates": variants,
            "cross_folder_title_review_candidates": cross_folder_reviews,
            "mixed_format_folder_review_candidates": folder_reviews}
