"""Database boundary: qmark parameters and rows shared by SQLite and PostgreSQL.

SQL dialect differences belong at the query/schema call sites. This module only
adapts DB-API parameter markers, row access, transactions and safe error types.
No database selection, migration or fallback happens after a connection fails.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg.pq import TransactionStatus


class DatabaseError(Exception):
    def __init__(self, sqlstate: str | None = None):
        self.sqlstate = sqlstate
        # Driver messages can contain the DSN, SQL or data values.
        super().__init__(f"PostgreSQL operation failed (SQLSTATE {sqlstate or 'unavailable'})")


class IntegrityError(DatabaseError):
    pass


class OperationalError(DatabaseError):
    pass


DATABASE_ERRORS = (sqlite3.DatabaseError, DatabaseError)
INTEGRITY_ERRORS = (sqlite3.IntegrityError, IntegrityError)
OPERATIONAL_ERRORS = (sqlite3.OperationalError, OperationalError)


def _safe_error(error: psycopg.Error) -> DatabaseError:
    if isinstance(error, psycopg.IntegrityError):
        return IntegrityError(error.sqlstate)
    if isinstance(error, (psycopg.OperationalError, psycopg.InterfaceError)) or error.sqlstate in {"55P03", "40P01", "40001"}:
        return OperationalError(error.sqlstate)
    return DatabaseError(error.sqlstate)


def is_postgres_target(target: str | Path) -> bool:
    return str(target).lower().startswith(("postgresql://", "postgres://"))


def validate_postgres_target(target: str) -> str:
    try:
        parsed = urlsplit(target)
        valid = (parsed.scheme in {"postgresql", "postgres"} and parsed.hostname
                 and parsed.username and parsed.path not in {"", "/"}
                 and not parsed.fragment and (parsed.port is None or 1 <= parsed.port <= 65535))
    except ValueError:
        valid = False
    if not valid or any(ord(character) < 32 for character in target):
        raise ValueError("DATABASE_URL must identify an explicit PostgreSQL host, user and database")
    return target


def resolve_database_target(*, require_sqlite_path: bool = False) -> str:
    """DATABASE_URL takes precedence; an invalid explicit value never falls back."""
    target = os.environ.get("DATABASE_URL", "").strip()
    if target:
        return validate_postgres_target(target)
    path = os.environ.get("DB_PATH", "").strip()
    if require_sqlite_path and not path:
        raise ValueError("DB_PATH or DATABASE_URL is required")
    if "://" in path:
        raise ValueError("DB_PATH is a SQLite path; use DATABASE_URL for PostgreSQL")
    return path or "/data/quiz.sqlite3"


def postgres_parameters(statement: str) -> str:
    """Convert qmarks outside quoted text/comments; escape literal psycopg %.

    Accept the existing qmark SQL contract, including quoted identifiers,
    dollar-quoted bodies and nested comments. Values are always passed separately.
    PostgreSQL JSON '?' operators are outside this application's qmark contract.
    """
    pieces = []
    index = 0
    while index < len(statement):
        start = index
        character = statement[index]
        if character in {"'", '"'}:
            quote = character
            index += 1
            while index < len(statement):
                if statement[index] == quote:
                    index += 1
                    if index < len(statement) and statement[index] == quote:
                        index += 1
                        continue
                    break
                index += 1
            else:
                raise ValueError("Unterminated SQL quote")
        elif statement.startswith("--", index):
            end = statement.find("\n", index)
            index = len(statement) if end < 0 else end + 1
        elif statement.startswith("/*", index):
            depth = 1
            index += 2
            while depth and index < len(statement):
                if statement.startswith("/*", index):
                    depth += 1
                    index += 2
                elif statement.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise ValueError("Unterminated SQL comment")
        elif character == "$" and (match := re.match(r"\$(?:[A-Za-z_]\w*)?\$", statement[index:])):
            tag = match.group()
            end = statement.find(tag, index + len(tag))
            if end < 0:
                raise ValueError("Unterminated dollar-quoted SQL")
            index = end + len(tag)
        elif character == "?":
            pieces.append("%s")
            index += 1
            continue
        else:
            index += 1
        pieces.append(statement[start:index].replace("%", "%%"))
    return "".join(pieces)


class PostgresRow:
    """Keep index/iteration and mapping access used by the existing domain."""
    def __init__(self, names, values):
        self._names, self._values = names, tuple(values)

    def __getitem__(self, key):
        return self._values[self._names.index(key) if isinstance(key, str) else key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return self._names


def _row_factory(cursor):
    names = tuple(column.name for column in cursor.description or ())
    return lambda values: PostgresRow(names, values)


class PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def fetchone(self):
        try:
            return self._cursor.fetchone()
        except psycopg.Error as error:
            raise _safe_error(error) from None

    def fetchall(self):
        try:
            return self._cursor.fetchall()
        except psycopg.Error as error:
            raise _safe_error(error) from None

    def __iter__(self):
        while (row := self.fetchone()) is not None:
            yield row


class PostgresConnection:
    backend = "postgresql"

    def __init__(self, target: str):
        validate_postgres_target(target)
        raw = None
        try:
            raw = psycopg.connect(target, autocommit=True, row_factory=_row_factory,
                                  connect_timeout=10, application_name="psychology-quiz")
            raw.execute("SET TIME ZONE 'UTC'")
            raw.execute("SET lock_timeout = '10s'")
            raw.autocommit = False
        except psycopg.Error as error:
            if raw is not None:
                raw.close()
            raise _safe_error(error) from None
        self._connection = raw

    @property
    def in_transaction(self):
        return self._connection.info.transaction_status != TransactionStatus.IDLE

    def execute(self, statement: str, parameters=None):
        try:
            cursor = self._connection.execute(
                postgres_parameters(statement) if parameters is not None else statement,
                parameters,
            )
            return PostgresCursor(cursor)
        except psycopg.Error as error:
            raise _safe_error(error) from None

    def executemany(self, statement: str, parameters):
        try:
            cursor = self._connection.cursor()
            cursor.executemany(postgres_parameters(statement), parameters)
            return PostgresCursor(cursor)
        except psycopg.Error as error:
            raise _safe_error(error) from None

    def commit(self):
        try:
            self._connection.commit()
        except psycopg.Error as error:
            raise _safe_error(error) from None

    def rollback(self):
        try:
            self._connection.rollback()
        except psycopg.Error as error:
            raise _safe_error(error) from None

    def close(self):
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        # Match the existing caller-owned SQLite context: transaction, not close.
        if error_type is None:
            try:
                self.commit()
            except DatabaseError:
                self.rollback()
                raise
        else:
            self.rollback()
        return False


Connection = sqlite3.Connection | PostgresConnection
Row = sqlite3.Row | PostgresRow


def is_postgres(connection: Connection) -> bool:
    return isinstance(connection, PostgresConnection)


def begin_write(connection: Connection, scope: str | None = None) -> None:
    if is_postgres(connection):
        if scope is not None:
            key = int.from_bytes(hashlib.sha256(("psychology:" + scope).encode()).digest()[:8], signed=True)
            connection.execute("SELECT pg_advisory_xact_lock(?)", (key,))
        elif not connection.in_transaction:
            connection.execute("BEGIN")
    elif not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")


def timestamp_sql(connection: Connection) -> str:
    # Retain the existing UTC text representation for exact import/API parity.
    if is_postgres(connection):
        return "to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')"
    return "CURRENT_TIMESTAMP"


def connect_database(target: str | Path) -> Connection:
    if is_postgres_target(target):
        return PostgresConnection(str(target))
    if "://" in str(target):
        raise ValueError("Unsupported database target")
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000;")
    connection.execute("PRAGMA synchronous = NORMAL;")
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection
