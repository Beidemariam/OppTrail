"""Granting one user access to one opportunity, written once.

Two paths write an `opportunity_shares` row: `routes_sharing.create_share`,
where an owner invites someone, and the ownership transfer in
`routes_opportunities` (milestone 3.0a), which leaves the previous owner
behind as an editor so a handover is not a lockout (**D-105**). Both have to
cope with the same history -- the pair may already exist and be soft-deleted,
because `soft_delete_share` stamps `deleted_at` rather than removing the row,
and `UNIQUE (opportunity_id, user_id)` means a second `INSERT` would fail.

So the grant is one upsert rather than a select-then-branch in each caller.
The conflict target is that unique index; a revived row is given the new
role, the new inviter and a fresh `created_at`, because it records this grant
rather than the one that was removed.

Who is *allowed* to grant stays with the callers: sharing is owner-only, and
each route resolves that through `permissions.py` before calling here.
"""

import sqlite3

from .time_utils import utc_now


def upsert_share_row(
    connection: sqlite3.Connection,
    opportunity_id: int,
    user_id: int,
    role: str,
    invited_by: int,
) -> None:
    connection.execute(
        """
        INSERT INTO opportunity_shares (
            opportunity_id, user_id, role, invited_by, created_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (opportunity_id, user_id) DO UPDATE SET
            role = excluded.role,
            invited_by = excluded.invited_by,
            created_at = excluded.created_at,
            deleted_at = NULL
        """,
        (opportunity_id, user_id, role, invited_by, utc_now()),
    )
