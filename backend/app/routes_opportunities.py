import sqlite3
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from .activity import fetch_activity_page
from .audit_utils import create_audit_log_entry
from .auth import get_current_user
from .database import db_connection
from .notification_service import create_notification
from .pagination import Page, PageRequest, cursor_clause, page_params, split_page
from .permissions import Role, require_opportunity_access, require_opportunity_owner
from .routes_saved_views import add_opportunity_ids_to_view, require_own_opportunity_view
from .schemas import (
    STAGES,
    ActivityEventPublic,
    BulkActionResponse,
    BulkActionResultItem,
    BulkOpportunityAction,
    OpportunityCreate,
    OpportunityPublic,
    OpportunityUpdate,
    OpportunityVersionPublic,
)
from .share_utils import upsert_share_row
from .soft_delete import restore_opportunity, soft_delete_opportunity, soft_delete_share
from .time_utils import utc_days_ago, utc_now
from .timeline_utils import create_system_timeline_entry
from .versioning import OPPORTUNITY_VERSIONS, record_version

router = APIRouter(prefix="/api/v2", tags=["opportunities"])


STALLED_AFTER_DAYS = 14


def is_opportunity_stalled(
    connection: sqlite3.Connection,
    opportunity_id: int,
) -> bool:
    """True when nothing has happened on the opportunity for 14 days.

    Every timestamp is stored as fixed-width UTC ISO-8601, so SQLite can pick
    the latest activity and compare it to the cutoff as a plain string.
    """
    latest_activity = connection.execute(
        """
        SELECT MAX(activity_at) AS latest_activity
        FROM (
            SELECT event_timestamp AS activity_at
            FROM timeline_entries
            WHERE opportunity_id = ? AND deleted_at IS NULL
            UNION ALL
            SELECT notes.created_at AS activity_at
            FROM notes
            JOIN timeline_entries ON timeline_entries.id = notes.entry_id
            WHERE timeline_entries.opportunity_id = ?
                AND timeline_entries.deleted_at IS NULL
                AND notes.deleted_at IS NULL
            UNION ALL
            SELECT comments.created_at AS activity_at
            FROM comments
            JOIN notes ON notes.id = comments.note_id
            JOIN timeline_entries ON timeline_entries.id = notes.entry_id
            WHERE timeline_entries.opportunity_id = ?
                AND timeline_entries.deleted_at IS NULL
                AND notes.deleted_at IS NULL
                AND comments.deleted_at IS NULL
        )
        """,
        (opportunity_id, opportunity_id, opportunity_id),
    ).fetchone()["latest_activity"]

    if latest_activity is None:
        return False
    return bool(latest_activity < utc_days_ago(STALLED_AFTER_DAYS))


