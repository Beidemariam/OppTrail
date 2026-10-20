"""Custom field definitions: the typed metadata behind ADR 0006.

Milestone 6.1. Like saved views, a definition is **not opportunity-scoped**,
so `permissions.py`'s owner/editor/viewer machinery does not apply -- but
unlike a saved view it is not personal either. A field changes the shape of
every record of its entity type, for everybody.

**Who may define one was D-171 and is now D-215.** `docs/FEATURES.md` §3
says "admin-defined"; this application had no admin, so D-171 read that as
*any authenticated user* -- the reversible direction, on the reasoning that
adding a gate later is a route change. The reviewer closed it at the Phase R
gate: *"both have to be done by the owner."* A definition has no opportunity
to own, so "the owner" is the deployment's, and
`permissions.require_admin` is the gate: the administrators are the addresses
in `ADMIN_EMAILS`.

**Reading stays open to every signed-in caller**, which is the half that
matters for the screens: the column picker, the filter bar and both forms
need the definitions, and "which fields does this team track" is not a
privileged question. What is gated is the four writes.

Archiving rather than deleting is the ADR's own requirement, and it is also
why there is no DELETE here: values stay in the JSON, the definition stops
being offered, and `custom_fields.visible_values` drops the orphaned keys on
read.
"""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .auth import get_current_user
from .custom_fields import DEFINITION_ROWS_SQL, definition_from_row
from .database import db_connection
from .pagination import Page, PageRequest, cursor_clause, page_params, split_page
from .permissions import require_admin
from .schemas import (
    CustomFieldCreate,
    CustomFieldEntity,
    CustomFieldPublic,
    CustomFieldUpdate,
)
from .time_utils import utc_now

router = APIRouter(prefix="/api/v2/custom-fields", tags=["custom-fields"])


def field_from_row(row: sqlite3.Row) -> CustomFieldPublic:
    return CustomFieldPublic(**definition_from_row(row))


def fetch_field(connection: sqlite3.Connection, field_id: int) -> sqlite3.Row:
    row: sqlite3.Row | None = connection.execute(
        f"{DEFINITION_ROWS_SQL} WHERE id = ?",
        (field_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Custom field not found",
        )
    return row


def refuse_duplicate_key(
    connection: sqlite3.Connection,
    entity_type: str,
    key: str,
) -> None:
    """The partial unique index would answer this with a 500.

    `idx_custom_field_key_per_entity` is the real guarantee -- enforced in the
    schema rather than in application code, like
    `idx_saved_views_default_per_user` -- and this turns the collision into
    the 409 a caller can act on.
    """
    clash = connection.execute(
        """
        SELECT 1 FROM custom_field_definitions
        WHERE entity_type = ? AND key = ? AND archived_at IS NULL
        """,
        (entity_type, key),
    ).fetchone()
    if clash is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A field with the key '{key}' already exists here",
        )


@router.get("", response_model=Page[CustomFieldPublic])
def list_custom_fields(
    entity_type: CustomFieldEntity | None = Query(default=None),
    include_archived: bool = Query(default=False),
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[CustomFieldPublic]:
    """Every definition, or those for one entity type.

    Open to any authenticated caller: a reader has to know what the columns
    on their screen mean, and a definition carries no record's data.
    Archived ones are available but not default, because the one screen that
    needs them is the one that manages fields.
    """
    filters = ["1 = 1"]
    params: list[object] = []
    if entity_type is not None:
        filters.append("entity_type = ?")
        params.append(entity_type)
    if not include_archived:
        filters.append("archived_at IS NULL")

    # Keyset over (position, id) -- the display order, which is what a reader
    # pages through. Ends in the id, like every paginated ORDER BY here.
    continuation, cursor_values = cursor_clause(page, "position", "id", descending=False)
    if continuation:
        filters.append(continuation)
        params.extend(cursor_values)

    with db_connection() as connection:
        rows = connection.execute(
            f"""
            {DEFINITION_ROWS_SQL}
            WHERE {" AND ".join(filters)}
            ORDER BY position, id
            LIMIT ?
            """,
            (*params, page.limit + 1),
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["position"], row["id"]))
    return Page(items=[field_from_row(row) for row in rows], next_cursor=next_cursor)


