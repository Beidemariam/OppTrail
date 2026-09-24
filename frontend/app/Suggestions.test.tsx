import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import type { SuggestionSources } from "../lib/suggestions";
import { RichTextEditor } from "./RichTextEditor";
import { SuggestionSourceProvider } from "./Suggestions";
import { writeInEditor } from "./test-editor";

/**
 * The three triggers, driven the way `app/test-editor.ts` drives everything
 * else in a ProseMirror document: by pasting, because jsdom makes none of the
 * DOM mutations typing reads back (**D-113**). A paste is a transaction, and a
 * transaction is what the suggestion plugin watches — so the popup opens here
 * exactly as it does under a keystroke, and `e2e/19-suggestions.spec.ts` is
 * where it is actually typed.
 */
const sources: SuggestionSources = {
  opportunityId: 4,
  people: [
    { email: "alex@opptrail.test", name: "Alex Owner", role: "owner" },
    { email: "blair@opptrail.test", name: "Blair Editor", role: "editor" },
  ],
  entries: [
    { id: 11, title: "Pricing pushback", type: "call" },
    { id: 12, title: "Security review", type: "meeting" },
  ],
};

function Harness({
  provided = sources,
  onEscape,
}: {
  provided?: SuggestionSources;
  onEscape?: () => void;
}) {
  const [markdown, setMarkdown] = useState("");
  return (
    <SuggestionSourceProvider sources={provided}>
      <RichTextEditor
        label="Body"
        placeholder="Write something"
        value=""
        onChange={setMarkdown}
        onKeyDown={(event) => {
          // What a `Composer` does with Escape: the popup has to take the
          // first one, or putting a menu away also throws the draft away.
          if (event.key === "Escape") {
            onEscape?.();
          }
        }}
      />
      <pre data-testid="markdown">{markdown}</pre>
    </SuggestionSourceProvider>
  );
}

const written = () => screen.getByTestId("markdown").textContent;

/** Types a trigger and waits for its options: the plugin resolves `items`
 * asynchronously, so the first render of the menu is always empty. */
async function openMenu(text: string) {
  const editable = screen.getByLabelText("Body");
  writeInEditor(editable, text);
  await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
  return editable;
}

const options = () =>
  screen.getAllByRole("option").map((item) => item.textContent);