def opportunity_from_row(row: sqlite3.Row, role: Role, stalled: bool = False) -> OpportunityPublic:
    return OpportunityPublic(
        id=row["id"],
        name=row["name"],
        account_name=row["account_name"],
        value=Decimal(str(row["value"])),
        currency=row["currency"],
        stage=row["stage"],
        owner_id=row["owner_id"],
        owner_name=row["owner_name"],
        expected_close_date=row["expected_close_date"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        stalled=stalled,
        current_user_role=role,
    )


def fetch_opportunity_row(
    connection: sqlite3.Connection,
    opportunity_id: int,
) -> sqlite3.Row | None:
    """Plain opportunity lookup. Callers resolve role via `permissions.py`."""
    row: sqlite3.Row | None = connection.execute(
        """
        SELECT opportunities.*, users.name AS owner_name
        FROM opportunities
        JOIN users ON users.id = opportunities.owner_id
        WHERE opportunities.id = ? AND opportunities.deleted_at IS NULL
        """,
        (opportunity_id,),
    ).fetchone()
    return row


@router.get("/opportunities", response_model=Page[OpportunityPublic])
def list_opportunities_page(
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[OpportunityPublic]:
    """Every opportunity the caller can read, newest activity first.

    `stages` used to ride along on this response; it is a fixed list rather
    than a property of this page, so it has its own endpoint below.

    The access predicate was a module-level constant while v1 served the same
    rows from a second query and the two could drift (D-033). With v1 removed
    this is its only reader, so it is written where it runs.
    """
    continuation, cursor_values = cursor_clause(
        page,
        "opportunities.updated_at",
        "opportunities.id",
        descending=True,
    )
    params: list[object] = [user["id"], user["id"], user["id"], *cursor_values, page.limit + 1]

    with db_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT DISTINCT
                opportunities.*,
                users.name AS owner_name,
                CASE
                    WHEN opportunities.owner_id = ? THEN 'owner'
                    ELSE opportunity_shares.role
                END AS current_user_role
            FROM opportunities
            JOIN users ON users.id = opportunities.owner_id
            LEFT JOIN opportunity_shares
                ON opportunity_shares.opportunity_id = opportunities.id
                AND opportunity_shares.deleted_at IS NULL
            WHERE opportunities.deleted_at IS NULL
                AND (
                    opportunities.owner_id = ?
                    OR opportunity_shares.user_id = ?
                )
                {f"AND {continuation}" if continuation else ""}
            ORDER BY opportunities.updated_at DESC, opportunities.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

        rows, next_cursor = split_page(rows, page.limit, lambda row: (row["updated_at"], row["id"]))
        items = [
            opportunity_from_row(
                row, row["current_user_role"], is_opportunity_stalled(connection, row["id"])
            )
            for row in rows
        ]

    return Page(items=items, next_cursor=next_cursor)


@router.get(
    "/stages",
    response_model=Page[str],
    dependencies=[Depends(get_current_user)],
)
def list_stages() -> Page[str]:
    """The fixed stage list, which v1 delivered as a field on the opportunity
    list response and the v2 envelope has no room for.

    Paginating seven values that a migration cannot add to (invariant 6: the
    stage list is fixed and non-renamable) would be theatre, so `next_cursor`
    is always null — but the shape stays the envelope, because a v2 client
    should not have to learn a second one.
    """
    return Page(items=STAGES, next_cursor=None)


@router.post(
    "/opportunities", response_model=OpportunityPublic, status_code=status.HTTP_201_CREATED
)
def create_opportunity(
    payload: OpportunityCreate,
    user: sqlite3.Row = Depends(get_current_user),
) -> OpportunityPublic:
    created_at = utc_now()
    with db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO opportunities (
                name,
                account_name,
                value,
                currency,
                stage,
                owner_id,
                expected_close_date,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.account_name,
                str(payload.value),
                payload.currency,
                payload.stage,
                user["id"],
                payload.expected_close_date,
                created_at,
                created_at,
            ),
        )
        assert cursor.lastrowid is not None
        opportunity_id = int(cursor.lastrowid)
        create_system_timeline_entry(
            connection=connection,
            opportunity_id=opportunity_id,
            created_by=int(user["id"]),
            entry_type="other",
            title="Opportunity created",
            body=f"{payload.name} was created for {payload.account_name}.",
        )
        row = fetch_opportunity_row(connection, opportunity_id)
        assert row is not None
        # Version 1 is the state the record was created in, so the history
        # opens with what the deal said on day one rather than with the first
        # thing that changed (milestone 2.10, same shape as `note_versions`).
        record_version(
            connection,
            OPPORTUNITY_VERSIONS,
            opportunity_id,
            row,
            int(user["id"]),
            created_at,
        )
        connection.commit()
        stalled = is_opportunity_stalled(connection, opportunity_id)

    return opportunity_from_row(row, "owner", stalled)


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityPublic)
def get_opportunity(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> OpportunityPublic:
    with db_connection() as connection:
        role = require_opportunity_access(connection, opportunity_id, int(user["id"]))
        row = fetch_opportunity_row(connection, opportunity_id)
        stalled = is_opportunity_stalled(connection, opportunity_id)

    assert row is not None
    return opportunity_from_row(row, role, stalled)


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityPublic)
def update_opportunity(
    opportunity_id: int,
    payload: OpportunityUpdate,
    user: sqlite3.Row = Depends(get_current_user),
) -> OpportunityPublic:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        with db_connection() as connection:
            require_opportunity_owner(connection, opportunity_id, int(user["id"]))
            row = fetch_opportunity_row(connection, opportunity_id)
            stalled = is_opportunity_stalled(connection, opportunity_id)
        assert row is not None
        return opportunity_from_row(row, "owner", stalled)

    assignments = [f"{field} = ?" for field in updates]
    values = [str(value) if isinstance(value, Decimal) else value for value in updates.values()]
    values.extend([opportunity_id, user["id"]])

    with db_connection() as connection:
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))
        row = fetch_opportunity_row(connection, opportunity_id)
        assert row is not None
        previous_stage = row["stage"]

        connection.execute(
            f"""
            UPDATE opportunities
            SET {", ".join(assignments)}, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE id = ? AND owner_id = ? AND deleted_at IS NULL
            """,
            values,
        )
        if updates.get("stage") and updates["stage"] != previous_stage:
            create_system_timeline_entry(
                connection=connection,
                opportunity_id=opportunity_id,
                created_by=int(user["id"]),
                entry_type="stage_change",
                title=f"Stage changed to {updates['stage']}",
                body=f"Stage changed from {previous_stage} to {updates['stage']}.",
            )
        updated = fetch_opportunity_row(connection, opportunity_id)
        assert updated is not None
        # Read back rather than assembled from `updates`: a PATCH carries only
        # the fields it changes, and a version is the whole state. The
        # statement above set `updated_at`, so the row and its newest version
        # carry the same timestamp.
        record_version(
            connection,
            OPPORTUNITY_VERSIONS,
            opportunity_id,
            updated,
            int(user["id"]),
            updated["updated_at"],
        )
        connection.commit()
        stalled = is_opportunity_stalled(connection, opportunity_id)

    return opportunity_from_row(updated, "owner", stalled)


