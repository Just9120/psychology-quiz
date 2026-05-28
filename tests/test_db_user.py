import sqlite3
import unittest

from app.db import create_or_load_user


def _setup_schema(conn: sqlite3.Connection) -> None:
    with open("sql/schema.sql", "r", encoding="utf-8") as schema_file:
        conn.executescript(schema_file.read())


class CreateOrLoadUserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        _setup_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_existing_user_with_same_profile_does_not_touch_updated_at(self):
        create_or_load_user(self.conn, 1001, "user", "First", "Last")
        self.conn.execute(
            "UPDATE users SET updated_at = '2000-01-01 00:00:00' WHERE telegram_user_id = ?",
            (1001,),
        )
        before = self.conn.execute(
            "SELECT updated_at FROM users WHERE telegram_user_id = ?",
            (1001,),
        ).fetchone()["updated_at"]

        row = create_or_load_user(self.conn, 1001, "user", "First", "Last")

        self.assertEqual("2000-01-01 00:00:00", before)
        self.assertEqual(before, row["updated_at"])
        self.assertEqual("normal", row["reading_mode"])

    def test_existing_user_profile_change_is_persisted_and_touches_updated_at(self):
        create_or_load_user(self.conn, 1002, "old_user", "Old", "Name")
        self.conn.execute(
            "UPDATE users SET updated_at = '2000-01-01 00:00:00' WHERE telegram_user_id = ?",
            (1002,),
        )

        row = create_or_load_user(self.conn, 1002, "new_user", "New", "Person")

        self.assertEqual("new_user", row["username"])
        self.assertEqual("New", row["first_name"])
        self.assertEqual("Person", row["last_name"])
        self.assertNotEqual("2000-01-01 00:00:00", row["updated_at"])
        self.assertEqual("normal", row["reading_mode"])


if __name__ == "__main__":
    unittest.main()
