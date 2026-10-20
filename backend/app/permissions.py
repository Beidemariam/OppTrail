import sqlite3
from typing import Literal

from fastapi import HTTPException, status

from .settings import settings

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


# Which entries one person may read, as a predicate the entry-reading queries
# paste into their own `WHERE` (milestone R.1b).
#
# **A private entry is readable by its author alone.** Not by the opportunity's
# owner either: "private" that the owner can read is not private, and an owner
# who needs the content can ask for it the way anybody else would. The rule is
# symmetric, which is what makes it one predicate rather than a role lookup --
# and `authorization is structural` (AGENTS.md invariant 2) means it belongs
# here, beside the rule it extends, rather than being retyped per query.
#
# **Used inside `timeline_utils.ENTRY_SEQUENCE_SQL` since R.1c**, which is the
# reverse of what R.1b decided and is the human's ruling at the R.1b
# shakedown: *"it is better not to mention anything instead of saying it is
# kept private, so the other person doesn't know anything about what's kept
# away from them"* (**D-209**). A sealed entry is now absent from a
# colleague's timeline rather than standing there emptied -- and an absent row
# has to take its number with it, because a gap between #35 and #37 says
# exactly what the card used to say out loud. So the number is per reader: it
# counts the entries *that reader* may read. The AI's context was already
# assembled per reader (R.1b), so the two still agree about what `#7` means
# for the person asking.
VISIBLE_ENTRIES_SQL = "(timeline_entries.visibility = 'shared' OR timeline_entries.created_by = ?)"


def visible_entries_clause(alias: str = "timeline_entries") -> str:
    """The same predicate against a different alias.

    Search joins the entries table under its own name in three of its four
    branches, and a string with `timeline_entries.` hard-coded would be wrong
    there rather than merely ugly.
    """
    return f"({alias}.visibility = 'shared' OR {alias}.created_by = ?)"


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


def admin_emails() -> frozenset[str]:
    """The configured administrators, lower-cased (R.1c, **D-215**).

    Read on every call rather than cached at import, so a test can set
    `settings.admin_emails` the way every other setting here is driven.
    """
    return frozenset(
        address.strip().lower() for address in settings.admin_emails.split(",") if address.strip()
    )


def is_admin(user: sqlite3.Row) -> bool:
    """Whether this caller administers the deployment.

    Not a role in the `Role` sense: those three are *per opportunity* and come
    from the database, while this is a property of the deployment and comes
    from its configuration. The two never mix -- an admin has no more access
    to a deal than their shares give them, and an opportunity's owner
    administers nothing beyond it.
    """
    return str(user["email"]).lower() in admin_emails()


def require_admin(user: sqlite3.Row) -> None:
    """The two global writes: defining a custom field, writing an automation
    rule (R.1c, **D-215**).

    **403 and not 404**, unlike every opportunity-scoped refusal in this
    module. Hiding existence is pointless here and the message is the useful
    part: the field list and the rule list are readable by everyone, so the
    caller already knows these objects exist and needs to be told who may
    change them -- which is why the sentence names the setting rather than
    saying "forbidden".
    """
    if not is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Only an administrator can change this. Administrators are set in "
                "the deployment's ADMIN_EMAILS setting."
            ),
        )