def opportunity_version_from_row(row: sqlite3.Row) -> OpportunityVersionPublic:
    return OpportunityVersionPublic(
        id=row["id"],
        opportunity_id=row["opportunity_id"],
        version_number=row["version_number"],
        name=row["name"],
        account_name=row["account_name"],
        value=Decimal(str(row["value"])),
        currency=row["currency"],
        stage=row["stage"],
        expected_close_date=row["expected_close_date"],
        edited_by=row["edited_by"],
        editor_name=row["editor_name"],
        created_at=row["created_at"],
    )


@router.get(
    "/opportunities/{opportunity_id}/versions",
    response_model=Page[OpportunityVersionPublic],
)
def list_opportunity_versions_page(
    opportunity_id: int,
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[OpportunityVersionPublic]:
    """Oldest version first: history reads forwards, like the audit log and
    like `GET /api/v2/notes/{id}/versions`.

    Owner-only, the audit log's rule (D-096). What an edit history answers is
    "who changed this and what did it say before", which is the question the
    audit log exists for -- and there is no admin role here, so `AGENTS.md`'s
    "owner or admin" resolves to the opportunity owner (`permissions.py`).
    """
    continuation, cursor_values = cursor_clause(
        page,
        "opportunity_versions.version_number",
        "opportunity_versions.id",
        descending=False,
    )
    params: list[object] = [opportunity_id, *cursor_values, page.limit + 1]

    with db_connection() as connection:
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))
        rows = connection.execute(
            f"""
            SELECT opportunity_versions.*, users.name AS editor_name
            FROM opportunity_versions
            JOIN users ON users.id = opportunity_versions.edited_by
            WHERE opportunity_versions.opportunity_id = ?
            {f"AND {continuation}" if continuation else ""}
            ORDER BY opportunity_versions.version_number ASC, opportunity_versions.id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    rows, next_cursor = split_page(rows, page.limit, lambda row: (row["version_number"], row["id"]))
    return Page(items=[opportunity_version_from_row(row) for row in rows], next_cursor=next_cursor)


@router.get(
    "/opportunities/{opportunity_id}/activity",
    response_model=Page[ActivityEventPublic],
)
def list_activity_page(
    opportunity_id: int,
    page: PageRequest = Depends(page_params),
    user: sqlite3.Row = Depends(get_current_user),
) -> Page[ActivityEventPublic]:
    """Who did what when, in one chronological list (milestone 3.0, D-101).

    Open to every role, and the *rows* are what the role decides: system
    entries for anyone with access, plus the audit and version halves for the
    owner, each keeping the rule it already had (`app/activity.py`). That is
    why this is not `require_opportunity_owner` — an editor asking what
    happened gets the events they may read rather than a 403.
    """
    with db_connection() as connection:
        role = require_opportunity_access(connection, opportunity_id, int(user["id"]))
        items, next_cursor = fetch_activity_page(connection, opportunity_id, role, page)

    return Page(items=items, next_cursor=next_cursor)


@router.delete("/opportunities/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_opportunity(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    with db_connection() as connection:
        require_opportunity_owner(connection, opportunity_id, int(user["id"]))
        row = fetch_opportunity_row(connection, opportunity_id)
        assert row is not None

        soft_delete_opportunity(connection, opportunity_id)
        create_audit_log_entry(
            connection=connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            action="opportunity_deleted",
            detail={
                "name": row["name"],
                "account_name": row["account_name"],
                "stage": row["stage"],
            },
        )
        connection.commit()


def bulk_delete(
    connection: sqlite3.Connection,
    opportunity_id: int,
    row: sqlite3.Row,
    actor_id: int,
) -> None:
    """`delete_opportunity`, once per id: the same cascade and the same audit
    row, so a bulk delete is undone by the same restore route."""
    soft_delete_opportunity(connection, opportunity_id)
    create_audit_log_entry(
        connection=connection,
        opportunity_id=opportunity_id,
        actor_id=actor_id,
        action="opportunity_deleted",
        detail={
            "name": row["name"],
            "account_name": row["account_name"],
            "stage": row["stage"],
        },
    )


def bulk_set_stage(
    connection: sqlite3.Connection,
    opportunity_id: int,
    row: sqlite3.Row,
    actor_id: int,
    stage: str,
) -> None:
    """`update_opportunity`'s stage branch, once per id."""
    previous_stage = row["stage"]
    connection.execute(
        """
        UPDATE opportunities
        SET stage = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE id = ? AND owner_id = ? AND deleted_at IS NULL
        """,
        (stage, opportunity_id, actor_id),
    )
    if stage != previous_stage:
        create_system_timeline_entry(
            connection=connection,
            opportunity_id=opportunity_id,
            created_by=actor_id,
            entry_type="stage_change",
            title=f"Stage changed to {stage}",
            body=f"Stage changed from {previous_stage} to {stage}.",
        )
    # A stage set in bulk is the same edit as one set on its own, so it leaves
    # the same version behind (milestone 2.10).
    moved = fetch_opportunity_row(connection, opportunity_id)
    assert moved is not None
    record_version(
        connection,
        OPPORTUNITY_VERSIONS,
        opportunity_id,
        moved,
        actor_id,
        moved["updated_at"],
    )


def bulk_assign_owner(
    connection: sqlite3.Connection,
    opportunity_id: int,
    row: sqlite3.Row,
    actor_id: int,
    new_owner: sqlite3.Row,
) -> None:
    """Hand one opportunity to another user (milestone 3.0a, **D-105**).

    Three writes, in the order they matter:

    - **The record changes hands.** `owner_id` is the one opportunity column
      with no version history (`versioning.OPPORTUNITY_VERSIONS` snapshots
      what a reader edits, and ownership is not edited in the dialog), so
      this writes no version row. It is recorded as history the way sharing
      is -- a system entry everyone with access reads, and an audit row for
      the forensics.
    - **The previous owner stays on as an editor**, rather than losing the
      deal entirely. A transfer is then not a lockout: the person who handed
      it on can still read their own work and add to it, and the new owner
      can remove them from the sharing panel if that is what they meant.
      D-105 records the alternative (a clean break) and why this is the
      safer default for an action the previous owner cannot undo themselves.
    - **The new owner is told.** Being given a deal is the one access change
      nobody asked for, so it notifies like a share does.

    An existing share row for the new owner is removed in the same step: they
    hold the record now, and a share row beside the ownership would draw them
    into the sharing panel as their own guest.
    """
    previous_owner_id = int(row["owner_id"])
    connection.execute(
        """
        UPDATE opportunities
        SET owner_id = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE id = ? AND deleted_at IS NULL
        """,
        (new_owner["id"], opportunity_id),
    )
    soft_delete_share(connection, opportunity_id, int(new_owner["id"]))
    upsert_share_row(connection, opportunity_id, previous_owner_id, "editor", actor_id)
    create_system_timeline_entry(
        connection=connection,
        opportunity_id=opportunity_id,
        created_by=actor_id,
        entry_type="other",
        title=f"Owner changed to {new_owner['name']}",
        body=(
            f"{row['owner_name']} handed this opportunity to {new_owner['name']} "
            f"and stays on as editor."
        ),
    )
    create_audit_log_entry(
        connection=connection,
        opportunity_id=opportunity_id,
        actor_id=actor_id,
        action="owner_changed",
        detail={
            "from_user_id": previous_owner_id,
            "to_user_id": int(new_owner["id"]),
            "to_email": new_owner["email"],
        },
    )
    create_notification(
        connection,
        int(new_owner["id"]),
        "owner_changed",
        {"opportunity_id": opportunity_id, "actor_id": actor_id},
    )


def resolve_new_owner(
    connection: sqlite3.Connection,
    email: str,
) -> sqlite3.Row:
    """The user an `assign_owner` names, or 404.

    A whole-request failure rather than a per-item one: an unknown email is
    wrong about the request, not about any id in it, so answering per item
    would repeat one mistake as many times as the selection is long.
    """
    new_owner: sqlite3.Row | None = connection.execute(
        "SELECT id, email, name FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    if not new_owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with that email was not found",
        )
    return new_owner


@router.post("/opportunities/bulk", response_model=BulkActionResponse)
def bulk_opportunity_action(
    payload: BulkOpportunityAction,
    user: sqlite3.Row = Depends(get_current_user),
) -> BulkActionResponse:
    """One request over many opportunities, checked and applied one id at a
    time rather than all-or-nothing (`docs/UX.md`: "report per-item failures
    rather than failing wholesale"). Every id gets a result even when another
    one in the same batch fails, so a caller's mixed selection of owned and
    merely-shared records only loses the ones it cannot touch.

    Four of `docs/UX.md`'s five action-bar actions are here, and each reuses a
    rule that already exists rather than adding one: `delete` and `set_stage`
    are owner-only through `require_opportunity_owner`, like the single-item
    routes they repeat; `assign_owner` is owner-only for the same reason --
    only the holder of a record may hand it on (D-105); and `add_to_view`
    asks only for *read* access per id, because it writes to the caller's own
    saved view rather than to the opportunity (D-106). The fifth, export, is
    not an action here at all: it answers with a file rather than a list of
    per-item outcomes (D-107, `routes_export.py`).

    Two failures are about the request rather than about one id -- an unknown
    email and a view that is not the caller's -- and both are raised before
    the loop, so a selection is never half-applied against a target that does
    not exist.
    """
    actor_id = int(user["id"])
    results: list[BulkActionResultItem] = []

    with db_connection() as connection:
        # `is not None` rather than truthiness: the validator has already
        # tied each field to its action, so what is left here is the value
        # itself, and an empty email or a view id of zero should reach the
        # lookup that answers 404 rather than quietly skipping it.
        new_owner = (
            resolve_new_owner(connection, payload.new_owner_email)
            if payload.new_owner_email is not None
            else None
        )
        view = (
            require_own_opportunity_view(connection, payload.view_id, actor_id)
            if payload.view_id is not None
            else None
        )
        pinned: list[int] = []

        for opportunity_id in payload.ids:
            try:
                if payload.action == "add_to_view":
                    require_opportunity_access(connection, opportunity_id, actor_id)
                else:
                    require_opportunity_owner(connection, opportunity_id, actor_id)
                row = fetch_opportunity_row(connection, opportunity_id)
            except HTTPException as exc:
                results.append(
                    BulkActionResultItem(id=opportunity_id, status="error", error=str(exc.detail))
                )
                continue

            assert row is not None
            if payload.action == "delete":
                bulk_delete(connection, opportunity_id, row, actor_id)
            elif payload.action == "set_stage":
                assert payload.stage is not None
                bulk_set_stage(connection, opportunity_id, row, actor_id, payload.stage)
            elif payload.action == "assign_owner":
                assert new_owner is not None
                if row["owner_id"] == new_owner["id"]:
                    results.append(
                        BulkActionResultItem(
                            id=opportunity_id,
                            status="error",
                            error="Opportunity is already owned by that user",
                        )
                    )
                    continue
                bulk_assign_owner(connection, opportunity_id, row, actor_id, new_owner)
            else:
                pinned.append(opportunity_id)

            results.append(BulkActionResultItem(id=opportunity_id, status="ok"))

        if view is not None and pinned:
            add_opportunity_ids_to_view(connection, view, pinned)

        connection.commit()

    return BulkActionResponse(results=results)


# Owner-only, and answered by a lookup of its own: once an
# opportunity is deleted the share rows are deleted with it, so
# `require_opportunity_owner` — which resolves a role through the undeleted
# tree — cannot see it at all. Everyone who is not the owner therefore gets
# 404, which is also the right answer: a deleted record leaks nothing.
@router.post("/opportunities/{opportunity_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_opportunity_route(
    opportunity_id: int,
    user: sqlite3.Row = Depends(get_current_user),
) -> None:
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT id, name, account_name, stage, deleted_at
            FROM opportunities
            WHERE id = ? AND owner_id = ? AND deleted_at IS NOT NULL
            """,
            (opportunity_id, int(user["id"])),
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deleted opportunity not found",
            )

        restore_opportunity(connection, opportunity_id, row["deleted_at"])
        create_audit_log_entry(
            connection=connection,
            opportunity_id=opportunity_id,
            actor_id=int(user["id"]),
            action="opportunity_restored",
            detail={
                "name": row["name"],
                "account_name": row["account_name"],
                "stage": row["stage"],
            },
        )
        connection.commit()