@router.post("", response_model=CustomFieldPublic, status_code=status.HTTP_201_CREATED)
def create_custom_field(
    payload: CustomFieldCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> CustomFieldPublic:
    require_admin(user)
    with db_connection() as connection:
        refuse_duplicate_key(connection, payload.entity_type, payload.key)
        now = utc_now()
        cursor = connection.execute(
            """
            INSERT INTO custom_field_definitions (
                entity_type, key, label, type, options, required, position,
                created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.entity_type,
                payload.key,
                payload.label,
                payload.type,
                json.dumps(payload.options),
                int(payload.required),
                payload.position,
                int(user["id"]),
                now,
                now,
            ),
        )
        connection.commit()
        return field_from_row(fetch_field(connection, int(cursor.lastrowid or 0)))


@router.patch("/{field_id}", response_model=CustomFieldPublic)
def update_custom_field(
    field_id: int,
    payload: CustomFieldUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> CustomFieldPublic:
    """Label, options, required and position. Never key or type (D-171).

    Removing an option a record already uses is allowed and does not rewrite
    anything: the stored value stops being offered and is dropped on read by
    `visible_values`, the same way an archived field's values are. Rewriting
    rows to match a definition edit is the data migration ADR 0006 exists to
    avoid.
    """
    require_admin(user)
    with db_connection() as connection:
        row = fetch_field(connection, field_id)
        if row["archived_at"] is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An archived field cannot be edited; create a new one",
            )
        chooses = row["type"] in ("select", "multi_select")
        if chooses and not payload.options:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A select field needs at least one option",
            )
        if not chooses and payload.options:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Only select fields carry options",
            )

        connection.execute(
            """
            UPDATE custom_field_definitions
            SET label = ?, options = ?, required = ?, position = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload.label,
                json.dumps(payload.options),
                int(payload.required),
                payload.position,
                utc_now(),
                field_id,
            ),
        )
        connection.commit()
        return field_from_row(fetch_field(connection, field_id))


@router.post("/{field_id}/archive", response_model=CustomFieldPublic)
def archive_custom_field(
    field_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> CustomFieldPublic:
    """Retire a field without touching a single stored value (ADR 0006).

    Idempotent: archiving an archived field answers the row as it stands, so
    the first archiver is the one recorded and a retry is safe -- the rule
    `resolve`/`unresolve` already follow (milestone 3.3).
    """
    require_admin(user)
    with db_connection() as connection:
        row = fetch_field(connection, field_id)
        if row["archived_at"] is None:
            connection.execute(
                """
                UPDATE custom_field_definitions
                SET archived_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (utc_now(), utc_now(), field_id),
            )
            connection.commit()
            row = fetch_field(connection, field_id)
        return field_from_row(row)


@router.post("/{field_id}/restore", response_model=CustomFieldPublic)
def restore_custom_field(
    field_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> CustomFieldPublic:
    """Put an archived field back, values and all.

    This is the undo of `archive`, and it is what makes archiving safe to try:
    the values were never deleted, so restoring a definition makes them
    visible again (`visible_values`). It can fail, unlike archive -- the key
    may have been taken by a field created in the meantime, which is exactly
    the reuse the partial unique index allows.
    """
    require_admin(user)
    with db_connection() as connection:
        row = fetch_field(connection, field_id)
        if row["archived_at"] is not None:
            refuse_duplicate_key(connection, row["entity_type"], row["key"])
            connection.execute(
                """
                UPDATE custom_field_definitions
                SET archived_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (utc_now(), field_id),
            )
            connection.commit()
            row = fetch_field(connection, field_id)
        return field_from_row(row)
