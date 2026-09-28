import sqlite3
from typing import Literal

from fastapi import HTTPException, status

Role = Literal["owner", "editor", "viewer"]

# Every opportunity one user may read, as a subquery for the reads that are not
# scoped to a single opportunity and so cannot resolve a role first (search,
# ADR 0007). Same rule as `get_opportunity_role` below -- owner, or an
# undeleted share -- expressed as a set rather than one row, and takes the
# user's id twice.
ACCESSIBLE_OPPORTUNITY_IDS_SQL = """
    SELECT opportunities.id
    FROM opportunities
    LEFT JOIN opportunity_shares
        ON opportunity_shares.opportunity_id = opportunities.id
        AND opportunity_shares.user_id = ?
        AND opportunity_shares.deleted_at IS NULL
    WHERE opportunities.deleted_at IS NULL
        AND (
            opportunities.owner_id = ?
            OR opportunity_shares.user_id IS NOT NULL
        )
"""


def get_opportunity_role(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
) -> Role | None:
    row = connection.execute(
        """
        SELECT opportunities.owner_id, opportunity_shares.role
        FROM opportunities
        LEFT JOIN opportunity_shares
            ON opportunity_shares.opportunity_id = opportunities.id
            AND opportunity_shares.user_id = ?
            AND opportunity_shares.deleted_at IS NULL
        WHERE opportunities.id = ?
            AND opportunities.deleted_at IS NULL
            AND (
                opportunities.owner_id = ?
                OR opportunity_shares.user_id IS NOT NULL
            )
        """,
        (user_id, opportunity_id, user_id),
    ).fetchone()

    if not row:
        return None
    if row["owner_id"] == user_id:
        return "owner"
    role: Role = row["role"]
    return role


def require_opportunity_access(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
) -> Role:
    role = get_opportunity_role(connection, opportunity_id, user_id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found",
        )
    return role


def require_timeline_write(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
) -> Role:
    role = require_opportunity_access(connection, opportunity_id, user_id)
    if role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewer cannot edit this opportunity",
        )
    return role


def require_author_or_owner(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
    author_id: int | None,
    detail: str,
) -> Role:
    """Changing an existing item is limited to its author or the opportunity
    owner. Editors add freely; a colleague's record on a shared opportunity is
    theirs to rewrite or remove.

    Editing and deleting resolve through this one function rather than two
    copies of the rule, so the two can no longer drift apart — which is how
    they came to disagree in the first place (DECISIONS.md D-005).
    """
    role = require_timeline_write(connection, opportunity_id, user_id)
    if role != "owner" and author_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    return role


def require_edit_permission(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
    author_id: int | None,
    detail: str,
) -> Role:
    return require_author_or_owner(connection, opportunity_id, user_id, author_id, detail)


def require_delete_permission(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
    author_id: int | None,
    detail: str,
) -> Role:
    return require_author_or_owner(connection, opportunity_id, user_id, author_id, detail)


def require_opportunity_exists(
    connection: sqlite3.Connection,
    opportunity_id: int,
) -> None:
    """Presence only -- no role, and the one deliberate exception to every
    other function in this module (milestone 3.3a, **D-129**).

    Watching is available to someone with no share on the opportunity at all
    (`docs/FEATURES.md` §7: "follow an opportunity you are not shared on"),
    so `require_opportunity_access`'s role resolution cannot gate it -- that
    would 404 exactly the caller this exists for. The cost, named and
    accepted in D-129, is that the three `.../watch` routes answer
    differently (200/204 vs 404) depending only on whether the id names a
    live opportunity, for *any* authenticated caller -- the one place in the
    app where existence is knowingly not hidden behind access. Nothing this
    function guards leaks the opportunity's content, only whether the id is
    live, and the caller learns nothing they could not already infer by
    trying every id in sequence.
    """
    row = connection.execute(
        "SELECT 1 FROM opportunities WHERE id = ? AND deleted_at IS NULL",
        (opportunity_id,),
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found",
        )


def require_opportunity_owner(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
) -> None:
    role = require_opportunity_access(connection, opportunity_id, user_id)
    if role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can manage this opportunity",
        )
