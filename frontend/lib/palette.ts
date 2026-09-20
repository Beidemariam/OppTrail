/**
 * The command palette's matcher (milestone 2.4a).
 *
 * `docs/UX.md` asks for a fuzzy jump, so "nwp" finds "Northwind platform
 * rollout": the query has to appear in order but not consecutively. Kept here
 * rather than inside the component because it is the part with edge cases
 * worth testing directly.
 */

export interface Command {
  id: string;
  label: string;
  /** The second line, also searched — an account name, or what a key does. */
  hint?: string;
  run: () => void;
}

/** Whether `query`'s characters appear in `text`, in order, ignoring case. */
export function fuzzyMatches(text: string, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return true;
  }

  const haystack = text.toLowerCase();
  let position = 0;
  for (const character of needle) {
    // A space in the query matches nothing in particular; treat it as a
    // separator so "acme exp" behaves like "acmeexp".
    if (character === " ") {
      continue;
    }
    const found = haystack.indexOf(character, position);
    if (found === -1) {
      return false;
    }
    position = found + 1;
  }
  return true;
}

/** The commands a query keeps, in the order they were declared — the palette's
 * own grouping is the ranking. */
export function filterCommands(commands: Command[], query: string): Command[] {
  return commands.filter((command) =>
    fuzzyMatches(`${command.label} ${command.hint ?? ""}`, query),
  );
}
