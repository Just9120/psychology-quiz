"""Synthetic preservation contract; no PostgreSQL service is required."""
from copy import deepcopy

import pytest

from app.postgres_recovery import verify_user_state


def _manifest():
    return {
        "format": "psychology-postgres-backup-v1",
        "columns": {"users": ["id"], "questions": ["id"]},
        "tables": {"users": {"rows": 1, "sha256": "user"},
                   "questions": {"rows": 1, "sha256": "content"}},
        "sequences": {"users": 1, "questions": 1},
        "import_manifest_sha256": "original-import",
    }


def test_preserves_any_existing_runtime_table_and_allows_content_rebuild():
    before = _manifest()
    after = deepcopy(before)
    after["tables"]["questions"] = {"rows": 2, "sha256": "rebuilt"}
    verify_user_state(before, after)

    after["columns"]["future_user_state"] = ["user_id"]
    after["tables"]["future_user_state"] = {"rows": 0, "sha256": "empty"}
    verify_user_state(before, after)
    after["tables"]["future_user_state"]["rows"] = 1
    with pytest.raises(ValueError, match="must be empty"):
        verify_user_state(before, after)
    after["tables"]["future_user_state"]["rows"] = 0
    after["sequences"]["future_user_state"] = 1
    with pytest.raises(ValueError, match="must be empty"):
        verify_user_state(before, after)

    existing = deepcopy(after)
    existing["tables"]["future_user_state"]["rows"] = 0
    existing["sequences"]["future_user_state"] = 0
    changed = deepcopy(existing)
    changed["tables"]["future_user_state"] = {"rows": 1, "sha256": "changed"}
    with pytest.raises(ValueError, match="pre-existing user state"):
        verify_user_state(existing, changed)
    with pytest.raises(ValueError, match="pre-existing user state"):
        verify_user_state(existing, before)


@pytest.mark.parametrize("sequence", [0, 2, None])
def test_content_rebuild_cannot_change_preexisting_user_identity_sequence(sequence):
    before = _manifest()
    after = deepcopy(before)
    after["sequences"]["questions"] = 9  # Content identity may be rebuilt.
    if sequence is None:
        del after["sequences"]["users"]
    else:
        after["sequences"]["users"] = sequence
    with pytest.raises(ValueError, match="changed a user identity sequence"):
        verify_user_state(before, after)


def test_content_rebuild_preserves_import_provenance():
    before = _manifest()
    after = deepcopy(before)
    after["import_manifest_sha256"] = "changed-import"
    with pytest.raises(ValueError, match="changed import provenance"):
        verify_user_state(before, after)
    del after["import_manifest_sha256"]
    with pytest.raises(ValueError, match="changed import provenance"):
        verify_user_state(before, after)
    legacy = deepcopy(before)
    del legacy["import_manifest_sha256"]
    verify_user_state(legacy, before)
