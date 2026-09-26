import hashlib

import pytest

from app.content_publication import fingerprint
from app.source_inventory import InventoryError
from scripts import source_capture, source_claim_candidates
from tests.test_source_inventory_report import export


def test_private_candidates_preserve_exact_crlf_coordinates_and_digest(tmp_path, monkeypatch):
    text = "Память — сохранение опыта.\r\nВнимание — избирательная обработка сигналов.\r\n"
    content = tmp_path / "source.txt"
    content.write_bytes(text.encode("utf-8"))
    current = export(["doc"])
    processed = source_capture.capture(current, {}, "doc", content, "extracted_text")
    item = {"id": "q1", "question": "Что означает внимание?",
            "options": ["Избирательная обработка сигналов", "Сохранение опыта"],
            "correct_option_index": 0, "explanation": "Внимание выбирает сигналы."}
    reviews = {"questions:q1": {"item_sha256": fingerprint(item),
                               "sources": [{"source_id": "doc"}]}}
    manifest = {"schema_version": 1, "sources": [{"source_id": "doc",
                 "content": "data/source.txt", "snapshot_kind": "extracted_text"}]}
    monkeypatch.setattr(source_claim_candidates, "_private_content_path", lambda _: content)
    queue = source_claim_candidates.build_queue(
        current, processed, manifest, reviews, {"questions:q1": item})
    claim = queue["sources"][0]["claims"]["questions:q1"]
    assert claim["state"] == "needs_claim_review"
    assert "Внимание —" in text[slice(*claim["candidate_ranges"][0])]
    assert queue["sources"][0]["snapshot_sha256"] == hashlib.sha256(content.read_bytes()).hexdigest()

    content.write_bytes(content.read_bytes() + b" changed")
    with pytest.raises(InventoryError, match="candidate_content_digest_mismatch"):
        source_claim_candidates.build_queue(
            current, processed, manifest, reviews, {"questions:q1": item})
