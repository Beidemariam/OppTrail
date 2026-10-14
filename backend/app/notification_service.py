import json
import re
import sqlite3
from collections.abc import Iterable
from typing import cast

from .schemas import NOTIFICATION_PAYLOAD_MODELS, NotificationPayload
from .time_utils import utc_now

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
        INSERT INTO notifications (user_id, type, payload, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, notification_type, json.dumps(payload, sort_keys=True), utc_now()),
    )


def parse_notification_payload(notification_type: str, raw_payload: str) -> NotificationPayload:
    model = NOTIFICATION_PAYLOAD_MODELS[notification_type]
    return cast(NotificationPayload, model.model_validate_json(raw_payload))


def mark_notification_read(
    connection: sqlite3.Connection,
    notification_id: int,
    user_id: int,
) -> sqlite3.Row | None:
    """Mark one notification read, scoped to its owner.

    `read` and `read_at` are written together so v1's column (read-only from
    this point on, per the notification-model breaking change in
    `docs/ROADMAP.md`) and v2's history stay in agreement without v1's own
    code having to change. `COALESCE` makes a second call idempotent: the
    first read time wins, not the most recent PATCH.
    """
    connection.execute(
        """
        UPDATE notifications
        SET read = 1, read_at = COALESCE(read_at, ?)
        WHERE id = ? AND user_id = ?
        """,
        (utc_now(), notification_id, user_id),
    )
    connection.commit()
    row: sqlite3.Row | None = connection.execute(
        "SELECT * FROM notifications WHERE id = ? AND user_id = ?",
        (notification_id, user_id),
    ).fetchone()
    return row


def mark_all_notifications_read(connection: sqlite3.Connection, user_id: int) -> int:
    """Mark every unread notification for a user read; returns the count."""
    cursor = connection.execute(
        """
        UPDATE notifications
        SET read = 1, read_at = ?
        WHERE user_id = ? AND read_at IS NULL
        """,
        (utc_now(), user_id),
    )
    connection.commit()
    return cursor.rowcount


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


def get_watcher_user_ids(
    connection: sqlite3.Connection,
    opportunity_id: int,
) -> set[int]:
    """Everyone following this opportunity (milestone 3.3a), shared on it or
    not -- `docs/FEATURES.md` §7's "follow an opportunity you are not shared
    on" is exactly the set `get_accessible_user_ids` cannot include.
    """
    rows = connection.execute(
        "SELECT user_id FROM watchers WHERE opportunity_id = ?",
        (opportunity_id,),
    ).fetchall()
    return {int(row["user_id"]) for row in rows}


def notify_shared_activity(
    connection: sqlite3.Connection,
    opportunity_id: int,
    actor_id: int,
    source_type: str,
    source_id: int,
    title: str,
) -> None:
    """Every accessible user, plus every watcher (milestone 3.3a) -- the
    union is what makes watching without a share notify at all: a watcher is
    additive to who already gets told, never a narrower filter over them.
    """
    recipients = get_accessible_user_ids(connection, opportunity_id) | get_watcher_user_ids(
        connection, opportunity_id
    )
    for user_id in recipients:
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
    recipient_ids: Iterable[int],
    actor_id: int,
    opportunity_id: int,
    comment_id: int,
) -> None:
    """Tell the people a comment is addressed to that it was written.

    A set rather than one id since milestone 3.3: a reply is addressed to the
    author of the comment it answers as well as to the note's author, and
    when those are the same person that is still one notification. Nobody is
    told about their own comment.
    """
    for recipient_id in sorted(set(recipient_ids)):
        if recipient_id == actor_id:
            continue
        create_notification(
            connection,
            recipient_id,
            "comment",
            {
                "opportunity_id": opportunity_id,
                "source_type": "comment",
                "source_id": comment_id,
                "actor_id": actor_id,
            },
        )


def withdraw_entry_notifications(
    connection: sqlite3.Connection,
    entry_id: int,
    keep_user_id: int,
) -> int:
    """Take back what a now-sealed entry already told people (milestone R.1b).

    The human's ruling: *"even when sealed after the fact, withdraw any
    notification related to it."* This is the half of privacy that is not a
    read predicate — a notification is a *copy*, written into somebody's inbox
    at the moment of the write, carrying the entry's title, and read back
    without re-checking anything against the deal. Nothing a query does later
    can unsay it.

    So the rows are stamped `deleted_at` and stop being served. A soft delete,
    not a hard one: `notifications` is in `soft_delete.USER_DATA_TABLES` and
    `AGENTS.md` invariant 5 says nothing here is ever removed — a rule worth
    more than the handful of bytes a withdrawn row costs. What the reader
    loses is the notification; what the database keeps is the record that one
    was sent, which is the same bargain every other delete in this app makes.

    `keep_user_id` is the author: their own copy says they wrote it, which is
    true, theirs, and about an entry they can still read.

    Mentions ride on the same mechanism: `notify_mentions` writes one row per
    mentioned person with the same `source_type`/`source_id`, so they go too.
    """
    cursor = connection.execute(
        """
        UPDATE notifications
        SET deleted_at = ?
        WHERE deleted_at IS NULL
            AND user_id != ?
            AND json_extract(payload, '$.source_type') = 'entry'
            AND json_extract(payload, '$.source_id') = ?
        """,
        (utc_now(), keep_user_id, entry_id),
    )
    return int(cursor.rowcount)
