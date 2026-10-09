"""The one place user data is deleted, and the one place it comes back.

Nothing in `AGENTS.md`'s data model is ever removed from the database: a
`deleted_at` stamp is written and cascaded down the opportunity → entry → note →
comment tree, and every read filters `deleted_at IS NULL` at each level. Routes
call the helpers here instead of writing their own `UPDATE ... SET deleted_at`,
so the cascade is defined once and a new delete path cannot quietly forget a
level of the tree.

The `restore_*` half (milestone 2.4b) is what makes Undo a real
`deleted_at = NULL` rather than a re-create with a new id. Each cascade stamps
one timestamp across everything it takes, so a restore can ask for exactly that
stamp back and leave anything deleted separately alone — which is why the
restore helpers take the stamp as an argument rather than reading it again.

`tests/test_soft_delete.py` fails the build if any module in `app/` issues a
`DELETE FROM` against one of `USER_DATA_TABLES`.
"""

import sqlite3

from .time_utils import utc_now

# Tables holding user data, which is soft-deleted and never removed.
# `sessions` is deliberately absent: a session is ephemeral authentication
# state, not user content, and logging out really does delete the row.
# `reactions` and `watchers` (milestone 3.3a) are absent for the same reason:
# each row is "I am currently reacting/watching", toggle state a person sets
# and unsets, not content whose history is worth keeping (D-130). Their
# routes (`routes_timeline.py`, `routes_sharing.py`) do write ordinary
# `DELETE FROM` against them.
USER_DATA_TABLES = (
    "users",
    "opportunities",
    "opportunity_shares",
    "timeline_entries",
    "timeline_entry_versions",
    "notes",
    "note_versions",
    "opportunity_versions",
    "comments",
    "notifications",
    "audit_log_entries",
    "saved_views",
    # A task is content, not toggle state (milestone 4.1): somebody wrote it
    # down and a colleague may be relying on it, so deleting one is a soft
    # delete with an audit row and an Undo. Completing one is not a delete at
    # all -- `completed_at` is a field, and a done task stays readable.
    "tasks",
    # A task's discussion is content as well (milestone 4.5): immutable like
    # every other comment here, and soft-deleted like every other thing a
    # person wrote.
    "task_comments",
    # An attachment is content too (milestone 4.3): somebody uploaded the
    # contract and a colleague may be about to read it, so deleting one is a
    # soft delete with an audit row and an Undo. **The file on disk is never
    # removed** (**D-149**) -- the row can come back, and a content-addressed
    # blob may be shared with a row nobody deleted.
    "attachments",
)


def soft_delete_comment(connection: sqlite3.Connection, comment_id: int) -> None:
    """Delete one comment, and the replies under it if it started a thread.

    Threading (milestone 3.3) added a level to the tree this module cascades
    down, and it is the same rule as every other level: a reply is readable
    only through the comment it answers, so leaving it behind would leave an
    answer to a question nobody can see. Replies take the parent's stamp, so
    one Undo brings the whole thread back.
    """
    deleted_at = utc_now()
    connection.execute(
        "UPDATE comments SET deleted_at = ? WHERE parent_id = ? AND deleted_at IS NULL",
        (deleted_at, comment_id),
    )
    connection.execute(
        "UPDATE comments SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
        (deleted_at, comment_id),
    )


def soft_delete_task(connection: sqlite3.Connection, task_id: int) -> None:
    """Delete one task, and the discussion on it (milestone 4.1, 4.5).

    `FEATURES.md` §8 rules out subtasks, so a task had no cascade at all until
    comments arrived -- and a comment is readable only through the task it is
    on, which is the same rule every other level of this tree follows.
    """
    deleted_at = utc_now()
    connection.execute(
        "UPDATE task_comments SET deleted_at = ? WHERE task_id = ? AND deleted_at IS NULL",
        (deleted_at, task_id),
    )
    connection.execute(
        "UPDATE tasks SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
        (deleted_at, task_id),
    )