describe("the @ trigger", () => {
  it("offers the people on this opportunity, narrowed by what was typed", async () => {
    render(<Harness />);
    await openMenu("Handing over to @bl");

    expect(screen.getByRole("listbox", { name: "People" })).toBeInTheDocument();
    expect(options()).toEqual(["Blair Editorblair@opptrail.test | editor"]);
  });

  it("writes the address a mention is delivered by", async () => {
    render(<Harness />);
    const editable = await openMenu("Handing over to @bl");
    fireEvent.keyDown(editable, { key: "Enter" });

    // The stored body is what the backend reads mentions out of
    // (`notification_service.MENTION_RE`), so the autocomplete's whole output
    // is the address the reader would otherwise have had to remember (D-122).
    expect(written()).toBe("Handing over to @blair@opptrail.test");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("moves the highlight with the arrow keys, and says which one it is on", async () => {
    render(<Harness />);
    const editable = await openMenu("cc @");
    expect(options()).toHaveLength(2);

    const highlighted = () =>
      screen
        .getAllByRole("option")
        .findIndex((option) => option.getAttribute("aria-selected") === "true");
    expect(highlighted()).toBe(0);
    // Focus never leaves the text, so the editable is what points at the
    // option the reader is on.
    expect(editable.getAttribute("aria-activedescendant")).toBe(
      screen.getAllByRole("option")[0].id,
    );

    fireEvent.keyDown(editable, { key: "ArrowDown" });
    expect(highlighted()).toBe(1);
    expect(editable.getAttribute("aria-activedescendant")).toBe(
      screen.getAllByRole("option")[1].id,
    );

    // And it wraps, so a list of two is reachable in either direction.
    fireEvent.keyDown(editable, { key: "ArrowDown" });
    expect(highlighted()).toBe(0);
    fireEvent.keyDown(editable, { key: "ArrowUp" });
    expect(highlighted()).toBe(1);

    // A key the menu has no use for is handed back to the editor, which is
    // still the thing being typed in.
    fireEvent.keyDown(editable, { key: "ArrowLeft" });
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    fireEvent.keyDown(editable, { key: "Enter" });
    expect(written()).toBe("cc @blair@opptrail.test");
  });

  it("can be chosen with the mouse without taking focus out of the sentence", async () => {
    render(<Harness />);
    await openMenu("cc @");
    const chosen = screen.getAllByRole("option")[1];
    const event = fireEvent.mouseDown(chosen);

    // `preventDefault` on mousedown is what keeps the caret where it was.
    expect(event).toBe(false);
    expect(written()).toBe("cc @blair@opptrail.test");
  });

  it("says so when nobody matches, and hands the keystrokes back", async () => {
    render(<Harness />);
    const editable = screen.getByLabelText("Body");
    writeInEditor(editable, "cc @zzz");
    await waitFor(() =>
      expect(
        screen.getByText("No colleagues on this opportunity"),
      ).toBeInTheDocument(),
    );

    // An empty popup must not swallow Enter: the reader is still typing a
    // sentence.
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    fireEvent.keyDown(editable, { key: "Enter" });
    expect(written()).toBe("cc @zzz");
  });

  it("offers nobody outside an opportunity, rather than failing", async () => {
    render(
      <Harness provided={{ opportunityId: null, people: [], entries: [] }} />,
    );
    writeInEditor(screen.getByLabelText("Body"), "cc @a");
    await waitFor(() =>
      expect(
        screen.getByText("No colleagues on this opportunity"),
      ).toBeInTheDocument(),
    );
  });
});

describe("the / trigger", () => {
  it("offers the blocks, and applies the one chosen to the line", async () => {
    render(<Harness />);
    const editable = await openMenu("/quo");

    expect(screen.getByRole("listbox", { name: "Blocks" })).toBeInTheDocument();
    expect(options()).toEqual(["Quote> then space"]);

    fireEvent.keyDown(editable, { key: "Enter" });
    // The typed `/quo` goes with the choice: what the reader wanted was the
    // block, not the words they used to ask for it.
    expect(written()).toBe(">");
  });

  it("carries the blocks the toolbar leaves to a Markdown input rule", async () => {
    render(<Harness />);
    const editable = await openMenu("/head");
    expect(options()).toEqual([
      "Heading# then space",
      "Subheading## then space",
    ]);
    fireEvent.keyDown(editable, { key: "Enter" });
    // An empty heading serializes to nothing, so what is asserted is the
    // block the reader is now typing into.
    expect(editable.querySelector("h1")).toBeInTheDocument();
  });

  it("completes on Tab as well as Enter", async () => {
    render(<Harness />);
    const editable = await openMenu("/bullet");
    fireEvent.keyDown(editable, { key: "Tab" });
    expect(written()).toBe("-");
  });
});

describe("the # trigger", () => {
  it("offers this opportunity's entries and links to the one chosen", async () => {
    render(<Harness />);
    const editable = await openMenu("As agreed in #secur");

    expect(
      screen.getByRole("listbox", { name: "Entries" }),
    ).toBeInTheDocument();
    expect(options()).toEqual(["Security reviewMeeting"]);

    fireEvent.keyDown(editable, { key: "Enter" });
    // A Markdown link, which is what makes it survive the round trip through
    // storage — and a relative one, which is what makes the app follow it
    // itself (D-124).
    expect(written()).toBe(
      "As agreed in [Security review](/opportunities/4?entry=12)",
    );
  });
});

describe("Escape", () => {
  it("puts the menu away without also closing the composer", async () => {
    let escapes = 0;
    render(<Harness onEscape={() => (escapes += 1)} />);
    const editable = await openMenu("cc @");

    fireEvent.keyDown(editable, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument(),
    );
    expect(escapes).toBe(0);

    // With the menu gone, the next Escape is the composer's again.
    fireEvent.keyDown(editable, { key: "Escape" });
    expect(escapes).toBe(1);
  });
});
