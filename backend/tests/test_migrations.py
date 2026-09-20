"""Migration coverage: upgrade from empty, and upgrade from an MVP-era database.

Brief §6.1 asks for both paths. The second matters more: a real installation's
`data/app.db` predates Alembic, predates `opportunity_shares.deleted_at`, and
was written with `CURRENT_TIMESTAMP` defaults (`app/schema.sql` at commit
acac885), so it carries non-canonical timestamps that the old startup path
rewrote on every boot. `tests/data/mvp_schema.sql` is that schema, verbatim.
"""

import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import CsrfClient

from app.database import (
    column_exists,
    db_connection,
    initialize_database,
    sqlite_path_from_url,
)
from app.main import app
from app.settings import settings

DATA_DIR = Path(__file__).resolve().parent / "data"
CANONICAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# The revision `alembic upgrade head` is expected to land on. Written down
# rather than read from the script directory, for the same reason
# `expected_schema.sql` is: a new revision should have to say so here.
HEAD_REVISION = "0004_saved_views"


@pytest.fixture
def database_url(tmp_path: Path) -> Iterator[str]:
    """Point the app at a scratch database and put the old value back.

    These tests build the database themselves instead of using the `client`
    fixture, so they own the setting for their duration.
    """
    original = settings.database_url
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    settings.database_url = url
    try:
        yield url
    finally:
        settings.database_url = original


def normalized_schema(connection: sqlite3.Connection) -> list[str]:
    """Every object in the database as collapsed, comparable DDL."""
    rows = connection.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    return [collapse(row["sql"]) for row in rows]


def collapse(statement: str) -> str:
    return re.sub(r"\s+", " ", statement.replace(" IF NOT EXISTS", "")).strip()


def expected_schema() -> list[str]:
    text = DATA_DIR.joinpath("expected_schema.sql").read_text(encoding="utf-8")
    without_comments = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("--")
    )
    # Statements are separated by a blank line rather than by every semicolon:
    # a trigger body holds semicolons of its own (revision 0002_search_index).
    chunks = re.split(r";\n\s*\n", without_comments)
    statements = [chunk.strip().rstrip(";") for chunk in chunks if chunk.strip()]
    return sorted(collapse(statement) for statement in statements)


def build_mvp_database(url: str) -> None:
    """A populated database exactly as the pre-Alembic code would have left it."""
    path = sqlite_path_from_url(url)
    connection = sqlite3.connect(path)
    connection.executescript(DATA_DIR.joinpath("mvp_schema.sql").read_text(encoding="utf-8"))
    # Commit acac885 predates `system_generated`; the pre-Alembic
    # `run_migrations()` added it with a guarded ALTER, so a database from that
    # era is missing it too.
    connection.execute("ALTER TABLE timeline_entries DROP COLUMN system_generated")
    connection.executescript(
        """
        INSERT INTO users (id, email, password_hash, name, created_at)
        VALUES (1, 'legacy@example.com', 'hash', 'Legacy Owner', '2026-01-04 09:15:00');

        INSERT INTO opportunities (
            id, name, account_name, value, currency, stage, owner_id,
            created_at, updated_at
        )
        VALUES (
            1, 'Legacy Deal', 'Legacy Account', '1000', 'USD', 'Prospecting', 1,
            '2026-01-04 09:16:00', '2026-01-04 09:16:00'
        );

        INSERT INTO timeline_entries (
            id, opportunity_id, type, title, body, event_timestamp, created_by, created_at
        )
        VALUES (
            1, 1, 'call', 'Discovery call', 'Budget discussed',
            '2026-01-05T14:30', 1, '2026-01-05 14:31:00'
        );

        INSERT INTO notes (id, entry_id, body, created_by, created_at, updated_at)
        VALUES (1, 1, 'Follow up in a week', 1, '2026-01-05 14:32:00', '2026-01-05 14:32:00');

        INSERT INTO comments (id, note_id, body, created_by, created_at)
        VALUES (1, 1, 'Agreed', 1, '2026-01-05 14:33:00');
        """
    )
    connection.commit()
    connection.close()


def timestamps(connection: sqlite3.Connection, table: str, column: str) -> list[str]:
    rows = connection.execute(f"SELECT {column} AS value FROM {table}").fetchall()
    return [row["value"] for row in rows if row["value"] is not None]


def test_upgrade_from_empty_produces_the_expected_schema(database_url: str) -> None:
    initialize_database()

    with db_connection() as connection:
        schema = normalized_schema(connection)
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert revision["version_num"] == HEAD_REVISION
    # alembic_version is Alembic's bookkeeping, not part of the app's schema.
    assert sorted(item for item in schema if "alembic_version" not in item) == expected_schema()


def test_upgrade_from_empty_is_idempotent(database_url: str) -> None:
    initialize_database()
    first = sqlite_path_from_url(database_url).read_bytes()

    initialize_database()

    with db_connection() as connection:
        revisions = connection.execute("SELECT version_num FROM alembic_version").fetchall()

    assert [row["version_num"] for row in revisions] == [HEAD_REVISION]
    assert len(first) > 0


