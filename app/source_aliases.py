"""Stable public source references; resolution exists only at private read boundaries.

Private captures, reviews, signatures and saved attempts are never rewritten.
Unknown aliases remain unresolved and therefore cannot gain current-source status.
"""
from __future__ import annotations

import hashlib
import re

ALIAS = re.compile(r"^src_[0-9a-f]{64}$")


def source_alias(source_id: str) -> str:
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("invalid_source_identity")
    if ALIAS.fullmatch(source_id):
        return source_id
    return "src_" + hashlib.sha256(("psychology-source-v1:" + source_id).encode()).hexdigest()


def resolve_public_sources(document, private_ids):
    """Copy public metadata into a supplied private inventory's identity space.

    No discovery, network access, file writes or publication approval. The caller
    must still validate revision, location, snapshot, review and conflict holds.
    """
    aliases = {}
    for raw in private_ids:
        if not isinstance(raw, str) or not raw:
            raise ValueError("private_source_identity_required")
        alias = source_alias(raw)
        if alias in aliases and aliases[alias] != raw:
            raise ValueError("ambiguous_source_alias")
        aliases[alias] = raw

    def resolve(value):
        if isinstance(value, str):
            if value.startswith("drive:"):
                identity, separator, locator = value[6:].partition("#")
                return "drive:" + aliases.get(identity, identity) + (separator + locator)
            return aliases.get(value, value)
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                resolved = aliases.get(key, key)
                if resolved in result:
                    raise ValueError("ambiguous_source_alias")
                result[resolved] = resolve(item)
            return result
        return value

    return resolve(document)


def private_graph_inputs(snapshot, *documents):
    return resolve_public_sources(list(documents), [snapshot["root_id"], *snapshot["files"]])
