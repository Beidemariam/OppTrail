/**
 * The one place this app asks "are you sure".
 *
 * `window.confirm` is a placeholder: milestone 2.5 replaces it with a real
 * dialog built on Radix. Routing every destructive action through one function
 * is what makes that a single-file change rather than a hunt through the views.
 */
export function confirmDelete(description: string): boolean {
  return window.confirm(`Delete ${description}? This cannot be undone here.`);
}
