"""A notebook of one's own, beside a deal (milestone R.1b).

The second half of the human's "build both" ruling. A sealed entry keeps a
*moment* to its author inside the deal's history; this keeps a *running note*
out of that history altogether — the thing a rep writes about a deal that is
not a record of anything that happened on it.

Three properties it has by construction rather than by rule:

- **Nobody else ever reads it.** Both routes resolve the row by
  `(opportunity_id, user_id)`, so there is no id a caller could supply that
  reaches somebody else's notebook. That is stronger than a permission check,
  in the spirit of `AGENTS.md` invariant 2.
- **Nothing else reads it either.** It is absent from search, the export, the
  AI's context, the activity log, every aggregate and every notification —
  not by exclusion, but because no query outside this module mentions the
  table. A grep for `private_notes` is the whole audit.
- **It needs the deal, not a role.** `require_opportunity_access` gates both
  routes: anyone who may open the deal may keep notes on it, including a
  viewer, because a note about a deal is a fact about the reader rather than a
  write to the record.
"""

import sqlite3

from fastapi import APIRouter, Depends

from .auth import get_current_user
from .database import db_connection
from .permissions import require_opportunity_access
from .schemas import PrivateNotePublic, PrivateNoteUpdate
from .time_utils import utc_now

router = APIRouter(prefix="/api/v2/opportunities", tags=["private-notes"])


@router.get("/{opportunity_id}/private-note", response_model=PrivateNotePublic)
def read_private_note(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> PrivateNotePublic:
    """This reader's notebook for this deal, empty if they have never written
    one — an empty notebook and no notebook are the same thing to read, so
    there is no 404 branch and no "create" route."""
    with db_connection() as connection:
        require_opportunity_access(connection, opportunity_id, int(user["id"]))
        row = connection.execute(
            """
            SELECT body, updated_at
            FROM private_notes
            WHERE opportunity_id = ? AND user_id = ? AND deleted_at IS NULL
            """,
            (opportunity_id, int(user["id"])),
        ).fetchone()

    return PrivateNotePublic(
        opportunity_id=opportunity_id,
        body=row["body"] if row else "",
        updated_at=row["updated_at"] if row else None,
    )


@router.put("/{opportunity_id}/private-note", response_model=PrivateNotePublic)
def write_private_note(
    opportunity_id: int,
    payload: PrivateNoteUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> PrivateNotePublic:
    """Write the whole notebook.

    `PUT`, not `PATCH`: there is one field and the client holds all of it, so
    a partial update would be a partial update of a single string. Clearing it
    to empty is how a notebook is emptied — the row stays, which keeps the
    unique index honest and costs nothing.

    No version history and no audit row. Invariant 8 is about *a record
    somebody else relies on* ("attributed to who changed it"); there is no
    second reader here to be surprised by a change, and keeping every draft of
    a private note would be the opposite of the feature.
    """
    now = utc_now()
    with db_connection() as connection:
        require_opportunity_access(connection, opportunity_id, int(user["id"]))
        connection.execute(
            """
            INSERT INTO private_notes (opportunity_id, user_id, body, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (opportunity_id, user_id) WHERE deleted_at IS NULL
            DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at
            """,
            (opportunity_id, int(user["id"]), payload.body, now, now),
        )
        connection.commit()

    return PrivateNotePublic(
        opportunity_id=opportunity_id,
        body=payload.body,
        updated_at=now,
    )
