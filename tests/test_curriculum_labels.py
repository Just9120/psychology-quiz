from copy import deepcopy
import json

import pytest

from app.curriculum import merge_public_labels
from scripts.export_curriculum_labels import project_labels


def fixture():
    source_id = "private-transcript-1234567890"
    source = {"id": source_id, "kind": "learning_material", "title": "Lecture",
        "corpus_path": "Модуль 4/Lecture", "modified_time": "2026-10-01T00:00:00Z",
        "snapshot_kind": "extracted_text", "snapshot_sha256": "a" * 64,
        "readable": True, "reviewed_at": "2026-10-03", "reviewer": "reviewer"}
    catalog = {"schema_version": 1, "disciplines": {}, "topics": {}, "editions": {}}
    private = {"schema_version": 1, "corpus_root_id": "root",
        "disciplines": {"development": {"title": "Development"}}, "topics": {
        "t_123456789abc": {"title": "Development lesson", "discipline_id": "development",
            "source": {"source_id": source_id, "modified_time": source["modified_time"],
                "snapshot_sha256": source["snapshot_sha256"]}}}}
    registry = {"schema_version": 1, "corpus_root_id": "root", "sources": [source]}
    snapshot = {"root_id": "root", "files": {source_id: {"title": source["title"],
        "modified_time": source["modified_time"], "mime_type": "application/vnd.google-apps.document"}},
        "paths": {source_id: [["Модуль 4", "Lecture"]]}}
    return catalog, private, registry, snapshot


def test_export_labels_preserves_private_graph_and_has_no_source_metadata():
    values = fixture()
    before = deepcopy(values)
    labels = project_labels(*values)
    assert values == before
    assert labels["disciplines"]["development"] == {
        "title": "Development", "module": "module4", "modules": ["module4"]}
    assert labels["topics"]["t_123456789abc"] == {
        "title": "Development lesson", "discipline_id": "development"}
    encoded = json.dumps(labels)
    assert "private-transcript" not in encoded and "snapshot_sha256" not in encoded
    result = merge_public_labels(values[0], labels)
    assert result["editions"] == {} and "source" not in result["topics"]["t_123456789abc"]


def test_changed_source_cannot_export_current_labels():
    catalog, private, registry, snapshot = fixture()
    next(iter(snapshot["files"].values()))["modified_time"] = "2026-10-02T00:00:00Z"
    with pytest.raises(ValueError, match="Current source graph"):
        project_labels(catalog, private, registry, snapshot)


@pytest.mark.parametrize("field,value", [("source", {}), ("editions", {}), ("locator", "private")])
def test_public_topic_labels_reject_source_and_answer_mapping_fields(field, value):
    values = fixture()
    labels = project_labels(*values)
    labels["topics"]["t_123456789abc"][field] = value
    with pytest.raises(ValueError, match="Invalid curriculum topic label"):
        merge_public_labels(values[0], labels)


def test_public_labels_cannot_rename_existing_topics_or_reassign_editions():
    values = fixture()
    labels = project_labels(*values)
    catalog = merge_public_labels(values[0], labels)
    catalog["editions"]["b" * 64] = {"topic_id": "t_123456789abc", "external_id": "old"}
    before = deepcopy(catalog)
    assert merge_public_labels(catalog, labels) == before
    labels["topics"]["t_123456789abc"]["title"] = "Other title"
    with pytest.raises(ValueError, match="Conflicting curriculum topic label"):
        merge_public_labels(catalog, labels)
    assert catalog == before
