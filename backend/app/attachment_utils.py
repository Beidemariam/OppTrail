"""Reading an attachment row (milestone 4.3).

The SQL and the row mapper live here rather than in `routes_attachments.py`
because three callers read them: the attachment routes themselves, the timeline
read that sends an entry's files along with it (`routes_timeline`), and the PDF
export's manifest. `audit_utils.py` and `timeline_utils.py` exist for the same
reason -- a helper module beside the routers rather than a service layer.

Nothing here resolves a permission. Every caller has already established who is
asking: the routes through `permissions.py`, the timeline read through the gate
on the page it belongs to.
"""

import sqlite3

from .schemas import AttachmentPublic

# Every read of an attachment carries the name it is displayed with and the
# opportunity its permission is resolved against, the way every other row here
# does.
# `visibility` and the entry's author ride along since R.1b: a file hangs off
# an entry (D-148), so "may this person read this file" is "may this person
# read that entry" -- and the download route is the one place in the app where
# bytes leave the volume.
ATTACHMENT_ROWS_SQL = """
    SELECT
        attachments.*,
        timeline_entries.opportunity_id AS opportunity_id,
        timeline_entries.visibility AS entry_visibility,
        timeline_entries.created_by AS entry_author_id,
        users.name AS uploader_name
    FROM attachments
    JOIN timeline_entries ON timeline_entries.id = attachments.entry_id
    JOIN opportunities ON opportunities.id = timeline_entries.opportunity_id
    JOIN users ON users.id = attachments.uploaded_by
"""


def attachment_from_row(row: sqlite3.Row) -> AttachmentPublic:
    return AttachmentPublic(
        id=row["id"],
        entry_id=row["entry_id"],
        sha256=row["sha256"],
        filename=row["filename"],
        content_type=row["content_type"],
        byte_size=row["byte_size"],
        uploaded_by=row["uploaded_by"],
        uploader_name=row["uploader_name"],
        created_at=row["created_at"],
    )


def attachments_by_entry_id(
    connection: sqlite3.Connection,
    entry_ids: list[int],
) -> dict[int, list[AttachmentPublic]]:
    """Every attachment on the given entries, one query for the whole set.

    The shape `reactions_by_comment_id` already uses, for the same reason: a
    page of entries costs one more round trip rather than one per card.
    """
    if not entry_ids:
        return {}
    placeholders = ",".join("?" for _ in entry_ids)
    rows = connection.execute(
        f"""
        {ATTACHMENT_ROWS_SQL}
        WHERE attachments.deleted_at IS NULL
            AND attachments.entry_id IN ({placeholders})
        ORDER BY attachments.created_at ASC, attachments.id ASC
        """,
        entry_ids,
    ).fetchall()
    grouped: dict[int, list[AttachmentPublic]] = {}
    for row in rows:
        grouped.setdefault(row["entry_id"], []).append(attachment_from_row(row))
    return grouped
