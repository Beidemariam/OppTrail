import json
import sqlite3


def create_audit_log_entry(
    connection: sqlite3.Connection,
    opportunity_id: int,
    actor_id: int,
    action: str,
    detail: dict[str, object],
) -> None:
    connection.execute(
        """
        INSERT INTO audit_log_entries (opportunity_id, actor_id, action, detail)
        VALUES (?, ?, ?, ?)
        """,
        (opportunity_id, actor_id, action, json.dumps(detail, sort_keys=True)),
    )
