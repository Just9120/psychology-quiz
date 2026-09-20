import copy

import pytest

from app.content_publication import PublicationPolicy, fingerprint
from scripts.validate_learning_reviews import validate


def fixture():
    items = {"questions:q": {"id": "q", "question": "Synthetic question", "status": "approved"}}
    source = {"id": "lecture", "kind": "learning_material", "readable": True,
              "modified_time": "2026-09-20T00:00:00Z", "snapshot_sha256": "a" * 64}
    review = {"item_sha256": fingerprint(items["questions:q"]), "reviewer": "test-reviewer",
              "reviewed_at": "2026-09-20", "source_support": "supported", "meaning": "consistent",
              "note": "Synthetic rationale", "issues": [],
              "checks": ["meaning", "answer", "explanation", "ambiguity", "duplicates", "sources"],
              "sources": [{"source_id": "lecture", "modified_time": source["modified_time"],
                           "snapshot_sha256": source["snapshot_sha256"], "locator": "section 2"}]}
    return {"schema_version": 1, "items": {"questions:q": review}}, items, {"lecture": source}


def test_audit_does_not_grant_publication_or_rewrite_an_uncertain_judgment():
    ledger, items, sources = fixture()
    review = ledger["items"]["questions:q"]
    assert validate(ledger, items, sources) == []
    policy = PublicationPolicy({}, sources, ledger["items"])
    assert not policy.can_publish("questions", items["questions:q"])
    review.update(source_support="unconfirmed", meaning="ambiguous", sources=[],
                  issues=["No readable fragment supporting the asserted causal relation"])
    before = copy.deepcopy(ledger)
    assert validate(ledger, items, sources) == []
    assert ledger == before
    assert not policy.can_publish("questions", items["questions:q"])


@pytest.mark.parametrize("mutation", [
    "missing_item", "new_item", "stale_question", "stale_source", "stale_revision",
    "bibliography", "unreadable", "unknown_source", "no_locator", "no_fingerprint",
    "no_source", "incomplete_aspects", "unclear_uncertainty", "invalid_date", "missing_reviewer",
])
def test_review_cannot_hide_missing_or_changed_evidence(mutation):
    ledger, items, sources = fixture()
    review = ledger["items"]["questions:q"]
    if mutation == "missing_item": items.clear()
    elif mutation == "new_item": items["questions:new"] = {"id": "new"}
    elif mutation == "stale_question": items["questions:q"]["question"] = "Different proposition"
    elif mutation == "stale_source": sources["lecture"]["snapshot_sha256"] = "b" * 64
    elif mutation == "stale_revision": sources["lecture"]["modified_time"] = "2026-09-21T00:00:00Z"
    elif mutation == "bibliography": sources["lecture"]["kind"] = "bibliography"
    elif mutation == "unreadable": sources["lecture"]["readable"] = False
    elif mutation == "unknown_source": sources.clear()
    elif mutation == "no_locator": review["sources"][0]["locator"] = ""
    elif mutation == "no_fingerprint":
        review["sources"][0].pop("snapshot_sha256")
        sources["lecture"].pop("snapshot_sha256")
    elif mutation == "no_source": review["sources"] = []
    elif mutation == "incomplete_aspects": review["checks"].remove("explanation")
    elif mutation == "unclear_uncertainty": review["source_support"] = "partial"
    elif mutation == "invalid_date": review["reviewed_at"] = "yesterday"
    elif mutation == "missing_reviewer": review["reviewer"] = " "
    assert validate(ledger, items, sources)
