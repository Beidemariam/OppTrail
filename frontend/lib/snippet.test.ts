import { describe, expect, it } from "vitest";

import { snippetSegments } from "./snippet";

describe("snippetSegments", () => {
  it("splits the excerpt around each match, in order", () => {
    expect(
      snippetSegments({
        text: "viewer-only for finance and finance alone",
        matches: [
          { start: 16, length: 7 },
          { start: 28, length: 7 },
        ],
      }),
    ).toEqual([
      { text: "viewer-only for ", match: false },
      { text: "finance", match: true },
      { text: " and ", match: false },
      { text: "finance", match: true },
      { text: " alone", match: false },
    ]);
  });

  it("keeps the excerpt whole when stemming left no literal match", () => {
    // `build_snippet` returns the head of the text with no offsets when FTS5
    // matched a stem this pass cannot find (`backend/app/search.py`).
    expect(
      snippetSegments({ text: "They raised objections", matches: [] }),
    ).toEqual([{ text: "They raised objections", match: false }]);
  });

  it("handles a match at each end of the excerpt", () => {
    expect(
      snippetSegments({
        text: "finance",
        matches: [{ start: 0, length: 7 }],
      }),
    ).toEqual([{ text: "finance", match: true }]);
  });
});