def test_upgrade_from_an_mvp_database_repairs_and_stamps_it(database_url: str) -> None:
    build_mvp_database(database_url)

    initialize_database()

    with db_connection() as connection:
        assert column_exists(connection, "timeline_entries", "system_generated")
        assert column_exists(connection, "opportunity_shares", "deleted_at")

        # Stamped at the baseline, then carried up to head by the same call.
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        assert revision["version_num"] == HEAD_REVISION

        # Legacy rows are rewritten into the canonical fixed-width UTC format.
        assert timestamps(connection, "opportunities", "created_at") == ["2026-01-04T09:16:00Z"]
        assert timestamps(connection, "timeline_entries", "event_timestamp") == [
            "2026-01-05T14:30:00Z",
            # The backfilled "Opportunity created" entry, stamped from the
            # opportunity's own (now canonical) created_at.
            "2026-01-04T09:16:00Z",
        ]
        assert timestamps(connection, "notes", "created_at") == ["2026-01-05T14:32:00Z"]
        assert timestamps(connection, "comments", "created_at") == ["2026-01-05T14:33:00Z"]

        # Existing data survives the upgrade.
        assert timestamps(connection, "users", "email") == ["legacy@example.com"]
        note = connection.execute("SELECT body FROM notes WHERE id = 1").fetchone()
        assert note["body"] == "Follow up in a week"


def test_mvp_backfill_creates_one_system_entry_per_opportunity(database_url: str) -> None:
    """The v1 backfill still runs for legacy rows, and still only once."""
    build_mvp_database(database_url)

    initialize_database()
    initialize_database()

    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT title, system_generated
            FROM timeline_entries
            WHERE opportunity_id = 1 AND system_generated = 1 AND deleted_at IS NULL
            """
        ).fetchall()

    assert [row["title"] for row in rows] == ["Opportunity created"]


def test_legacy_repair_runs_once_rather_than_on_every_startup(database_url: str) -> None:
    """The repair is a one-shot migration, not a boot-time scan of every row.

    It used to run on every startup (ADR 0002). Proving it no longer does is
    what makes the explicit-timestamp writes below load bearing: nothing repairs
    a non-canonical value after the bridge has run.
    """
    build_mvp_database(database_url)
    initialize_database()

    with db_connection() as connection:
        connection.execute(
            "UPDATE opportunities SET created_at = '2026-02-01 08:00:00' WHERE id = 1"
        )
        connection.commit()

    initialize_database()

    with db_connection() as connection:
        assert timestamps(connection, "opportunities", "created_at") == ["2026-02-01 08:00:00"]


def test_writes_to_a_bridged_legacy_database_are_canonical(database_url: str) -> None:
    """A legacy database keeps its `CURRENT_TIMESTAMP` column defaults.

    `ALTER TABLE` cannot rewrite a default, so the bridge leaves them in place.
    Application code therefore supplies every timestamp itself rather than
    letting the column default decide the format.
    """
    build_mvp_database(database_url)

    with CsrfClient(app) as client:
        signup = client.post(
            "/api/auth/signup",
            json={"email": "new@example.com", "password": "password123", "name": "New User"},
        )
        assert signup.status_code == 201
        opportunity = client.post(
            "/api/opportunities",
            json={
                "name": "Expansion",
                "account_name": "Acme",
                "value": "25000",
                "currency": "USD",
                "stage": "Prospecting",
            },
        )
        assert opportunity.status_code == 201
        opportunity_id = opportunity.json()["id"]
        entry = client.post(
            f"/api/opportunities/{opportunity_id}/timeline",
            json={
                "type": "call",
                "title": "Discovery call",
                "body": "Budget discussed",
                "event_timestamp": "2026-09-01T10:00:00",
            },
        )
        assert entry.status_code == 201
        note = client.post(
            f"/api/timeline/{entry.json()['id']}/notes",
            json={"body": "Note body"},
        )
        assert note.status_code == 201
        note_id = note.json()["id"]
        assert (
            client.patch(f"/api/notes/{note_id}", json={"body": "Edited body"}).status_code == 200
        )
        assert (
            client.post(f"/api/notes/{note_id}/comments", json={"body": "A comment"}).status_code
            == 201
        )
        share = client.post(
            f"/api/opportunities/{opportunity_id}/shares",
            json={"email": "legacy@example.com", "role": "editor"},
        )
        assert share.status_code == 201

    written = [
        ("users", "created_at"),
        ("sessions", "created_at"),
        ("sessions", "expires_at"),
        ("opportunities", "created_at"),
        ("opportunities", "updated_at"),
        ("opportunity_shares", "created_at"),
        ("timeline_entries", "created_at"),
        ("timeline_entries", "event_timestamp"),
        ("notes", "created_at"),
        ("notes", "updated_at"),
        ("note_versions", "created_at"),
        ("comments", "created_at"),
        ("notifications", "created_at"),
        ("audit_log_entries", "created_at"),
    ]
    with db_connection() as connection:
        for table, column in written:
            values = timestamps(connection, table, column)
            assert values, f"{table}.{column} has no rows to check"
            for value in values:
                assert CANONICAL.match(value), f"{table}.{column} = {value!r}"
