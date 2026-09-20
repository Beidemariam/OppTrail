"""Saved views: a named filter + sort + group set for a view over one dataset.

Milestone 2.2 (`docs/ROADMAP.md` Phase 2, `docs/FEATURES.md` §1). A saved view
is not opportunity-scoped -- it belongs to the user who created it -- so
`permissions.py`'s owner/editor/viewer machinery does not apply here. The only
rule is creator-only write, mirroring the audit log's owner-only read: a view
that is not yours and not shared answers 404, matching `CLAUDE.md`'s rule that
absence of access is 404, not 403, so a view's existence does not leak to a
caller who has no business with it.

v2 only: there is no v1 shape to mirror (like notifications' mark-all-read).
"""

import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from .auth import get_current_user
from .database import db_connection
from .pagination import Page, PageRequest, cursor_clause, page_params, split_page
from .schemas import SavedViewCreate, SavedViewPublic, SavedViewUpdate
from .soft_delete import soft_delete_saved_view
from .time_utils import utc_now

v2_router = APIRouter(prefix="/api/v2/saved-views", tags=["saved-views"])


def saved_view_from_row(row: sqlite3.Row) -> SavedViewPublic:
    return SavedViewPublic(
        id=row["id"],
        created_by=row["created_by"],
        creator_name=row["creator_name"],
        name=row["name"],
        entity=row["entity"],
        filters=json.loads(row["filters"]),
        sort=json.loads(row["sort"]),
        group_by=row["group_by"],
        is_shared=bool(row["is_shared"]),
        is_default=bool(row["is_default"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def fetch_saved_view_row(connection: sqlite3.Connection, view_id: int) -> sqlite3.Row | None:
    row: sqlite3.Row | None = connection.execute(
        """
        SELECT saved_views.*, users.name AS creator_name
        FROM saved_views
        JOIN users ON users.id = saved_views.created_by
        WHERE saved_views.id = ? AND saved_views.deleted_at IS NULL
        """,
        (view_id,),
    ).fetchone()
    return row


def _clear_other_defaults(
    connection: sqlite3.Connection,
    user_id: int,
    entity: str,
    exclude_id: int | None,
) -> None:
    """A new default replaces the old one rather than colliding with it.

    Runs before the insert/update that sets `is_default = 1`, in the same
    transaction, so the partial unique index
    (`idx_saved_views_default_per_user`) never sees two defaults at once.
    """
    connection.execute(
        """
        UPDATE saved_views
        SET is_default = 0
        WHERE created_by = ?
            AND entity = ?
            AND is_default = 1
            AND deleted_at IS NULL
            AND id IS NOT ?
        """,
        (user_id, entity, exclude_id),
    )


@v2_router.post("", response_model=SavedViewPublic, status_code=status.HTTP_201_CREATED)
def create_saved_view(
    payload: SavedViewCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> SavedViewPublic:
    now = utc_now()
    with db_connection() as connection:
        if payload.is_default:
            _clear_other_defaults(connection, int(user["id"]), payload.entity, None)
        cursor = connection.execute(
            """
            INSERT INTO saved_views (
                created_by, name, entity, filters, sort, group_by,
                is_shared, is_default, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                payload.name,
                payload.entity,
                json.dumps(payload.filters),
                json.dumps(payload.sort),
                payload.group_by,
                int(payload.is_shared),
                int(payload.is_default),
                now,
                now,
            ),
        )
        assert cursor.lastrowid is not None
        connection.commit()
        row = fetch_saved_view_row(connection, int(cursor.lastrowid))

    assert row is not None
    return saved_view_from_row(row)


@v2_router.get("", response_model=Page[SavedViewPublic])
def list_saved_views(
    page: PageRequest = Depends(page_params),
    entity: str | None = None,
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[SavedViewPublic]:
    """Every view the caller may apply: their own, plus anyone's shared ones."""
    where = [
        "saved_views.deleted_at IS NULL",
        "(saved_views.created_by = ? OR saved_views.is_shared = 1)",
    ]
    params: list[object] = [user["id"]]

    if entity:
        where.append("saved_views.entity = ?")
        params.append(entity)

    continuation, cursor_values = cursor_clause(
        page, "saved_views.updated_at", "saved_views.id", descending=True
    )
    if continuation:
        where.append(continuation)
        params.extend(cursor_values)
    params.append(page.limit + 1)

    with db_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT saved_views.*, users.name AS creator_name
            FROM saved_views
            JOIN users ON users.id = saved_views.created_by
            WHERE {" AND ".join(where)}
            ORDER BY saved_views.updated_at DESC, saved_views.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["updated_at"], row["id"]))
    return Page(items=[saved_view_from_row(row) for row in rows], next_cursor=next_cursor)


def _require_creator(row: sqlite3.Row | None, user_id: int) -> sqlite3.Row:
    if row is None or row["created_by"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved view not found")
    return row


@v2_router.patch("/{view_id}", response_model=SavedViewPublic)
def update_saved_view(
    view_id: int,
    payload: SavedViewUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> SavedViewPublic:
    with db_connection() as connection:
        existing = _require_creator(fetch_saved_view_row(connection, view_id), int(user["id"]))

        fields = payload.model_dump(exclude_unset=True)
        if fields.get("is_default"):
            _clear_other_defaults(connection, int(user["id"]), existing["entity"], view_id)

        connection.execute(
            """
            UPDATE saved_views
            SET name = ?,
                filters = ?,
                sort = ?,
                group_by = ?,
                is_shared = ?,
                is_default = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                fields.get("name", existing["name"]),
                json.dumps(fields["filters"]) if "filters" in fields else existing["filters"],
                json.dumps(fields["sort"]) if "sort" in fields else existing["sort"],
                fields.get("group_by", existing["group_by"]),
                int(fields.get("is_shared", existing["is_shared"])),
                int(fields.get("is_default", existing["is_default"])),
                utc_now(),
                view_id,
            ),
        )
        connection.commit()
        row = fetch_saved_view_row(connection, view_id)

    assert row is not None
    return saved_view_from_row(row)


@v2_router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_view(
    view_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    with db_connection() as connection:
        _require_creator(fetch_saved_view_row(connection, view_id), int(user["id"]))
        soft_delete_saved_view(connection, view_id)
        connection.commit()
