/**
 * The client-side mirror of `backend/app/permissions.py`.
 *
 * These decide which buttons are offered, never who is allowed to do what —
 * the server resolves the role from the database on every request and is the
 * only thing that enforces it. They exist so the UI does not offer an action
 * the API will refuse.
 */

export type Role = "owner" | "editor" | "viewer";

/** Sharing, the audit log, and the opportunity's own fields: owner only. */
export function canManageOpportunity(role: Role | null | undefined): boolean {
  return role === "owner";
}

/** Adding entries, notes and comments: everyone except a viewer. */
export function canWriteTimeline(role: Role | null | undefined): boolean {
  return role === "owner" || role === "editor";
}

/**
 * Changing an item that already exists — editing it or deleting it.
 *
 * Reserved to the item's author and the opportunity owner. The two rules are
 * deliberately the same and resolve through this one function, because when
 * they were written separately they drifted apart (DECISIONS.md D-005).
 * `require_author_or_owner` is the side that enforces it.
 */
export function canChangeItem(options: {
  role: Role | null | undefined;
  userId: number | null | undefined;
  authorId: number | null | undefined;
}): boolean {
  const { role, userId, authorId } = options;
  if (!canWriteTimeline(role)) {
    return false;
  }
  return (
    canManageOpportunity(role) || (authorId != null && authorId === userId)
  );
}

/**
 * Whether this caller administers the deployment (R.1c, **D-215**).
 *
 * Not a `Role`: those three are per opportunity and come from a share, while
 * this is a property of the deployment and arrives on the session, resolved
 * from `ADMIN_EMAILS` on the server. It gates the two writes that are not
 * scoped to a deal — defining a custom field, writing an automation rule —
 * and like everything else in this file it decides which controls are drawn,
 * never who may do what.
 */
export function canAdminister(
  user: { is_admin?: boolean } | null | undefined,
): boolean {
  return user?.is_admin === true;
}
