/**
 * What a typed trigger offers, as data (milestone 3.2).
 *
 * Three things a composer can be asked for mid-sentence — who to notify, which
 * block to start, which earlier entry to point at — are one mechanism with
 * three triggers (**D-111**): a `@tiptap/suggestion` plugin per character,
 * reading its list from here. This module is the list; `app/Suggestions.tsx`
 * is the popup and the plugins, the way `lib/keyboard.ts` declares the map and
 * a view binds it.
 *
 * Two things about the shape are load bearing:
 *
 * - **What an item inserts is data, not an editor call.** A chosen item is
 *   either text put in place of what was typed, a link, or a command over the
 *   block the cursor is in — so the whole list is testable without a DOM and
 *   without an editor, which is the same reason `lib/markdown.ts` serializes
 *   through a standalone manager.
 * - **Mentions insert plain `@email` text** (**D-122**). The backend finds a
 *   mention by matching that pattern in the stored body
 *   (`notification_service.MENTION_RE`), and storage is Markdown, so the
 *   autocomplete's job is to type the address a person would otherwise have to
 *   remember — not to introduce a node the renderer has never seen.
 */

import type { ChainedCommands } from "@tiptap/core";

import { entryTypeLabel, type EntryType } from "./domain";

/** How many matches a popup offers at once. */
export const SUGGESTION_LIMIT = 8;

/** Someone a mention on this opportunity would reach: the owner and every
 * share (`GET /api/v2/opportunities/{id}/members`, D-123). */
export interface SuggestionPerson {
  email: string;
  name: string;
  role: string;
}

/** An entry a link can point at: one of this opportunity's own. */
export interface SuggestionEntry {
  id: number;
  title: string;
  type: EntryType;
}

/**
 * Everything the three triggers read, gathered per opportunity.
 *
 * `opportunityId` is null where there is no opportunity in scope; the entry
 * trigger then has nothing to offer, because a link to an entry is a link into
 * one deal's timeline.
 */
export interface SuggestionSources {
  people: SuggestionPerson[];
  entries: SuggestionEntry[];
  opportunityId: number | null;
}

export const emptySuggestionSources: SuggestionSources = {
  people: [],
  entries: [],
  opportunityId: null,
};

/**
 * One offered choice: what it says, and what choosing it does.
 *
 * `text` replaces what was typed including the trigger character, `link` does
 * the same as a Markdown link, and `run` is a command over the current block —
 * which is what a slash command is, since "make this a bullet list" is not
 * text at all.
 */
export type SuggestionItem = {
  /** Stable within one popup; the option element's id is built from it. */
  id: string;
  /** The line the reader picks from. */
  label: string;
  /** The second line: an address, an entry's type, a shortcut. */
  detail: string;
} & (
  | { insert: "text"; text: string }
  | { insert: "link"; text: string; href: string }
  | { insert: "command"; run: (chain: ChainedCommands) => ChainedCommands }
);

export interface SuggestionTrigger {
  /** The character that opens this popup. */
  char: string;
  /** What the popup is called, for assistive technology and for tests. */
  label: string;
  /** What to say when the trigger matched nothing. */
  empty: string;
  items: (query: string, sources: SuggestionSources) => SuggestionItem[];
}

/** Case-insensitive contains, which is what a reader typing three letters of
 * a name means. */
function matches(haystack: string, query: string): boolean {
  return haystack.toLowerCase().includes(query.toLowerCase());
}

/**
 * The people trigger: `@`.
 *
 * Matched on name as well as address, because the reader knows the colleague's
 * name and the address is what has to be typed — which is requirement 13's
 * discoverability gap in one sentence (`docs/FEATURES.md` §7).
 */
export function peopleItems(
  query: string,
  { people }: SuggestionSources,
): SuggestionItem[] {
  return people
    .filter(
      (person) => matches(person.name, query) || matches(person.email, query),
    )
    .slice(0, SUGGESTION_LIMIT)
    .map((person) => ({
      id: person.email,
      label: person.name,
      detail: `${person.email} | ${person.role}`,
      insert: "text",
      // The space is part of the insertion: a mention runs up against the next
      // word otherwise, and `MENTION_RE` would read the two as one address.
      text: `@${person.email} `,
    }));
}

