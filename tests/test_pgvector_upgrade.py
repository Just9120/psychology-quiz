"""The live-image change must follow a verified native backup, never precede it."""
import json
from pathlib import Path

import pytest

from app.postgres_config import PG_IMAGE, PG_PREVIOUS_IMAGE
from scripts import postgres_vps as vps


def test_vector_upgrade_rejects_running_private_search_worker(monkeypatch):
    def compose(command, **_kwargs):
        assert command == ["--profile", "search", "ps", "--all", "--quiet",
                           "psych_quiz_private_search"]
        return b"search-container\n"

    monkeypatch.setattr(vps, "compose", compose)
    runtime = vps.Runtime("a" * 40)
    def inspect(command, **_kwargs):
        assert command == ["docker", "inspect", "search-container"]
        return json.dumps([{"Config": {"Labels": {
            "com.docker.compose.project": "psychology-quiz",
            "com.docker.compose.service": "psych_quiz_private_search",
        }}, "State": {"Running": True}}]).encode()

    monkeypatch.setattr(vps, "run", inspect)
    with pytest.raises(vps.OperationError, match="private_search_worker_must_be_stopped"):
        runtime.require_stopped_search_worker()


@pytest.mark.parametrize("owned", [True, False])
def test_vector_upgrade_accepts_only_stopped_owned_search_worker(monkeypatch, owned):
    monkeypatch.setattr(vps, "compose", lambda command, **_kwargs: (
        b"search-container\n" if command == ["--profile", "search", "ps", "--all", "--quiet",
                                          "psych_quiz_private_search"]
        else pytest.fail("unexpected Compose query")))
    monkeypatch.setattr(vps, "run", lambda command, **_kwargs: json.dumps([{
        "Config": {"Labels": {
            "com.docker.compose.project": "psychology-quiz" if owned else "other-project",
            "com.docker.compose.service": "psych_quiz_private_search",
        }}, "State": {"Running": False},
    }]).encode() if command == ["docker", "inspect", "search-container"]
        else pytest.fail("unexpected container inspection"))
    runtime = vps.Runtime("a" * 40)
    if owned:
        runtime.require_stopped_search_worker()
    else:
        with pytest.raises(vps.OperationError, match="container_target_mismatch"):
            runtime.require_stopped_search_worker()


def test_vector_image_stage_checks_rehearsal_space_before_pull(monkeypatch):
    class FakeRuntime:
        def __init__(self, revision):
            assert revision == "a" * 40

        def sql(self, query):
            assert "pg_database_size" in query
            return str(2 * 1024 ** 3)

    monkeypatch.setattr(vps, "Runtime", FakeRuntime)
    monkeypatch.setattr(vps, "vector_image_state", lambda _: "previous")
    def reject_insufficient_space(required):
        assert required == 6 * 1024 ** 3
        raise vps.OperationError("insufficient_space_for_database_and_restore")

    monkeypatch.setattr(vps, "check_space", reject_insufficient_space)
    monkeypatch.setattr(vps, "compose", lambda *_args, **_kwargs: pytest.fail("stage must stop before Compose"))
    with pytest.raises(vps.OperationError, match="insufficient_space_for_database_and_restore"):
        vps.stage_vector_image("a" * 40)


def test_vector_image_stage_rechecks_space_after_pull_before_stopping_writers(monkeypatch):
    events = []

    class FakeRuntime:
        def __init__(self, revision):
            assert revision == "a" * 40

        def sql(self, query):
            assert "pg_database_size" in query
            return "26214400"

        def container(self, service):
            assert service == vps.PG_SERVICE
            return {"Config": {"Image": PG_PREVIOUS_IMAGE}}

    def space(required):
        assert required == 1024 ** 3
        events.append("space")
        if events.count("space") == 2:
            raise vps.OperationError("insufficient_space_for_database_and_restore")

    def run(command, **_kwargs):
        if command[:2] == ["docker", "pull"]:
            events.append("pull")
            return b""
        if command[-2:] == ["-u", "postgres"]:
            return b"999"
        if command[-1] == "--version":
            return b"postgres (PostgreSQL) 18.6"
        assert "vector--0.8.6.sql" in command[-1]
        return b""

    monkeypatch.setattr(vps, "Runtime", FakeRuntime)
    monkeypatch.setattr(vps, "vector_image_state", lambda _: "previous")
    monkeypatch.setattr(vps, "check_space", space)
    monkeypatch.setattr(vps, "compose", lambda *_args, **_kwargs: (PG_IMAGE + "\n").encode())
    monkeypatch.setattr(vps, "run", run)
    with pytest.raises(vps.OperationError, match="insufficient_space_for_database_and_restore"):
        vps.stage_vector_image("a" * 40)
    assert events == ["space", "pull", "space"]


