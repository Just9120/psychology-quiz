from scripts.audit_topic_evidence import coverage


def test_current_edition_support_is_distinct_from_stale_and_partial():
    curriculum = {
        "topics": {"one": {"title": "One", "source": {"source_id": "s1",
                    "modified_time": "revision-1", "snapshot_sha256": "digest-1"}},
                   "two": {"title": "Two"}},
        "editions": {
            "first": {"topic_id": "one", "external_id": "q1", "item_sha256": "current"},
            "second": {"topic_id": "one", "external_id": "q2", "item_sha256": "old"},
            "third": {"topic_id": "two", "external_id": "q3", "item_sha256": "same"},
            "unknown": {"topic_id": "removed", "external_id": "q4", "item_sha256": "same"},
            "retired": {"topic_id": "two", "external_id": "q5", "item_sha256": "same"},
        },
    }
    quality = {"items": {
        "questions:q1": {"item_sha256": "current", "source_support": "supported",
                         "sources": [{"source_id": "s1", "modified_time": "revision-1",
                                      "snapshot_sha256": "digest-1"}]},
        "questions:q2": {"item_sha256": "new", "source_support": "supported"},
        "questions:q3": {"item_sha256": "same", "source_support": "partial"},
        "questions:q6": {"item_sha256": "same", "source_support": "disputed"},
    }}

    result = coverage(curriculum, quality, {
        "q1": "current", "q2": "new", "q3": "same", "q4": "same", "q6": "same"})

    assert result["topics"]["one"]["supported"] == 1
    assert result["topics"]["one"]["stale"] == 1
    assert result["topics"]["two"]["partial"] == 1
    assert result["topics_without_supported_question"] == ["two"]
    assert result["unknown_topic_editions"] == 1
    assert result["approved_questions_without_curriculum_edition"] == 1
    assert result["unmapped_questions_by_source_support"] == {"disputed": 1}


def test_stale_unmapped_review_is_not_reported_as_supported():
    result = coverage({"topics": {}, "editions": {}}, {"items": {
        "questions:new": {"item_sha256": "old", "source_support": "supported"},
    }}, {"new": "current"})

    assert result["approved_questions_without_curriculum_edition"] == 1
    assert result["unmapped_questions_by_source_support"] == {"stale": 1}


def test_supported_label_without_current_topic_source_does_not_cover_topic():
    curriculum = {"topics": {"one": {"title": "One", "source": {
        "source_id": "s1", "modified_time": "revision-2", "snapshot_sha256": "digest-2"}}},
        "editions": {"first": {"topic_id": "one", "external_id": "q1",
                               "item_sha256": "current"}}}
    quality = {"items": {"questions:q1": {"item_sha256": "current",
        "source_support": "supported", "sources": [{"source_id": "s1",
        "modified_time": "revision-1", "snapshot_sha256": "digest-1"}]}}}

    result = coverage(curriculum, quality, {"q1": "current"})

    assert result["topics"]["one"]["supported"] == 0
    assert result["topics"]["one"]["unverified_source"] == 1
    assert result["topics_without_supported_question"] == ["one"]


def test_private_review_state_explains_gap_without_exposing_source_id():
    curriculum = {"topics": {"one": {"title": "One", "source": {"source_id": "private-1"}},
                             "two": {"title": "Two", "source": {"source_id": "private-2"}}},
                  "editions": {}}
    result = coverage(curriculum, {"items": {}}, {}, {"private-1": "conflict_review"})
    assert result["topics"]["one"]["source_review_state"] == "conflict_review"
    assert result["topics"]["two"]["source_review_state"] == "missing_from_inventory"
    assert "private-1" not in str(result)
