import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config

from alembic import command

from .settings import settings

BASELINE_REVISION = "0001_baseline"

# WAL lets readers proceed while a write is in flight, which is the only
# contention this deployment generates (ADR 0001). It is a property of the
# database file, so re-asserting it per connection is a no-op after the first.
# The busy timeout is per connection and must be set every time.
SQLITE_BUSY_TIMEOUT_MS = 5000


def sqlite_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("DATABASE_URL must use sqlite:/// for the MVP")

    raw_path = database_url.removeprefix("sqlite:///")
    return Path(raw_path).expanduser()


def sqlalchemy_url() -> str:
    """The configured database as a SQLAlchemy URL, for Alembic's engine.

    Alembic and the application must resolve to the same file, so this is
    derived from the same `settings.database_url` the raw `sqlite3` connections
    use rather than configured separately in `alembic.ini`.
    """
    return f"sqlite:///{sqlite_path_from_url(settings.database_url)}"


def get_connection() -> sqlite3.Connection:
    database_path = sqlite_path_from_url(settings.database_url)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    return connection


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def read_only_connection() -> Iterator[sqlite3.Connection]:
    """A connection SQLite itself refuses every write on.

    Brief §2.1 requires the AI agent's data access to be unable to mutate state
    *by construction* rather than by convention, and a reviewer noticing that
    `ai_service` only contains SELECTs is convention. `PRAGMA query_only` is
    enforced inside SQLite: an INSERT, UPDATE or DELETE on this connection
    raises `sqlite3.OperationalError` no matter what the calling code, the
    prompt, or the model's answer says.

    It is a pragma rather than a `mode=ro` URI because the database runs in WAL
    (ADR 0001), and a `mode=ro` connection cannot create the `-shm` file that
    WAL needs when no writer happens to be connected — which would turn "ask
    the agent a question" into an intermittent failure.
    """
    connection = get_connection()
    connection.execute("PRAGMA query_only = ON")
    try:
        yield connection
    finally:
        connection.close()


def alembic_config() -> Config:
    """Alembic configuration built without depending on the process's cwd.

    The application starts from whatever directory uvicorn was launched in, so
    `script_location` is resolved from this file rather than from `alembic.ini`.
    """
    backend_dir = Path(__file__).resolve().parent.parent
    config = Config(backend_dir / "alembic.ini")
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    return config


def initialize_database() -> None:
    """Bring the configured database to the latest revision.

    New installs get the whole schema from the baseline revision, so there is
    still no setup step. Databases that predate Alembic are repaired once and
    stamped (see `bridge_pre_alembic_database`).
    """
    database_path = sqlite_path_from_url(settings.database_url)
    if database_path.parent != Path("."):
        database_path.parent.mkdir(parents=True, exist_ok=True)

    config = alembic_config()
    with db_connection() as connection:
        needs_stamp = _is_pre_alembic_database(connection)
        if needs_stamp:
            bridge_pre_alembic_database(connection)
            connection.commit()

    if needs_stamp:
        command.stamp(config, BASELINE_REVISION)
    command.upgrade(config, "head")


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def column_exists(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(column["name"] == column_name for column in columns)


def _is_pre_alembic_database(connection: sqlite3.Connection) -> bool:
    """True for a populated database that Alembic has never versioned."""
    return table_exists(connection, "users") and not table_exists(connection, "alembic_version")


def bridge_pre_alembic_database(connection: sqlite3.Connection) -> None:
    """One-time repair of a database created before Alembic existed.

    Everything here used to run on every startup, scanning every row each boot
    (ADR 0002). It only ever had work to do on a database written by the
    pre-canonical MVP code, so it now runs once, immediately before the database
    is stamped at the baseline revision, and never again.
    """
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
# "YYYY-MM-DD HH:MM:SS" (SQLite CURRENT_TIMESTAMP), "YYYY-MM-DDTHH:MM" (browser
# datetime-local) and offset-suffixed values, which sort and compare incorrectly
# against each other. Rewrite them to fixed-width UTC ISO-8601. `users` and
# `sessions` are included because the repair now runs once instead of on every
# boot, so a row left alone here stays non-canonical for good.
LEGACY_TIMESTAMP_COLUMNS = [
    ("users", "created_at"),
    ("sessions", "created_at"),
    ("sessions", "expires_at"),
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
