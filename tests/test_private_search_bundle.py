import hashlib
import json
import os
from pathlib import Path
import zipfile

import pytest

from scripts.private_search_bundle import BundleError, create, install, read_bundle


def example(tmp_path):
    local = tmp_path / "local" / ".private-search"
    source = local / "input"
    source.mkdir(parents=True)
    (source / "lesson.txt").write_text("Проверенный приватный фрагмент", encoding="utf-8")
    (source / "processing.json").write_text("{}", encoding="utf-8")
    (source / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "processing_path": "processing.json",
        "sources": [{"source_id": "source-id", "text_path": "lesson.txt"}]}), encoding="utf-8")
    (source / "qa.json").write_text(json.dumps({"schema_version": 1, "cases": []}), encoding="utf-8")
    archive = local / "private.zip"
    result = create(source, "manifest.json", "qa.json", archive)
    return archive, result["sha256"]


def test_private_bundle_integrity_install_resume_and_collision(tmp_path):
    archive, digest = example(tmp_path)
    envelope, files = read_bundle(archive, digest)
    assert envelope["manifest"] == "manifest.json" and len(files) == 4
    target = tmp_path / "vps" / ".private-search" / "input"
    target.parent.parent.mkdir(parents=True)
    first = install(archive, digest, target)
    assert first["created"] == 4
    assert install(archive, digest, target)["created"] == 0
    assert (target / "lesson.txt").read_bytes() == files["lesson.txt"]
    (target / "lesson.txt").write_text("изменено", encoding="utf-8")
    with pytest.raises(BundleError, match="collision"):
        install(archive, digest, target)
    with pytest.raises(BundleError, match="digest_changed"):
        read_bundle(archive, "0" * 64)


def test_private_bundle_includes_explicit_private_registry(tmp_path):
    source = tmp_path / "local" / ".private-search" / "input"
    source.mkdir(parents=True)
    (source / "lesson.txt").write_text("Проверенный фрагмент", encoding="utf-8")
    (source / "processing.json").write_text("{}", encoding="utf-8")
    (source / "private-registry.json").write_text(json.dumps({
        "schema_version": 1, "corpus_root_id": "root", "sources": []}), encoding="utf-8")
    manifest = {"schema_version": 1, "processing_path": "processing.json",
                "private_registry_path": "private-registry.json",
                "sources": [{"source_id": "private-source", "text_path": "lesson.txt"}]}
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (source / "qa.json").write_text(json.dumps({"schema_version": 1, "cases": []}), encoding="utf-8")
    archive = source.parent / "private.zip"
    digest = create(source, "manifest.json", "qa.json", archive)["sha256"]
    _, files = read_bundle(archive, digest)
    assert "private-registry.json" in files and len(files) == 5
    manifest["private_registry_path"] = "../outside.json"
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BundleError, match="filename_required"):
        create(source, "manifest.json", "qa.json", source.parent / "invalid.zip")


def test_private_search_host_data_is_not_mounted_into_public_clients():
    compose = Path(__file__).resolve().parents[1].joinpath("docker-compose.yml").read_text(encoding="utf-8")
    app_services, search_service = compose.split("  psych_quiz_private_search:", 1)
    assert ".private-search" not in app_services
    assert "./.private-search/input:/data/search-input:ro" in search_service
    assert "./.private-search/model-cache:/data/search-model-cache" in search_service
    assert "./data/search-input" not in compose


def test_private_bundle_refuses_old_shared_app_location(tmp_path):
    archive, digest = example(tmp_path)
    host = tmp_path / "vps"
    legacy = host / "data" / "search-input"
    legacy.mkdir(parents=True)
    with pytest.raises(BundleError, match="legacy_private_search_exposed_to_app"):
        install(archive, digest, host / ".private-search" / "input")
    assert not (host / ".private-search").exists()


def test_private_bundle_rejects_archive_escape_and_unreferenced_file(tmp_path):
    archive, digest = example(tmp_path)
    envelope, files = read_bundle(archive, digest)
    invalid = tmp_path / "escape.zip"
    with zipfile.ZipFile(invalid, "w") as output:
        for name, content in files.items():
            output.writestr(name, content)
        output.writestr("../outside.txt", "private")
        output.writestr("_bundle.json", json.dumps(envelope))
    os.chmod(invalid, 0o600)
    with pytest.raises(BundleError, match="invalid_private_archive_members"):
        read_bundle(invalid, hashlib.sha256(invalid.read_bytes()).hexdigest())

    invalid = tmp_path / "extra.zip"
    extra = b"unreferenced"
    envelope["files"]["extra.txt"] = {"sha256": hashlib.sha256(extra).hexdigest(),
                                           "size": len(extra)}
    with zipfile.ZipFile(invalid, "w") as output:
        for name, content in files.items():
            output.writestr(name, content)
        output.writestr("extra.txt", extra)
        output.writestr("_bundle.json", json.dumps(envelope))
    os.chmod(invalid, 0o600)
    with pytest.raises(BundleError, match="unreferenced_file"):
        read_bundle(invalid, hashlib.sha256(invalid.read_bytes()).hexdigest())