/**
 * The blocks the slash menu offers, and what each one does.
 *
 * The same shape as `app/RichTextEditor.tsx`'s toolbar `controls`, and
 * deliberately not the same list: the toolbar carries the marks and lists a
 * reader reaches for while writing, and this carries the *blocks* — including
 * the three the toolbar leaves to a Markdown input rule (a heading, a code
 * block, a divider), which is exactly the discoverability a slash menu adds
 * (**D-111**). Every one of them is a node `lib/markdown.ts` declares and
 * `app/MarkdownText.tsx` renders, so nothing here can write a block that
 * cannot be read back.
 */
export const slashCommands: {
  name: string;
  label: string;
  detail: string;
  run: (chain: ChainedCommands) => ChainedCommands;
}[] = [
  {
    name: "heading1",
    label: "Heading",
    detail: "# then space",
    run: (chain) => chain.setNode("heading", { level: 1 }),
  },
  {
    name: "heading2",
    label: "Subheading",
    detail: "## then space",
    run: (chain) => chain.setNode("heading", { level: 2 }),
  },
  {
    name: "bulletList",
    label: "Bulleted list",
    detail: "- then space",
    run: (chain) => chain.toggleBulletList(),
  },
  {
    name: "orderedList",
    label: "Numbered list",
    detail: "1. then space",
    run: (chain) => chain.toggleOrderedList(),
  },
  {
    name: "taskList",
    label: "Checklist",
    detail: "[ ] then space",
    run: (chain) => chain.toggleTaskList(),
  },
  {
    name: "blockquote",
    label: "Quote",
    detail: "> then space",
    run: (chain) => chain.toggleBlockquote(),
  },
  {
    name: "codeBlock",
    label: "Code block",
    detail: "``` then space",
    run: (chain) => chain.toggleCodeBlock(),
  },
  {
    name: "horizontalRule",
    label: "Divider",
    detail: "---",
    run: (chain) => chain.setHorizontalRule(),
  },
];

export function commandItems(query: string): SuggestionItem[] {
  return slashCommands
    .filter((command) => matches(command.label, query))
    .slice(0, SUGGESTION_LIMIT)
    .map((command) => ({
      id: command.name,
      label: command.label,
      detail: command.detail,
      insert: "command",
      run: command.run,
    }));
}

/**
 * Where a link to an entry points.
 *
 * The opportunity's own route with the entry named in the query string, which
 * `app/OpportunityPanel.tsx` reads to scroll to it and mark it. A relative
 * href, so `app/MarkdownText.tsx` follows it through the router rather than
 * reloading the app (**D-124**) — and one the sanitizer keeps, since it
 * carries no protocol at all (`isAllowedLinkHref`).
 */
export function entryHref(opportunityId: number, entryId: number): string {
  return `/opportunities/${opportunityId}?entry=${entryId}`;
}

/**
 * The entry trigger: `#`.
 *
 * Matched on the title, and on the id as it is written — `#12` finds entry 12,
 * which is how the id reads everywhere else in this app. The trigger shares
 * its character with a Markdown heading, and that costs nothing: a heading is
 * `#` *then a space*, and a space ends a suggestion, so `# ` still opens a
 * heading while `#pri` looks for an entry.
 */
export function entryItems(
  query: string,
  { entries, opportunityId }: SuggestionSources,
): SuggestionItem[] {
  if (opportunityId === null) {
    return [];
  }
  return entries
    .filter(
      (entry) => matches(entry.title, query) || String(entry.id) === query,
    )
    .slice(0, SUGGESTION_LIMIT)
    .map((entry) => ({
      id: String(entry.id),
      label: entry.title,
      detail: entryTypeLabel(entry.type),
      insert: "link",
      text: entry.title,
      href: entryHref(opportunityId, entry.id),
    }));
}

/**
 * The three triggers, in the order they were built.
 *
 * One array, so adding a fourth is a declaration here rather than a second
 * popup: `app/Suggestions.tsx` registers a plugin per entry and renders them
 * all through one menu.
 */
export const suggestionTriggers: SuggestionTrigger[] = [
  {
    char: "@",
    label: "People",
    empty: "No colleagues on this opportunity",
    items: peopleItems,
  },
  {
    char: "/",
    label: "Blocks",
    empty: "No matching block",
    items: (query) => commandItems(query),
  },
  {
    char: "#",
    label: "Entries",
    empty: "No matching entry",
    items: entryItems,
  },
];
