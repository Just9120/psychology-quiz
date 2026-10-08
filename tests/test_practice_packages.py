from copy import deepcopy
import json
from pathlib import Path
import pytest
from app.practice_packages import load_case_package, package_from_case
from scripts import export_practice_package

CASE_ID = "case_first_consultation_001"


def published_case():
    return json.loads(Path("content/questions/module3/cases.json").read_text(encoding="utf-8"))[0]


def test_handoff_separates_role_from_review_and_keeps_only_published_material():
    original = published_case()
    saved = deepcopy(original)
    package = package_from_case(original)
    assert original == saved
    assert package == load_case_package(CASE_ID)
    assert package["student_brief"]["situation"] == original["case"]["situation"]
    assert package["materials"]["explanation"] == original["explanation"]
    assert [c["rationale"] for c in package["criteria"]] == original["case"]["option_rationales"]
    assert sum(c["preferred_in_stated_conditions"] for c in package["criteria"]) == 1
    for key in ("student_brief", "client_role"):
        text = json.dumps(package[key], ensure_ascii=False)
        assert original["explanation"] not in text
        assert original["options"][original["correct_option_index"]] not in text
        assert "criteria" not in package[key]
    serialized = json.dumps(package, ensure_ascii=False)
    assert "drive:" not in serialized and "source_ref" not in serialized
    # Current private-review cases omit raw source identities before handoff.
    assert "source_ref" not in original
    assert "профессиональную компетентность" in package["transcript_analysis"]["notice"]
    package["transcript_analysis"]["criteria"][0]["action"] = "modified"
    assert package["criteria"][0]["action"] == original["options"][0]


def test_changed_unapproved_or_noncase_content_cannot_export_as_reviewed():
    original = published_case()
    for mutate in (
        lambda q: q.update(status="draft"),
        lambda q: q.update(kind="theory"),
        lambda q: q.update(explanation="An unreviewed clinical recommendation"),
        lambda q: q["case"].update(situation="unreviewed situation"),
        lambda q: q["case"].pop("conditions"),
    ):
        changed = deepcopy(original)
        mutate(changed)
        with pytest.raises(ValueError, match="published_reviewed_case_required"):
            package_from_case(changed)
    with pytest.raises(ValueError, match="unique_case_required"):
        load_case_package("missing-case")


def test_private_export_readback_refuses_overwrite_and_outside_output(tmp_path, monkeypatch):
    monkeypatch.setattr(export_practice_package, "ROOT", tmp_path)
    output = tmp_path / "data" / "practice"
    result = export_practice_package.export(CASE_ID, output)
    assert result["files"] == 4
    assert {p.name for p in output.iterdir()} == {"session.json", "client-role.json", "student-brief.txt", "transcript-analysis.json"}
    session = json.loads((output / "session.json").read_text(encoding="utf-8"))
    assert json.loads((output / "client-role.json").read_text(encoding="utf-8")) == session["client_role"]
    assert json.loads((output / "transcript-analysis.json").read_text(encoding="utf-8")) == session["transcript_analysis"]
    brief = (output / "student-brief.txt").read_text(encoding="utf-8")
    assert session["student_brief"]["situation"] in brief and session["materials"]["explanation"] not in brief
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    with pytest.raises(ValueError, match="new_private_output_required"):
        export_practice_package.export(CASE_ID, output)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
    with pytest.raises(ValueError, match="new_private_output_required"):
        export_practice_package.export(CASE_ID, tmp_path / "outside")
    with pytest.raises(ValueError, match="unique_case_required"):
        export_practice_package.export("missing-case", tmp_path / "data" / "missing")
    assert not (tmp_path / "outside").exists() and not (tmp_path / "data" / "missing").exists()


def test_voice_handoff_preserves_case_review_and_export_without_transcript(tmp_path, monkeypatch):
    question = published_case()
    original = deepcopy(question)
    text = package_from_case(question)
    voice = package_from_case(question, mode="voice")
    assert question == original
    for key in ("case_fingerprint", "materials", "criteria", "transcript_analysis"):
        assert voice[key] == text[key]
    for key in ("instructions", "role_context", "constraints"):
        assert voice["client_role"][key] == text["client_role"][key]
    assert voice["practice_mode"] == "voice"
    assert "голосовой режим" in voice["student_brief"]["task"]
    assert "ошибку распознавания" in " ".join(voice["client_role"]["voice_instructions"])
    assert question["explanation"] not in json.dumps(voice["client_role"], ensure_ascii=False)
    monkeypatch.setattr(export_practice_package, "ROOT", tmp_path)
    output = tmp_path / "data" / "voice-practice"
    result = export_practice_package.export(CASE_ID, output, mode="voice")
    assert result["files"] == 4
    saved = json.loads((output / "session.json").read_text(encoding="utf-8"))
    assert saved == voice
    assert "voice_instructions" in json.loads((output / "client-role.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="invalid_practice_mode"):
        export_practice_package.export(CASE_ID, tmp_path / "data" / "invalid", mode="unknown")
    assert not (tmp_path / "data" / "invalid").exists()
