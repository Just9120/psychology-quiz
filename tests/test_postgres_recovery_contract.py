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

    existing = deepcopy(after)
    existing["tables"]["future_user_state"]["rows"] = 0
    changed = deepcopy(existing)
    changed["tables"]["future_user_state"] = {"rows": 1, "sha256": "changed"}
    with pytest.raises(ValueError, match="pre-existing user state"):
        verify_user_state(existing, changed)
    with pytest.raises(ValueError, match="pre-existing user state"):
        verify_user_state(existing, before)
