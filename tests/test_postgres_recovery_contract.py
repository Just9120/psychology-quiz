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


def reading_migration_manifests():
    from app.reading_schema import FIELDS, VERSION
    before = _manifest()
    before['columns']['user_literature_progress'] = ['id']
    before['tables']['user_literature_progress'] = {'rows': 2, 'sha256': 'unchanged-history'}
    before['reading_work_migration'] = {'version': VERSION, 'columns': list(FIELDS),
        'projection': {'rows': 1, 'sha256': 'a' * 64}, 'catalog_sha256': 'b' * 64}
    after = deepcopy(before)
    after['columns']['user_literature_work_progress'] = list(FIELDS)
    after['tables']['user_literature_work_progress'] = dict(before['reading_work_migration']['projection'])
    after['reading_work_catalog_sha256'] = 'b' * 64
    return before, after


def test_accepts_only_exact_derived_reading_state_and_keeps_history_check():
    before, after = reading_migration_manifests()
    verify_user_state(before, after)
    after['tables']['user_literature_progress']['sha256'] = 'changed'
    with pytest.raises(ValueError, match='pre-existing user state'):
        verify_user_state(before, after)


@pytest.mark.parametrize('tamper', ['digest', 'count', 'columns', 'catalog', 'proof', 'sequence', 'old-columns'])
def test_rejects_reading_derivation_tampering(tamper):
    before, after = reading_migration_manifests()
    table = 'user_literature_work_progress'
    if tamper == 'digest': after['tables'][table]['sha256'] = 'c' * 64
    elif tamper == 'count': after['tables'][table]['rows'] += 1
    elif tamper == 'columns': after['columns'][table].reverse()
    elif tamper == 'catalog': after['reading_work_catalog_sha256'] = 'c' * 64
    elif tamper == 'proof': del before['reading_work_migration']
    elif tamper == 'sequence': after['sequences'][table] = 1
    else:
        del before['columns']['user_literature_progress']
        del before['tables']['user_literature_progress']
    expected = 'must be empty' if tamper == 'old-columns' else 'verified legacy derivation'
    with pytest.raises(ValueError, match=expected):
        verify_user_state(before, after)
