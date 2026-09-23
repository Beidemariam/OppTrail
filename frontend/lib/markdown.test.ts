import { describe, expect, it } from "vitest";

import {
  docFromMarkdown,
  isAllowedLinkHref,
  linkProtocols,
  markdownFromDoc,
  normalizeMarkdown,
} from "./markdown";

/**
 * The round trip is the whole reason this milestone needed no migration: what
 * comes out of the composer has to be the Markdown the API already stores, and
 * what goes in has to be the document that Markdown describes.
 */
describe("the editor's Markdown", () => {
  it("parses the constructs a note is written with", () => {
    const doc = docFromMarkdown(
      "A **bold** point\n\n- one\n- two\n\n1. first\n\n> quoted\n\n- [x] done",
    );
    const kinds = (doc.content ?? []).map((node) => node.type);
    expect(kinds).toEqual([
      "paragraph",
      "bulletList",
      "orderedList",
      "blockquote",
      "taskList",
    ]);
  });

  it("writes a document back out as the same Markdown", () => {
    const markdown = "A **bold** point\n\n- one\n- two\n\n> quoted";
    expect(markdownFromDoc(docFromMarkdown(markdown))).toBe(markdown);
  });

  it("keeps a checklist's state, which is what the box is for", () => {
    expect(normalizeMarkdown("- [ ] call back\n- [x] sent the quote")).toBe(
      "- [ ] call back\n- [x] sent the quote",
    );
  });

  it("drops the trailing paragraph the editor keeps for the cursor", () => {
    expect(
      markdownFromDoc({
        type: "doc",
        content: [
          { type: "paragraph", content: [{ type: "text", text: "Sent." }] },
          { type: "paragraph" },
        ],
      }),
    ).toBe("Sent.");
  });

  /**
   * Normalization is why `NoteBlock` compares a saved body against this rather
   * than against the stored text: the document records the structure, not the
   * characters that produced it, so re-saving an untouched note would otherwise
   * look like an edit.
   */
  it("says how stored Markdown will be written back", () => {
    expect(normalizeMarkdown("* one\n* two")).toBe("- one\n- two");
    expect(normalizeMarkdown("__shipped__")).toBe("**shipped**");
    expect(normalizeMarkdown("Plain text.")).toBe("Plain text.");
  });
});

describe("the link allowlist", () => {
  it("is the renderer's own, so the editor cannot write what it strips", () => {
    expect(linkProtocols).toEqual(["http", "https", "mailto"]);
  });

  it.each(["https://example.com/quote", "mailto:casey@example.com", "#top"])(
    "allows %s",
    (href) => {
      expect(isAllowedLinkHref(href)).toBe(true);
    },
  );

  it.each([
    "javascript:alert(1)",
    "  JavaScript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "vbscript:msgbox",
  ])("refuses %s", (href) => {
    expect(isAllowedLinkHref(href)).toBe(false);
  });
});