def restore_task(connection: sqlite3.Connection, task_id: int, deleted_at: str) -> None:
    """Undo one `soft_delete_task`, discussion included, scoped by the stamp
    like every restore here -- so a comment deleted on its own an hour earlier
    carries a different stamp and stays deleted."""
    connection.execute(
        "UPDATE task_comments SET deleted_at = NULL WHERE task_id = ? AND deleted_at = ?",
        (task_id, deleted_at),
    )
    connection.execute(
        "UPDATE tasks SET deleted_at = NULL WHERE id = ? AND deleted_at = ?",
        (task_id, deleted_at),
    )


def soft_delete_task_comment(connection: sqlite3.Connection, comment_id: int) -> None:
    """Delete one line of a task's discussion (milestone 4.5)."""
    connection.execute(
        "UPDATE task_comments SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
        (utc_now(), comment_id),
    )


def restore_task_comment(
    connection: sqlite3.Connection,
    comment_id: int,
    deleted_at: str,
) -> None:
    """Undo one `soft_delete_task_comment`, scoped by the stamp."""
    connection.execute(
        "UPDATE task_comments SET deleted_at = NULL WHERE id = ? AND deleted_at = ?",
        (comment_id, deleted_at),
    )


def soft_delete_attachment(connection: sqlite3.Connection, attachment_id: int) -> None:
    """Delete one attachment (milestone 4.3).

    Nothing hangs off an attachment and nothing is unlinked from disk
    (**D-149**): this stamps the row, and the bytes stay where the digest says
    they are. A delete that removed the file could not be undone, and the
    digest it addresses may be another entry's attachment as well.
    """
    connection.execute(
        "UPDATE attachments SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
        (utc_now(), attachment_id),
    )


