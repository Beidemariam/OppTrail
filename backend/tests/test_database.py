"""Connection-level SQLite settings (brief §4.4).

WAL and the busy timeout are the two halves of ADR 0001's concurrency answer:
WAL lets a reader proceed while a write is in flight, and the busy timeout makes
a writer that does have to wait retry instead of raising "database is locked"
immediately. Foreign keys are off by default in SQLite and have to be asserted
per connection, so all three belong to `get_connection()` and are checked here.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import database
from app.database import SQLITE_BUSY_TIMEOUT_MS, db_connection, sqlite_path_from_url
from app.settings import settings


def pragma(connection: sqlite3.Connection, name: str) -> object:
    return connection.execute(f"PRAGMA {name}").fetchone()[0]


def test_connections_use_wal_foreign_keys_and_a_busy_timeout(client: TestClient) -> None:
    with db_connection() as connection:
        assert pragma(connection, "journal_mode") == "wal"
        assert pragma(connection, "foreign_keys") == 1
        assert pragma(connection, "busy_timeout") == SQLITE_BUSY_TIMEOUT_MS


def test_foreign_keys_are_enforced_not_merely_declared(client: TestClient) -> None:
    with db_connection() as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
                INSERT INTO notes (entry_id, body, created_by, created_at, updated_at)
                VALUES (9999, 'orphan', 9999, '2026-09-16T00:00:00Z', '2026-09-16T00:00:00Z')
                """
        )


def test_wal_is_written_into_the_database_file(client: TestClient) -> None:
    """Journal mode is persistent state, which is why re-asserting it is cheap.

    A connection opened without `get_connection()` still reports WAL, so the
    mode was recorded in the file rather than only in the app's sessions.
    """
    outsider = sqlite3.connect(sqlite_path_from_url(settings.database_url))
    try:
        assert outsider.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        outsider.close()


def test_a_connection_that_cannot_be_set_up_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Milestone R.4, found by a `ResourceWarning`.

    Asserting WAL is a write, so `PRAGMA journal_mode = WAL` is the statement
    that fails on a read-only mount or a full disk — and it fails *inside*
    `get_connection`, before the caller has the object, so `db_connection`'s
    `finally` cannot close it. The container's HEALTHCHECK probes `/readyz`
    every 30 seconds, which made this a leaked file descriptor every 30
    seconds on exactly the deployment already in trouble.
    """

    class RefusesToSetUp:
        def __init__(self) -> None:
            self.closed = False
            self.row_factory: object = None

        def execute(self, statement: str) -> None:
            if "journal_mode" in statement:
                raise sqlite3.OperationalError("attempt to write a readonly database")

        def close(self) -> None:
            self.closed = True

    stand_in = RefusesToSetUp()
    monkeypatch.setattr(database.sqlite3, "connect", lambda *_args, **_kwargs: stand_in)

    with pytest.raises(sqlite3.OperationalError):
        database.get_connection()

    assert stand_in.closed, "the connection was left open when its setup failed"
