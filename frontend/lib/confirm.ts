/**
 * The one place this app asks "are you sure".
 *
 * Milestone 2.4b took confirmation off the timeline's destructive actions:
 * they apply and offer Undo instead (`docs/UX.md`, `app/Toasts.tsx`). Three
 * callers are left, deliberately:
 *
 * - Deleting an opportunity, which cascades across a whole record. UX.md keeps
 *   friction there; 2.5 makes it the typed confirmation it describes.
 * - Bulk-deleting opportunities (milestone 2.4c): the same cascade, multiplied
 *   by however many are selected — more reason for the friction, not less.
 * - Removing someone's access, which has no restore route — re-sharing is a
 *   new grant with its own audit row, not an undo — so the question is still
 *   worth asking.
 *
 * `window.confirm` is a placeholder: milestone 2.5 replaces it with a real
 * dialog built on Radix, which stays a single-file change while all three
 * callers sit behind this function.
 */
export function confirmDelete(description: string): boolean {
  return window.confirm(`Delete ${description}?`);
}
