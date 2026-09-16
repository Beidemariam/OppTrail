import sqlite3

from .time_utils import utc_now


def create_system_timeline_entry(
    connection: sqlite3.Connection,
    opportunity_id: int,
    created_by: int,
    entry_type: str,
    title: str,
    body: str,
) -> None:
    now = utc_now()
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
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (opportunity_id, entry_type, title, body, now, created_by, now),
    )
