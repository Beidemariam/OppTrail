/**
 * Search snippets arrive as plain text plus match offsets, never as markup
 * (`backend/app/search.py`'s `build_snippet`), so the client is the only place
 * that decides how a match is shown. This turns those offsets into runs.
 *
 * The offsets are produced by one ordered, non-overlapping pass over the
 * excerpt, and index into the text as it was returned — leading ellipsis
 * included — so slicing what we were given is all this needs to do.
 */

import type { components } from "./api-types";

type SearchSnippet = components["schemas"]["SearchSnippet"];

export interface SnippetSegment {
  text: string;
  match: boolean;
}

export function snippetSegments(snippet: SearchSnippet): SnippetSegment[] {
  const segments: SnippetSegment[] = [];
  let cursor = 0;

  for (const match of snippet.matches) {
    if (match.start > cursor) {
      segments.push({
        text: snippet.text.slice(cursor, match.start),
        match: false,
      });
    }
    const end = match.start + match.length;
    segments.push({ text: snippet.text.slice(match.start, end), match: true });
    cursor = end;
  }

  if (cursor < snippet.text.length) {
    segments.push({ text: snippet.text.slice(cursor), match: false });
  }

  return segments;
}
