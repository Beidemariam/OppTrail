"""Attachments on a timeline entry (milestone 4.3, ADR 0008, `FEATURES.md` §6).

Proposals, quotes and contracts are the artifacts a deal actually turns on, and
until this milestone they lived in somebody's inbox instead of on the timeline.
Four routes: put a file on an entry, read it back, remove it, put it back.

What is decided here rather than in `uploads.py`:

- **A download is a read of the opportunity**, so it runs
  `require_opportunity_access` like every other read -- a viewer on a shared
  deal may download, and somebody who is not on the deal gets the ordinary 404.
  `/data` is never mounted as a static path (`main.py` serves only the frontend
  build), so this route is the *only* way bytes leave the volume.
- **The digest is not a capability.** `AttachmentPublic` carries `sha256` and
  the download route ignores it: the id names a row, the row's permission is
  resolved, and the digest is read from that row. Knowing a digest without
  access to its entry gets you nothing.
- **Uploading is adding, deleting is changing** -- the split D-005 draws
  everywhere else. An editor may attach a file to anyone's entry
  (`require_timeline_write`); removing one is the uploader's or the
  opportunity owner's (`require_delete_permission`).
- **An attachment has no PATCH**, so it has no version table: there is no field
  a person can rewrite. Replacing a document means attaching the new one, which
  is what a timeline is for -- and the old row stays readable rather than being
  overwritten.
"""

import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from .attachment_utils import ATTACHMENT_ROWS_SQL, attachment_from_row
from .audit_utils import create_audit_log_entry
from .auth import get_current_user
from .database import db_connection
from .events import publish_timeline_changed
from .notification_service import notify_shared_activity
from .permissions import (
    require_delete_permission,
    require_opportunity_access,
    require_timeline_write,
)
from .schemas import AttachmentPublic
from .settings import settings
from .soft_delete import restore_attachment, soft_delete_attachment
from .time_utils import utc_now
from .uploads import (
    attachments_dir,
    download_headers,
    resolve_stored_path,
    safe_filename,
    store_bytes,
    validate_upload,
)

router = APIRouter(prefix="/api/v2", tags=["attachments"])