@pytest.mark.parametrize(("schemas", "extension_ready", "allowed"), [
    ("public", False, True),
    ("private_search,public", True, True),
    ("private_search,public", False, False),
    ("operator_data,public", False, False),
])
def test_native_backup_excludes_only_verified_rebuildable_search_schema(
        tmp_path, monkeypatch, schemas, extension_ready, allowed):
    runtime = vps.Runtime("a" * 40)
    calls = []

    def pg(arguments, **kwargs):
        calls.append(arguments[0])
        if arguments[0] == "psql":
            assert b"pg_namespace" in kwargs["data"]
            return schemas.encode()
        assert arguments[0] == "pg_dump"
        assert "--exclude-schema=private_search" in arguments
        assert "--exclude-extension=vector" in arguments
        kwargs["output"].write(b"synthetic-native-dump")
        return b""

    monkeypatch.setattr(runtime, "pg", pg)
    monkeypatch.setattr(vps, "vector_extension_status", lambda _: extension_ready)
    output = tmp_path / "database.dump"
    if allowed:
        runtime.dump(output)
        assert output.read_bytes() == b"synthetic-native-dump"
        assert calls == ["psql", "pg_dump"]
    else:
        with pytest.raises(vps.OperationError, match="backup_schema|extension_required"):
            runtime.dump(output)
        assert not output.exists()
        assert calls == ["psql"]


def test_vector_image_stage_requires_exact_extension_before_upgrade(monkeypatch):
    class FakeRuntime:
        def __init__(self, revision):
            assert revision == "a" * 40

        def sql(self, query):
            return "1048576"

        def container(self, service):
            return {"Config": {"Image": PG_IMAGE}}

    monkeypatch.setattr(vps, "Runtime", FakeRuntime)
    monkeypatch.setattr(vps, "vector_image_state", lambda _: "resume")
    monkeypatch.setattr(vps, "check_space", lambda _: None)
    monkeypatch.setattr(vps, "compose", lambda *_args, **_kwargs: (PG_IMAGE + "\n").encode())

    def fake_run(command, **_kwargs):
        if command[:3] == ["docker", "image", "inspect"]:
            return b"[{}]"
        if command[-2:] == ["-u", "postgres"]:
            return b"999"
        if command[-1] == "--version":
            return b"postgres (PostgreSQL) 18.6"
        assert "vector--0.8.6.sql" in command[-1]
        assert "default_version" in command[-1]
        raise vps.OperationError("command_failed")

    monkeypatch.setattr(vps, "run", fake_run)
    with pytest.raises(vps.OperationError, match="command_failed"):
        vps.stage_vector_image("a" * 40, pull=False)


