import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Composer, RichTextEditor } from "./RichTextEditor";
import { clearEditor, selectAllInEditor, writeInEditor } from "./test-editor";

function Harness({ initial = "" }: { initial?: string }) {
  const [markdown, setMarkdown] = useState(initial);
  return (
    <div>
      <RichTextEditor
        label="Body"
        placeholder="Write something"
        value={initial}
        onChange={setMarkdown}
      />
      <pre data-testid="markdown">{markdown}</pre>
    </div>
  );
}

const written = () => screen.getByTestId("markdown").textContent;

describe("the rich composer", () => {
  it("opens with the Markdown it was given, as a document", () => {
    render(<Harness initial={"A **bold** point\n\n- one\n- two"} />);
    const editable = screen.getByLabelText("Body");
    expect(editable.querySelector("strong")?.textContent).toBe("bold");
    expect(editable.querySelectorAll("ul li")).toHaveLength(2);
  });

  it("reports what the reader wrote back as Markdown", () => {
    render(<Harness />);
    writeInEditor(screen.getByLabelText("Body"), "- one\n- two");
    expect(written()).toBe("- one\n\n- two");
  });

  it("formats the selection from the toolbar", async () => {
    render(<Harness initial="pricing" />);
    await userEvent.click(screen.getByRole("button", { name: "Bullets" }));
    expect(written()).toBe("- pricing");
  });

  /** Every control, because a toolbar that lies about one of them is worse
   * than one button fewer. */
  it.each([
    ["Bold", "**pricing**"],
    ["Italic", "*pricing*"],
    ["Strike", "~~pricing~~"],
    ["Code", "`pricing`"],
    ["Bullets", "- pricing"],
    ["Numbers", "1. pricing"],
    ["Checklist", "- [ ] pricing"],
    ["Quote", "> pricing"],
  ])("writes what %s promises", async (control, markdown) => {
    render(<Harness initial="pricing" />);
    selectAllInEditor(screen.getByLabelText("Body"));

    await userEvent.click(screen.getByRole("button", { name: control }));

    expect(written()).toBe(markdown);
  });

  it("empties to nothing at all, not to a blank line", () => {
    render(<Harness initial="pricing" />);
    clearEditor(screen.getByLabelText("Body"));
    expect(written()).toBe("");
  });

  it("says which formatting the cursor is in", async () => {
    render(<Harness initial="pricing" />);
    const quote = screen.getByRole("button", { name: "Quote" });
    expect(quote).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(quote);
    expect(quote).toHaveAttribute("aria-pressed", "true");
  });

  /**
   * The risk `docs/ROADMAP.md` names for this phase. Sanitization on render is
   * the boundary (`MarkdownText`), and this is the other half: the editor's
   * link allowlist is the renderer's, so a protocol the renderer would strip
   * is refused where it is written rather than disappearing when it is read.
   */
  it("refuses a link the renderer would strip", () => {
    render(<Harness />);
    const editable = screen.getByLabelText("Body");
    writeInEditor(editable, "[go](javascript:alert(1))");

    // The text survives, escaped, as the text it is: what is refused is the
    // link, so nothing renders an `href` a reader could follow.
    expect(editable.querySelector("a")).toBeNull();
    expect(written()).not.toContain("[go](");
  });

  it("keeps a link the renderer will render", () => {
    render(<Harness />);
    const editable = screen.getByLabelText("Body");
    writeInEditor(editable, "[the quote](https://example.com/quote)");

    expect(editable.querySelector("a")).toHaveAttribute(
      "href",
      "https://example.com/quote",
    );
  });
});

describe("a composer that opens when it is written in", () => {
  function posted(onSubmit = () => Promise.resolve()) {
    render(
      <Composer
        label="Add a comment to this note"
        trigger="Add comment"
        placeholder="Write a comment"
        submitLabel="Post"
        onSubmit={onSubmit}
      />,
    );
  }

  it("is one control until it is opened, and then the editor", async () => {
    posted();
    expect(
      screen.queryByLabelText("Add a comment to this note"),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Add comment" }));

    const editable = screen.getByLabelText("Add a comment to this note");
    expect(editable).toHaveFocus();
  });

  it("posts what was written and closes", async () => {
    const submit = vi.fn(() => Promise.resolve());
    posted(submit);

    await userEvent.click(screen.getByRole("button", { name: "Add comment" }));
    writeInEditor(
      screen.getByLabelText("Add a comment to this note"),
      "Sent the **quote**.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Post" }));

    expect(submit).toHaveBeenCalledWith("Sent the **quote**.");
    expect(
      await screen.findByRole("button", { name: "Add comment" }),
    ).toHaveFocus();
  });

  it("does not post an empty composer", async () => {
    const submit = vi.fn(() => Promise.resolve());
    posted(submit);

    await userEvent.click(screen.getByRole("button", { name: "Add comment" }));
    await userEvent.click(screen.getByRole("button", { name: "Post" }));

    expect(submit).not.toHaveBeenCalled();
    expect(
      screen.getByLabelText("Add a comment to this note"),
    ).toBeInTheDocument();
  });

  it("holds the draft while it is closed, by Esc or by Cancel", async () => {
    posted();

    await userEvent.click(screen.getByRole("button", { name: "Add comment" }));
    writeInEditor(
      screen.getByLabelText("Add a comment to this note"),
      "Half a thought",
    );
    await userEvent.keyboard("{Escape}");

    expect(
      screen.queryByLabelText("Add a comment to this note"),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Add comment" }));
    expect(
      screen.getByLabelText("Add a comment to this note"),
    ).toHaveTextContent("Half a thought");

    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      screen.queryByLabelText("Add a comment to this note"),
    ).not.toBeInTheDocument();
  });

  it("stays open, holding the draft, when the post is refused", async () => {
    posted(() => Promise.reject(new Error("Viewers cannot comment")));

    await userEvent.click(screen.getByRole("button", { name: "Add comment" }));
    writeInEditor(
      screen.getByLabelText("Add a comment to this note"),
      "Worth a try",
    );
    await userEvent.click(screen.getByRole("button", { name: "Post" }));

    expect(
      await screen.findByLabelText("Add a comment to this note"),
    ).toHaveTextContent("Worth a try");
  });
});
