import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .settings import settings


def sqlite_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("DATABASE_URL must use sqlite:/// for the MVP")

    raw_path = database_url.removeprefix("sqlite:///")
    return Path(raw_path).expanduser()


def get_connection() -> sqlite3.Connection:
    database_path = sqlite_path_from_url(settings.database_url)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


def initialize_database() -> None:
    database_path = sqlite_path_from_url(settings.database_url)
    if database_path.parent != Path("."):
        database_path.parent.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).resolve().parent / "schema.sql"
    with db_connection() as connection:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        run_migrations(connection)
        connection.commit()


def column_exists(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column["name"] == column_name for column in columns)


def run_migrations(connection: sqlite3.Connection) -> None:
    if not column_exists(connection, "timeline_entries", "system_generated"):
        connection.execute(
            """
            ALTER TABLE timeline_entries
            ADD COLUMN system_generated INTEGER NOT NULL DEFAULT 0
            """
        )
    if not column_exists(connection, "opportunity_shares", "deleted_at"):
        connection.execute(
            """
            ALTER TABLE opportunity_shares
            ADD COLUMN deleted_at TEXT
            """
        )
    normalize_legacy_timestamps(connection)
    backfill_opportunity_created_entries(connection)


# Columns written before timestamps were canonicalized hold a mix of
# "YYYY-MM-DD HH:MM:SS" (SQLite CURRENT_TIMESTAMP) and "YYYY-MM-DDTHH:MM"
# (browser datetime-local) values, which sort and compare incorrectly against
# each other. Rewrite them to fixed-width UTC ISO-8601.
LEGACY_TIMESTAMP_COLUMNS = [
    ("timeline_entries", "event_timestamp"),
    ("timeline_entries", "created_at"),
    ("notes", "created_at"),
    ("notes", "updated_at"),
    ("comments", "created_at"),
    ("opportunities", "created_at"),
    ("opportunities", "updated_at"),
    ("note_versions", "created_at"),
    ("audit_log_entries", "created_at"),
    ("notifications", "created_at"),
]


def normalize_legacy_timestamps(connection: sqlite3.Connection) -> None:
    for table_name, column_name in LEGACY_TIMESTAMP_COLUMNS:
        # strftime returns NULL for values it cannot parse, so unreadable rows
        # are left untouched rather than replaced with NULL.
        connection.execute(
            f"""
            UPDATE {table_name}
            SET {column_name} = strftime('%Y-%m-%dT%H:%M:%SZ', {column_name})
            WHERE {column_name} IS NOT NULL
                AND strftime('%Y-%m-%dT%H:%M:%SZ', {column_name}) IS NOT NULL
                AND {column_name} <> strftime('%Y-%m-%dT%H:%M:%SZ', {column_name})
            """
        )


def backfill_opportunity_created_entries(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO timeline_entries (
            opportunity_id,
            type,
            title,
            body,
            event_timestamp,
            created_by,
            system_generated,
            created_at
        )
        SELECT
            opportunities.id,
            'other',
            'Opportunity created',
            opportunities.name || ' was created for ' || opportunities.account_name || '.',
            opportunities.created_at,
            opportunities.owner_id,
            1,
            opportunities.created_at
        FROM opportunities
        WHERE opportunities.deleted_at IS NULL
            AND NOT EXISTS (
                SELECT 1
                FROM timeline_entries
                WHERE timeline_entries.opportunity_id = opportunities.id
                    AND timeline_entries.system_generated = 1
                    AND timeline_entries.title = 'Opportunity created'
                    AND timeline_entries.deleted_at IS NULL
            )
        """
    )
