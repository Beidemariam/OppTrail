"""The one place user data is deleted.

Nothing in `AGENTS.md`'s data model is ever removed from the database: a
`deleted_at` stamp is written and cascaded down the opportunity → entry → note →
comment tree, and every read filters `deleted_at IS NULL` at each level. Routes
call the helpers here instead of writing their own `UPDATE ... SET deleted_at`,
so the cascade is defined once and a new delete path cannot quietly forget a
level of the tree.

`tests/test_soft_delete.py` fails the build if any module in `app/` issues a
`DELETE FROM` against one of `USER_DATA_TABLES`.
"""

import sqlite3

from .time_utils import utc_now

# Tables holding user data, which is soft-deleted and never removed.
# `sessions` is deliberately absent: a session is ephemeral authentication
# state, not user content, and logging out really does delete the row.
USER_DATA_TABLES = (
    "users",
    "opportunities",
    "opportunity_shares",
    "timeline_entries",
    "notes",
    "note_versions",
    "comments",
    "notifications",
    "audit_log_entries",
)


def soft_delete_comment(connection: sqlite3.Connection, comment_id: int) -> None:
    connection.execute(
        "UPDATE comments SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
        (utc_now(), comment_id),
    )


def soft_delete_note(connection: sqlite3.Connection, note_id: int) -> None:
    deleted_at = utc_now()
    connection.execute(
        "UPDATE comments SET deleted_at = ? WHERE note_id = ? AND deleted_at IS NULL",
        (deleted_at, note_id),
    )
    connection.execute(
        "UPDATE notes SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
        (deleted_at, note_id),
    )


def soft_delete_timeline_entry(connection: sqlite3.Connection, entry_id: int) -> None:
    deleted_at = utc_now()
    connection.execute(
        """
        UPDATE comments
        SET deleted_at = ?
        WHERE deleted_at IS NULL
            AND note_id IN (SELECT id FROM notes WHERE entry_id = ?)
        """,
        (deleted_at, entry_id),
    )
    connection.execute(
        "UPDATE notes SET deleted_at = ? WHERE entry_id = ? AND deleted_at IS NULL",
        (deleted_at, entry_id),
    )
    connection.execute(
        "UPDATE timeline_entries SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
        (deleted_at, entry_id),
    )


def soft_delete_share(connection: sqlite3.Connection, opportunity_id: int, user_id: int) -> None:
    connection.execute(
        """
        UPDATE opportunity_shares
        SET deleted_at = ?
        WHERE opportunity_id = ? AND user_id = ? AND deleted_at IS NULL
        """,
        (utc_now(), opportunity_id, user_id),
    )


def soft_delete_opportunity(connection: sqlite3.Connection, opportunity_id: int) -> None:
    deleted_at = utc_now()
    connection.execute(
        """
        UPDATE comments
        SET deleted_at = ?
        WHERE deleted_at IS NULL
            AND note_id IN (
                SELECT notes.id
                FROM notes
                JOIN timeline_entries ON timeline_entries.id = notes.entry_id
                WHERE timeline_entries.opportunity_id = ?
            )
        """,
        (deleted_at, opportunity_id),
    )
    connection.execute(
        """
        UPDATE notes
        SET deleted_at = ?
        WHERE deleted_at IS NULL
            AND entry_id IN (SELECT id FROM timeline_entries WHERE opportunity_id = ?)
        """,
        (deleted_at, opportunity_id),
    )
    connection.execute(
        """
        UPDATE timeline_entries
        SET deleted_at = ?
        WHERE opportunity_id = ? AND deleted_at IS NULL
        """,
        (deleted_at, opportunity_id),
    )
    connection.execute(
        """
        UPDATE opportunity_shares
        SET deleted_at = ?
        WHERE opportunity_id = ? AND deleted_at IS NULL
        """,
        (deleted_at, opportunity_id),
    )
    connection.execute(
        """
        UPDATE opportunities
        SET deleted_at = ?, updated_at = ?
        WHERE id = ? AND deleted_at IS NULL
        """,
        (deleted_at, deleted_at, opportunity_id),
    )
