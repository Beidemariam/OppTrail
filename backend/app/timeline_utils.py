import sqlite3


def create_system_timeline_entry(
    connection: sqlite3.Connection,
    opportunity_id: int,
    created_by: int,
    entry_type: str,
    title: str,
    body: str,
) -> None:
    connection.execute(
        """
        INSERT INTO timeline_entries (
            opportunity_id,
            type,
            title,
            body,
            event_timestamp,
            created_by,
            system_generated
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, 1)
        """,
        (opportunity_id, entry_type, title, body, created_by),
    )
