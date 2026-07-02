import sqlite3
import unittest

from app.db import ensure_user_literature_progress_table


def _setup_schema(conn: sqlite3.Connection) -> None:
    with open("sql/schema.sql", "r", encoding="utf-8") as schema_file:
        conn.executescript(schema_file.read())


class UserLiteratureProgressSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        _setup_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_schema_creates_required_columns_indexes_and_unique_constraint(self):
        columns = {
            row["name"]: row
            for row in self.conn.execute("PRAGMA table_info(user_literature_progress)").fetchall()
        }
        self.assertEqual(
            {
                "id",
                "user_id",
                "literature_id",
                "reading_status",
                "progress_percent",
                "started_at",
                "completed_at",
                "updated_at",
                "last_opened_at",
                "private_note",
                "remind_at",
            },
            set(columns),
        )
        self.assertEqual(1, columns["id"]["pk"])
        for required_column in ("user_id", "literature_id", "reading_status", "updated_at"):
            self.assertEqual(1, columns[required_column]["notnull"])

        indexes = {
            row["name"]
            for row in self.conn.execute("PRAGMA index_list(user_literature_progress)").fetchall()
        }
        self.assertIn("idx_user_literature_progress_user_id", indexes)
        self.assertIn("idx_user_literature_progress_reading_status", indexes)
        self.assertIn("idx_user_literature_progress_user_updated", indexes)
        self.assertTrue(any(name.startswith("sqlite_autoindex_user_literature_progress") for name in indexes))

    def test_runtime_migration_helper_is_idempotent_and_preserves_data(self):
        user_id = self._create_user()
        self.conn.execute(
            """
            INSERT INTO user_literature_progress (
                user_id, literature_id, reading_status, progress_percent, updated_at
            )
            VALUES (?, 'lit_1', 'in_progress', 25, '2026-07-02T00:00:00Z')
            """,
            (user_id,),
        )

        ensure_user_literature_progress_table(self.conn)
        ensure_user_literature_progress_table(self.conn)

        row = self.conn.execute(
            """
            SELECT reading_status, progress_percent, updated_at
            FROM user_literature_progress
            WHERE user_id = ? AND literature_id = 'lit_1'
            """,
            (user_id,),
        ).fetchone()
        self.assertEqual("in_progress", row["reading_status"])
        self.assertEqual(25, row["progress_percent"])
        self.assertEqual("2026-07-02T00:00:00Z", row["updated_at"])

    def test_valid_runtime_reading_statuses_are_accepted(self):
        user_id = self._create_user()
        for idx, status in enumerate(("not_started", "in_progress", "read", "revisit", "skipped"), start=1):
            self.conn.execute(
                """
                INSERT INTO user_literature_progress (
                    user_id, literature_id, reading_status, progress_percent, updated_at
                )
                VALUES (?, ?, ?, ?, '2026-07-02T00:00:00Z')
                """,
                (user_id, f"lit_{idx}", status, min(idx * 10, 100)),
            )

        count = self.conn.execute("SELECT COUNT(*) FROM user_literature_progress").fetchone()[0]
        self.assertEqual(5, count)

    def test_invalid_status_progress_and_empty_literature_id_are_rejected(self):
        user_id = self._create_user()
        invalid_rows = [
            (user_id, "lit_invalid_status", "approved", 10, "2026-07-02T00:00:00Z"),
            (user_id, "lit_negative_progress", "in_progress", -1, "2026-07-02T00:00:00Z"),
            (user_id, "lit_large_progress", "in_progress", 101, "2026-07-02T00:00:00Z"),
            (user_id, "   ", "in_progress", 10, "2026-07-02T00:00:00Z"),
        ]

        for row in invalid_rows:
            with self.assertRaises(sqlite3.IntegrityError):
                self.conn.execute(
                    """
                    INSERT INTO user_literature_progress (
                        user_id, literature_id, reading_status, progress_percent, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    row,
                )

    def test_unique_user_literature_pair_is_enforced(self):
        user_id = self._create_user()
        values = (user_id, "lit_1", "not_started", "2026-07-02T00:00:00Z")
        self.conn.execute(
            """
            INSERT INTO user_literature_progress (user_id, literature_id, reading_status, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            values,
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                """
                INSERT INTO user_literature_progress (user_id, literature_id, reading_status, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                values,
            )

    def _create_user(self) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO users (telegram_user_id, username, first_name, last_name)
            VALUES (12345, 'reader', 'Read', 'Er')
            """
        )
        return int(cursor.lastrowid)


if __name__ == "__main__":
    unittest.main()