@pytest.mark.parametrize("preserved", [True, False])
def test_vector_upgrade_orders_backup_switch_manifest_and_extension(tmp_path, monkeypatch, preserved):
    state = tmp_path / ".postgres"
    backups = state / "backups"
    backups.mkdir(parents=True)
    record_path = backups / "record.json"
    record_path.write_text("synthetic")
    monkeypatch.setattr(vps, "STATE", state)
    monkeypatch.setattr(vps, "private_file", lambda path: Path(path).read_bytes())
    events = []
    runtime = {"image": PG_PREVIOUS_IMAGE, "extension": False}
    before = {"learning_state": "unchanged"}

    class FakeRuntime:
        def __init__(self, revision, *, target_override=None, db_image=PG_IMAGE):
            self.db_image = db_image

        def require_stopped_writers(self):
            events.append("writers_stopped")

        def require_stopped_search_worker(self):
            events.append("search_stopped")

        def verify_database_container(self):
            assert runtime["image"] == self.db_image
            events.append("verify_image")

        def identity(self):
            return {"cluster": "synthetic-cluster"}

        def manifest(self):
            events.append("manifest")
            return before if preserved else {"learning_state": "changed"}

        def container(self, service):
            return {"Config": {"Image": runtime["image"]}}

        def pg(self, command, **kwargs):
            assert kwargs.get("input_file") is not None
            events.append("extension_bootstrap")
            runtime["extension"] = True

    def compose(command, **kwargs):
        assert command[:3] == ["up", "-d", "--no-deps"]
        events.append("switch_image")
        runtime["image"] = PG_IMAGE

    monkeypatch.setattr(vps, "Runtime", FakeRuntime)
    monkeypatch.setattr(vps, "load_state", lambda: {"cluster": "synthetic-cluster"})
    monkeypatch.setattr(vps, "app_target", lambda: "synthetic-private-dsn")
    monkeypatch.setattr(vps, "vector_image_state", lambda _: "previous")
    monkeypatch.setattr(vps, "stage_vector_image", lambda _revision, *, pull: events.append("staged") if not pull else None)
    monkeypatch.setattr(vps, "run", lambda *_args, **_kwargs: b"[{}]")
    monkeypatch.setattr(vps, "compose", compose)
    monkeypatch.setattr(vps, "backup", lambda _: events.append("verified_backup") or record_path)
    monkeypatch.setattr(vps, "read_verified_record", lambda _: {
        "before": before, "source": {"cluster": "synthetic-cluster"}})
    monkeypatch.setattr(vps, "vector_extension_status", lambda _: runtime["extension"])

    if preserved:
        assert vps.upgrade_vector_image("a" * 40) == record_path
        assert events.index("staged") < events.index("verified_backup")
        assert events.index("writers_stopped") < events.index("verified_backup")
        assert events.index("search_stopped") < events.index("verified_backup")
        assert events.index("verified_backup") < events.index("switch_image")
        assert events.index("switch_image") < events.index("extension_bootstrap")
        assert vps.vector_upgrade_record()["phase"] == "complete"
    else:
        with pytest.raises(vps.OperationError, match="user_state_mismatch"):
            vps.upgrade_vector_image("a" * 40)
        assert "extension_bootstrap" not in events
        assert vps.vector_upgrade_record()["phase"] == "switching"


def test_resume_after_image_switch_uses_existing_verified_backup(tmp_path, monkeypatch):
    state = tmp_path / ".postgres"
    backups = state / "backups"
    backups.mkdir(parents=True)
    backup_path = backups / "record.json"
    backup_path.write_text("synthetic")
    before = {"learning_state": "unchanged"}
    monkeypatch.setattr(vps, "STATE", state)
    monkeypatch.setattr(vps, "private_file", lambda path: Path(path).read_bytes())
    vps.write_record(vps.vector_upgrade_path(), {
        "format": vps.VECTOR_UPGRADE_FORMAT, "phase": "switching",
        "revision": "a" * 40, "cluster": "synthetic-cluster",
        "previous_image": PG_PREVIOUS_IMAGE, "candidate_image": PG_IMAGE,
        "backup_path": str(backup_path), "before": before,
    })
    calls = []
    extension = {"ready": False}

    class FakeRuntime:
        def __init__(self, revision, *, target_override=None, db_image=PG_IMAGE):
            self.db_image = db_image

        def require_stopped_writers(self):
            calls.append("stopped")

        def require_stopped_search_worker(self):
            calls.append("search_stopped")

        def container(self, service):
            return {"Config": {"Image": PG_IMAGE}}

        def verify_database_container(self):
            calls.append("verified")

        def identity(self):
            return {"cluster": "synthetic-cluster"}

        def manifest(self):
            return before

        def pg(self, command, **kwargs):
            calls.append("bootstrap")
            extension["ready"] = True

    monkeypatch.setattr(vps, "Runtime", FakeRuntime)
    monkeypatch.setattr(vps, "load_state", lambda: {"cluster": "synthetic-cluster"})
    monkeypatch.setattr(vps, "app_target", lambda: "synthetic-private-dsn")
    monkeypatch.setattr(vps, "vector_image_state", lambda _: "resume")
    monkeypatch.setattr(vps, "stage_vector_image", lambda _revision, *, pull: calls.append("staged") if not pull else None)
    monkeypatch.setattr(vps, "read_verified_record", lambda _: {
        "before": before, "source": {"cluster": "synthetic-cluster"}})
    monkeypatch.setattr(vps, "vector_extension_status", lambda _: extension["ready"])
    monkeypatch.setattr(vps, "backup", lambda _: pytest.fail("backup must not repeat on resume"))
    monkeypatch.setattr(vps, "compose", lambda *_args, **_kwargs: pytest.fail("image must not switch twice"))

    assert vps.upgrade_vector_image("a" * 40) == backup_path
    assert calls.count("bootstrap") == 1
    assert calls.count("search_stopped") == 1
    assert vps.vector_upgrade_record()["phase"] == "complete"