def fetch_attachment(
    connection: sqlite3.Connection,
    attachment_id: int,
    *,
    deleted: bool = False,
) -> sqlite3.Row:
    """One attachment and the deal it hangs off, or 404.

    `deleted=True` is the restore path's mirror image: the row itself must be
    deleted and everything above it must not be, so a file cannot come back
    under an entry that is gone -- the rule every other restore here follows.
    """
    row: sqlite3.Row | None = connection.execute(
        f"""
        {ATTACHMENT_ROWS_SQL}
        WHERE attachments.id = ?
            AND attachments.deleted_at IS {"NOT NULL" if deleted else "NULL"}
            AND timeline_entries.deleted_at IS NULL
            AND opportunities.deleted_at IS NULL
        """,
        (attachment_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return row


@router.post(
    "/timeline/{entry_id}/attachments",
    response_model=AttachmentPublic,
    status_code=status.HTTP_201_CREATED,
)
def upload_attachment(
    entry_id: int,
    file: UploadFile = File(...),
    user: sqlite3.Row = Depends(get_current_user),
) -> AttachmentPublic:
    """Put a file on an entry. Editors may, viewers may not -- the same gate as
    adding a note, because this is adding something rather than changing
    somebody else's.

    What the client declared the file to be is never consulted: only the
    sniffed type decides, which is what makes a `.exe` renamed `.pdf` a 415.

    The read stops one byte past the limit, which is all `validate_upload` needs
    to answer 413. It is worth being precise about what that bounds
    (**D-153**): Starlette's multipart parser has already spooled the whole
    request before this `def` handler runs, so the cap refuses what gets
    *stored* rather than what gets *received*. Enforcing it while reading needs
    this app's first `async def` route handler; a request-size middleware in
    front of routing is the cheaper answer and is a cross-cutting control of
    its own. The residual is accepted the way ADR 0008 accepts the absence of
    virus scanning.
    """
    with db_connection() as connection:
        entry = connection.execute(
            """
            SELECT timeline_entries.id, timeline_entries.opportunity_id
            FROM timeline_entries
            JOIN opportunities ON opportunities.id = timeline_entries.opportunity_id
            WHERE timeline_entries.id = ?
                AND timeline_entries.deleted_at IS NULL
                AND opportunities.deleted_at IS NULL
            """,
            (entry_id,),
        ).fetchone()
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Timeline entry not found",
            )
        opportunity_id = int(entry["opportunity_id"])
        require_timeline_write(connection, opportunity_id, int(user["id"]))

        # Who is asking is settled before the bytes are looked at, so somebody
        # with no write access gets the answer about their access rather than
        # one about their file -- and nothing is hashed or stored for them.
        data = file.file.read(settings.max_upload_bytes + 1)
        upload = validate_upload(data)
        filename = safe_filename(file.filename or "")

        # The file lands on disk before the row is written, so a failed write
        # leaves an unreferenced blob rather than a row pointing at nothing --
        # and because the path is the content's own digest, the retry writes
        # the same bytes to the same place instead of a second copy.
        store_bytes(attachments_dir(), upload, data)

        cursor = connection.execute(
            """
            INSERT INTO attachments (
                entry_id, sha256, filename, content_type, byte_size, uploaded_by,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                upload.sha256,
                filename,
                upload.content_type,
                upload.size,
                int(user["id"]),
                utc_now(),
            ),
        )
        attachment_id = int(cursor.lastrowid or 0)

        # Told the way a note is: a document arriving on a shared deal is
        # activity on it, and `source_type` is what lets the inbox say which
        # kind of thing was added.
        notify_shared_activity(
            connection,
            opportunity_id,
            int(user["id"]),
            "attachment",
            attachment_id,
            f"New attachment: {filename}",
        )

        row = fetch_attachment(connection, attachment_id)
        connection.commit()

    # On the timeline, so `timeline.changed` rather than the broader
    # `opportunity.changed` a task publishes (D-143): this one really is an
    # entry's own content.
    publish_timeline_changed(opportunity_id)
    return attachment_from_row(row)


@router.get(
    "/attachments/{attachment_id}/download",
    response_class=FileResponse,
    responses={
        200: {
            "description": (
                "The file itself, as a download: `Content-Disposition: "
                "attachment` and `X-Content-Type-Options: nosniff`, with the "
                "sniffed content type recorded at upload."
            ),
            "content": {"application/octet-stream": {}},
        }
    },
)
def download_attachment(
    attachment_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> FileResponse:
    """Read the file. Any role on the deal may, including a viewer -- this is
    `require_opportunity_access`, the same gate as reading the timeline the
    file is attached to.

    The response is forced to download and marked `nosniff`
    (`uploads.download_headers`), so a file that got past the type allowlist
    still cannot be rendered as HTML in this app's origin. The filename the
    reader gets back is the one that was uploaded; the path it came from is the
    digest.
    """
    with db_connection() as connection:
        attachment = fetch_attachment(connection, attachment_id)
        require_opportunity_access(connection, int(attachment["opportunity_id"]), int(user["id"]))

    path = resolve_stored_path(attachments_dir(), attachment["sha256"])
    if not path.is_file():
        # The row says there is a file and the volume disagrees, which is a
        # real state rather than a hypothetical one: the database is backed up
        # (ADR 0011) and the blobs are not yet (Phase R, R.5), so a restored
        # database can name files this volume has never held. A 404 says so;
        # letting the response fail while it is being sent is a 500 that names
        # nothing.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment file is missing",
        )

    # The headers carry the content type, so `media_type` is left alone:
    # Starlette only fills one in when the header is absent, and the type here
    # is the sniffed one from upload rather than a guess from the path -- which
    # is a bare digest with no extension to guess from.
    return FileResponse(
        path,
        headers=download_headers(attachment["filename"], attachment["content_type"]),
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    """Take a file off an entry: its uploader or the opportunity owner (D-005).

    Soft, audited and undoable like every other delete -- and **the bytes stay
    on disk** (**D-149**), because the row can come back and the digest may be
    another entry's attachment as well.
    """
    with db_connection() as connection:
        attachment = fetch_attachment(connection, attachment_id)
        opportunity_id = int(attachment["opportunity_id"])
        require_delete_permission(
            connection,
            opportunity_id,
            int(user["id"]),
            attachment["uploaded_by"],
            "Only the uploader or the opportunity owner can delete this attachment",
        )

        soft_delete_attachment(connection, attachment_id)
        create_audit_log_entry(
            connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            action="attachment_deleted",
            detail={
                "attachment_id": attachment_id,
                "entry_id": int(attachment["entry_id"]),
                "filename": attachment["filename"],
                "byte_size": int(attachment["byte_size"]),
            },
        )
        connection.commit()

    publish_timeline_changed(opportunity_id)


@router.post("/attachments/{attachment_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_deleted_attachment(
    attachment_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    """Undo the delete (milestone 2.4b's shape), scoped by the delete's own
    stamp: a file deleted with its entry comes back with the entry, and one
    deleted on its own comes back here.

    Restoring something that is not deleted is a 404, the same answer as one
    that never existed, and the restore writes its own audit row rather than
    removing the delete's -- the log is the sequence of what happened.
    """
    with db_connection() as connection:
        attachment = fetch_attachment(connection, attachment_id, deleted=True)
        opportunity_id = int(attachment["opportunity_id"])
        require_delete_permission(
            connection,
            opportunity_id,
            int(user["id"]),
            attachment["uploaded_by"],
            "Only the uploader or the opportunity owner can restore this attachment",
        )

        restore_attachment(connection, attachment_id, attachment["deleted_at"])
        create_audit_log_entry(
            connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            action="attachment_restored",
            detail={
                "attachment_id": attachment_id,
                "entry_id": int(attachment["entry_id"]),
                "filename": attachment["filename"],
                "byte_size": int(attachment["byte_size"]),
            },
        )
        connection.commit()

    publish_timeline_changed(opportunity_id)
