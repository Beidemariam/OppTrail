import json
import re
import sqlite3

MENTION_RE = re.compile(r"@([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def extract_mentioned_emails(text: str) -> list[str]:
    emails: list[str] = []
    for match in MENTION_RE.findall(text):
        email = match.lower()
        if email not in emails:
            emails.append(email)
    return emails


def create_notification(
    connection: sqlite3.Connection,
    user_id: int,
    notification_type: str,
    payload: dict[str, object],
) -> None:
    connection.execute(
        """
        INSERT INTO notifications (user_id, type, payload)
        VALUES (?, ?, ?)
        """,
        (user_id, notification_type, json.dumps(payload, sort_keys=True)),
    )


def get_accessible_user_ids(
    connection: sqlite3.Connection,
    opportunity_id: int,
) -> set[int]:
    rows = connection.execute(
        """
        SELECT owner_id AS user_id
        FROM opportunities
        WHERE id = ? AND deleted_at IS NULL
        UNION
        SELECT user_id
        FROM opportunity_shares
        WHERE opportunity_id = ? AND deleted_at IS NULL
        """,
        (opportunity_id, opportunity_id),
    ).fetchall()
    return {int(row["user_id"]) for row in rows}


def notify_mentions(
    connection: sqlite3.Connection,
    opportunity_id: int,
    actor_id: int,
    body: str,
    source_type: str,
    source_id: int,
) -> None:
    emails = extract_mentioned_emails(body)
    if not emails:
        return

    placeholders = ",".join("?" for _ in emails)
    users = connection.execute(
        f"""
        SELECT id, email
        FROM users
        WHERE lower(email) IN ({placeholders})
        """,
        emails,
    ).fetchall()
    accessible_ids = get_accessible_user_ids(connection, opportunity_id)

    for user in users:
        user_id = int(user["id"])
        if user_id == actor_id or user_id not in accessible_ids:
            continue
        create_notification(
            connection,
            user_id,
            "mention",
            {
                "opportunity_id": opportunity_id,
                "source_type": source_type,
                "source_id": source_id,
                "actor_id": actor_id,
                "email": user["email"],
            },
        )


def notify_shared_activity(
    connection: sqlite3.Connection,
    opportunity_id: int,
    actor_id: int,
    source_type: str,
    source_id: int,
    title: str,
) -> None:
    for user_id in get_accessible_user_ids(connection, opportunity_id):
        if user_id == actor_id:
            continue
        create_notification(
            connection,
            user_id,
            "shared_activity",
            {
                "opportunity_id": opportunity_id,
                "source_type": source_type,
                "source_id": source_id,
                "actor_id": actor_id,
                "title": title,
            },
        )


def notify_note_comment(
    connection: sqlite3.Connection,
    note_owner_id: int,
    actor_id: int,
    opportunity_id: int,
    comment_id: int,
) -> None:
    if note_owner_id == actor_id:
        return
    create_notification(
        connection,
        note_owner_id,
        "comment",
        {
            "opportunity_id": opportunity_id,
            "source_type": "comment",
            "source_id": comment_id,
            "actor_id": actor_id,
        },
    )