def restore_attachment(connection: sqlite3.Connection, attachment_id: int, deleted_at: str) -> None:
    """Undo one `soft_delete_attachment`, scoped by the stamp like every
    restore here."""
    connection.execute(
        "UPDATE attachments SET deleted_at = NULL WHERE id = ? AND deleted_at = ?",
        (attachment_id, deleted_at),
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
    # Attachments are a level of this tree (milestone 4.3): a file is read
    # through the entry it was attached to and has nowhere else to appear, so
    # leaving it live would leave a document reachable with no context. Unlike
    # a task, which outlives the entry that prompted it because an action item
    # is a fact about the deal rather than about the entry.
    connection.execute(
        "UPDATE attachments SET deleted_at = ? WHERE entry_id = ? AND deleted_at IS NULL",
        (deleted_at, entry_id),
    )
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


def soft_delete_saved_view(connection: sqlite3.Connection, view_id: int) -> None:
    connection.execute(
        "UPDATE saved_views SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
        (utc_now(), view_id),
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
        UPDATE attachments
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
    # Tasks are a level of this tree too (milestone 4.1), and their discussions
    # with them (4.5). Missing the tasks would leave live action items pointing
    # at a deleted deal, and My Tasks reads across opportunities -- so they
    # would keep appearing on somebody's list for a deal that is gone.
    connection.execute(
        """
        UPDATE task_comments
        SET deleted_at = ?
        WHERE deleted_at IS NULL
            AND task_id IN (SELECT id FROM tasks WHERE opportunity_id = ?)
        """,
        (deleted_at, opportunity_id),
    )
    connection.execute(
        """
        UPDATE tasks
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


def restore_timeline_entry(connection: sqlite3.Connection, entry_id: int, deleted_at: str) -> None:
    """Undo one `soft_delete_timeline_entry`, and only it.

    A cascade stamps a single `deleted_at` value across the tree it takes, so
    "what did this delete remove" is answerable afterwards: the children
    carrying that exact stamp. Restoring on the stamp rather than on the parent
    id is what leaves a note deleted an hour earlier deleted.
    """
    connection.execute(
        """
        UPDATE comments
        SET deleted_at = NULL
        WHERE deleted_at = ?
            AND note_id IN (SELECT id FROM notes WHERE entry_id = ?)
        """,
        (deleted_at, entry_id),
    )
    connection.execute(
        "UPDATE notes SET deleted_at = NULL WHERE entry_id = ? AND deleted_at = ?",
        (entry_id, deleted_at),
    )
    connection.execute(
        "UPDATE attachments SET deleted_at = NULL WHERE entry_id = ? AND deleted_at = ?",
        (entry_id, deleted_at),
    )
    connection.execute(
        "UPDATE timeline_entries SET deleted_at = NULL WHERE id = ? AND deleted_at = ?",
        (entry_id, deleted_at),
    )


def restore_note(connection: sqlite3.Connection, note_id: int, deleted_at: str) -> None:
    """Undo one `soft_delete_note`, and only it."""
    connection.execute(
        "UPDATE comments SET deleted_at = NULL WHERE note_id = ? AND deleted_at = ?",
        (note_id, deleted_at),
    )
    connection.execute(
        "UPDATE notes SET deleted_at = NULL WHERE id = ? AND deleted_at = ?",
        (note_id, deleted_at),
    )


def restore_comment(connection: sqlite3.Connection, comment_id: int, deleted_at: str) -> None:
    """Undo one `soft_delete_comment`, replies included.

    Scoped by the stamp like every other restore: a reply deleted separately
    an hour earlier carries a different one and stays deleted.
    """
    connection.execute(
        "UPDATE comments SET deleted_at = NULL WHERE parent_id = ? AND deleted_at = ?",
        (comment_id, deleted_at),
    )
    connection.execute(
        "UPDATE comments SET deleted_at = NULL WHERE id = ? AND deleted_at = ?",
        (comment_id, deleted_at),
    )


def restore_opportunity(
    connection: sqlite3.Connection,
    opportunity_id: int,
    deleted_at: str,
) -> None:
    """Undo one `soft_delete_opportunity`, and only it.

    `updated_at` moves to now rather than back to its pre-delete value: the
    delete overwrote it, and the record really did change again here.
    """
    connection.execute(
        """
        UPDATE comments
        SET deleted_at = NULL
        WHERE deleted_at = ?
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
        SET deleted_at = NULL
        WHERE deleted_at = ?
            AND entry_id IN (SELECT id FROM timeline_entries WHERE opportunity_id = ?)
        """,
        (deleted_at, opportunity_id),
    )
    connection.execute(
        """
        UPDATE attachments
        SET deleted_at = NULL
        WHERE deleted_at = ?
            AND entry_id IN (SELECT id FROM timeline_entries WHERE opportunity_id = ?)
        """,
        (deleted_at, opportunity_id),
    )
    connection.execute(
        """
        UPDATE timeline_entries
        SET deleted_at = NULL
        WHERE opportunity_id = ? AND deleted_at = ?
        """,
        (opportunity_id, deleted_at),
    )
    connection.execute(
        """
        UPDATE opportunity_shares
        SET deleted_at = NULL
        WHERE opportunity_id = ? AND deleted_at = ?
        """,
        (opportunity_id, deleted_at),
    )
    connection.execute(
        """
        UPDATE task_comments
        SET deleted_at = NULL
        WHERE deleted_at = ?
            AND task_id IN (SELECT id FROM tasks WHERE opportunity_id = ?)
        """,
        (deleted_at, opportunity_id),
    )
    connection.execute(
        """
        UPDATE tasks
        SET deleted_at = NULL
        WHERE opportunity_id = ? AND deleted_at = ?
        """,
        (opportunity_id, deleted_at),
    )
    connection.execute(
        """
        UPDATE opportunities
        SET deleted_at = NULL, updated_at = ?
        WHERE id = ? AND deleted_at = ?
        """,
        (utc_now(), opportunity_id, deleted_at),
    )
