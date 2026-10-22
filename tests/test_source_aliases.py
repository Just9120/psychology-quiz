import copy

import pytest

from app.source_aliases import private_graph_inputs, resolve_public_sources, source_alias
from app.source_inventory import InventoryError, combine_registries, reviewed_graph


def test_alias_resolution_preserves_private_evidence_and_rejects_ambiguous_identity():
    raw = "synthetic-private-source"
    public = {"sources": [{"source_id": source_alias(raw), "snapshot_sha256": "a" * 64}],
              "source_ref": "drive:" + source_alias(raw) + "#characters:0:5"}
    before = copy.deepcopy(public)
    resolved = resolve_public_sources(public, [raw])
    assert resolved["sources"][0] == {"source_id": raw, "snapshot_sha256": "a" * 64}
    assert resolved["source_ref"] == "drive:" + raw + "#characters:0:5"
    assert public == before
    assert resolve_public_sources(public, ["another-source"]) == public
    with pytest.raises(ValueError, match="ambiguous_source_alias"):
        resolve_public_sources(public, [raw, source_alias(raw)])
    registry = {"schema_version": 1, "corpus_root_id": source_alias("root"),
                "sources": [{"id": source_alias(raw)}]}
    with pytest.raises(InventoryError, match="duplicate_or_invalid_private_source"):
        combine_registries(registry, {"schema_version": 1, "corpus_root_id": "root",
                                     "sources": [{"id": raw}]})


def test_alias_graph_still_checks_revision_and_location_without_rewriting_inputs():
    source = {"id": "private-source", "kind": "learning_material", "readable": True,
        "title": "Lesson", "modified_time": "2026-09-25T00:00:00Z", "snapshot_kind": "extracted_text",
        "snapshot_sha256": "a" * 64, "corpus_path": "Lesson", "reviewer": "editor", "reviewed_at": "2026-09-26"}
    snapshot = {"root_id": "root", "files": {source["id"]: {**source, "mime_type": "text/plain"}},
                "paths": {source["id"]: [["Lesson"]]}}
    registry = {"schema_version": 1, "corpus_root_id": source_alias("root"),
                "sources": [{**source, "id": source_alias(source["id"])}]}
    curriculum = {"schema_version": 1, "disciplines": {"general": {}}, "topics": {"lesson": {
        "title": "Lesson", "discipline_id": "general", "source": {
            "source_id": source_alias(source["id"]), "modified_time": source["modified_time"],
            "snapshot_sha256": source["snapshot_sha256"]}}}}
    before = copy.deepcopy((registry, curriculum, snapshot))
    assert reviewed_graph(snapshot, registry, curriculum)["lesson_metadata"] == {"current": 1}
    assert (registry, curriculum, snapshot) == before
    snapshot["files"][source["id"]]["modified_time"] = "2026-10-01T00:00:00Z"
    assert reviewed_graph(snapshot, registry, curriculum)["lesson_metadata"] == {"changed": 1}
    snapshot["files"][source["id"]]["modified_time"] = source["modified_time"]
    snapshot["paths"][source["id"]] = [["Moved", "Lesson"]]
    assert reviewed_graph(snapshot, registry, curriculum)["lesson_metadata"] == {"relocated": 1}
    resolved_registry, resolved_curriculum = private_graph_inputs(snapshot, registry, curriculum)
    assert resolved_registry["corpus_root_id"] == "root"
    assert resolved_curriculum["topics"]["lesson"]["source"]["source_id"] == source["id"]
