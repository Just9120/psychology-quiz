"""Private Drive metadata inventory; discovery never approves publication.

The caller supplies complete, paginated direct-child listings. A missing page
is an error, not an empty folder. Persist snapshots only in ignored private
operator storage, never among public content or static assets.
"""
from __future__ import annotations

from collections import deque


class InventoryError(ValueError):
    pass


def _revision(item: dict) -> tuple[str, str, str]:
    return item["modified_time"], item["title"], item["mime_type"]


def scan(root_id: str, listings: dict[str, dict]) -> dict:
    if not isinstance(root_id, str) or not root_id:
        raise InventoryError("root_required")
    queue, seen_folders, files = deque([root_id]), set(), {}
    while queue:
        parent = queue.popleft()
        if parent in seen_folders:
            continue
        listing = listings.get(parent)
        if not isinstance(listing, dict) or listing.get("complete") is not True:
            raise InventoryError("incomplete_folder_listing")
        children = listing.get("children")
        if not isinstance(children, list):
            raise InventoryError("invalid_folder_listing")
        seen_folders.add(parent)
        for item in children:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                raise InventoryError("invalid_child")
            parents = item.get("parent_ids")
            if not isinstance(parents, list) or parent not in parents:
                raise InventoryError("parent_mismatch")
            if item.get("file_or_folder") == "folder":
                queue.append(item["id"])
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
    return {"root_id": root_id, "folders": len(seen_folders), "files": files}


def reconcile(previous: dict, current: dict) -> dict:
    if previous.get("root_id") != current.get("root_id"):
        raise InventoryError("root_changed")
    old, new = previous["files"], current["files"]
    changes = {"new": [], "changed": [], "unchanged": [], "missing": []}
    for file_id, item in new.items():
        if file_id not in old:
            changes["new"].append(file_id)
        elif _revision(old[file_id]) != _revision(item):
            changes["changed"].append(file_id)
        else:
            changes["unchanged"].append(file_id)
    changes["missing"] = sorted(old.keys() - new.keys())
    return {name: sorted(ids) for name, ids in changes.items()}
