from contextlib import nullcontext
import json

import pytest

from app import deletion_journal as journal


class Transaction:
    status = "in progress"

    def execute(self, statement, parameters=None):
        self.result = ("psychology_test",)
        if "pg_xact_status" in statement:
            self.result = (self.status,)
        elif "pg_current_xact_id" in statement:
            self.result = ("517",)
        return self

    def fetchone(self):
        return self.result

    def commit(self):
        self.status = "committed"


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    # Linux CI's native PostgreSQL rehearsal also exercises real permissions,
    # fsync and the inter-process lock. Keep the state machine test portable.
    monkeypatch.setattr(journal, "_locked", lambda directory: nullcontext())
    monkeypatch.setattr(journal, "_check_private", lambda *args: None)
    monkeypatch.setattr(journal, "_sync_directory", lambda directory: None)
    monkeypatch.setattr(journal, "is_postgres", lambda conn: True)
    directory = tmp_path / "journal"
    monkeypatch.setenv("LEARNING_DELETION_JOURNAL", str(directory))
    journal.initialize(directory, cluster="1234", database="psychology_test")
    return directory, Transaction()


def test_confirm_and_reconcile_unknown_post_commit(fixture, monkeypatch):
    directory, conn = fixture
    point = journal.recovery_records(directory, conn, cluster="1234")
    write = journal._write

    def interrupt(directory, state):
        if state["events"][-1]["status"] == "committed":
            raise OSError("interrupted")
        write(directory, state)

    with monkeypatch.context() as failure:
        failure.setattr(journal, "_write", interrupt)
        with pytest.raises(OSError, match="interrupted"):
            with journal.recorded_deletion(conn, 7654321):
                assert conn.status == "in progress"

    state, actors = journal.recovery_records(directory, conn, cluster="1234", point=point)
    assert actors == {journal.actor_digest(state, 7654321)}
    assert "7654321" not in (directory / "journal.json").read_text()
    after = journal.recovery_records(directory, conn, cluster="1234")
    assert journal.recovery_records(directory, conn, cluster="1234", point=after)[1] == set()


def test_pending_aborted_and_truncated_journal(fixture):
    directory, conn = fixture
    point = journal.recovery_records(directory, conn, cluster="1234")
    with pytest.raises(RuntimeError, match="interrupted"):
        with journal.recorded_deletion(conn, 7654321):
            raise RuntimeError("interrupted")
    for status in ("in progress", None):
        conn.status = status
        with pytest.raises(journal.JournalError, match="unresolved"):
            journal.recovery_records(directory, conn, cluster="1234", point=point)
    conn.status = "aborted"
    assert not journal.recovery_records(directory, conn, cluster="1234", point=point)[1]
    after = journal.recovery_records(directory, conn, cluster="1234")
    with pytest.raises(journal.JournalError, match="cluster"):
        journal.recovery_records(directory, conn, cluster="9999", point=point)
    path = directory / "journal.json"
    document = json.loads(path.read_text())
    document["state"]["events"].clear()
    path.write_text(json.dumps(document))
    with pytest.raises(journal.JournalError, match="invalid_deletion_journal"):
        journal.recovery_records(directory, conn, cluster="1234", point=point)
    journal._write(directory, document["state"])
    with pytest.raises(journal.JournalError, match="point"):
        journal.recovery_records(directory, conn, cluster="1234", point=after)
