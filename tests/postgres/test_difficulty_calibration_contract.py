from contextlib import closing

import pytest

from app.database import DatabaseError
from app.db import get_connection
from app.difficulty_calibration import report
from tests.test_difficulty_calibration import (
    test_independent_first_answer_isolated_by_actor_and_captured_edition,
)


def test_report_runs_in_postgres_read_only_transaction(bank):
    with closing(get_connection(bank)) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        assert report(conn)["items"]
        with pytest.raises(DatabaseError):
            conn.execute("UPDATE questions SET difficulty=difficulty WHERE id=1")
