import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ALEX, BLAIR, anEntry, anOpportunity } from "./test-api";
import { openTimeline, renderDashboard, renderDeal } from "./test-app";
import { writeInEditor } from "./test-editor";

/**
 * Keeping something to yourself on a shared deal (milestone R.1b).
 *
 * Two shapes, both from the human's ruling: an entry sealed in place, and a
 * notebook beside the deal. What is asserted here is the *screen's* half —
 * the server's half, including every read that could leak one, is
 * `backend/tests/test_entry_visibility.py`.
 */
describe("writing an entry decides who reads it", () => {
  it("starts private, and says what that means", async () => {
    await renderDeal({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await userEvent.click(screen.getByRole("button", { name: "New entry" }));

    const reveal = await screen.findByRole("checkbox", {
      name: /Reveal this entry to everyone/,
    });

    expect(reveal).not.toBeChecked();
    expect(screen.getByText(/Only you will see it/)).toBeInTheDocument();
  });

  it("posts what the tick box says", async () => {
    const api = await renderDeal({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await userEvent.click(screen.getByRole("button", { name: "New entry" }));
    await userEvent.type(await screen.findByLabelText("Title"), "Pricing call");
    writeInEditor(screen.getByLabelText("Body"), "They pushed back.");

    await userEvent.click(
      screen.getByRole("checkbox", { name: /Reveal this entry to everyone/ }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Add Entry" }));

    await waitFor(() =>
      expect(api.callsTo("POST", "/timeline")).toHaveLength(1),
    );
    const posted = api.callsTo("POST", "/timeline")[0].body as {
      visibility: string;
    };
    expect(posted.visibility).toBe("shared");
  });
});

describe("a sealed entry on somebody else's deal", () => {
  const sealed = anEntry({
    id: 101,
    title: "Kept back",
    body: "The part nobody else sees",
    sequence: 2,
    visibility: "private",
    created_by: BLAIR.id,
    author_name: BLAIR.name,
  });

  it("is not on the timeline at all, and leaves no gap", async () => {
    await renderDeal({
      user: ALEX,
      opportunities: [anOpportunity()],
      entries: [
        anEntry({ id: 100, title: "Said out loud" }),
        sealed,
        // #2 for this reader, because the sealed one is not in their count.
        anEntry({ id: 102, title: "Said out loud again", sequence: 2 }),
      ],
    });
    await screen.findByText("Said out loud");

    // R.1c, **D-209**: not an emptied card — no card. R.1b drew the row with
    // its number, its author and "kept this entry to themselves"; the human
    // ruled that a colleague should not be told there is anything to know.
    expect(
      screen.queryByText(/kept this entry to themselves/),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Kept back")).not.toBeInTheDocument();
    expect(
      screen.queryByText("The part nobody else sees"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(BLAIR.name)).not.toBeInTheDocument();

    // And the numbering runs 1, 2 — not 1, 3, which would say as much as the
    // card used to.
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("#2")).toBeInTheDocument();
    expect(screen.queryByText("#3")).not.toBeInTheDocument();
  });
});

describe("its author", () => {
  it("is told which of their own entries is sealed", async () => {
    await renderDeal({
      user: ALEX,
      opportunities: [anOpportunity()],
      entries: [
        anEntry({ id: 100, title: "Said out loud", visibility: "shared" }),
        anEntry({
          id: 101,
          title: "Kept back",
          sequence: 2,
          visibility: "private",
        }),
      ],
    });

    const card = (await screen.findByText("Kept back")).closest(
      "article",
    ) as HTMLElement;

    expect(within(card).getByText("Private")).toBeInTheDocument();
    // And the one beside it, which everybody reads, is not marked.
    const shared = (await screen.findByText("Said out loud")).closest(
      "article",
    ) as HTMLElement;
    expect(within(shared).queryByText("Private")).toBeNull();
  });

  it("reads it whole, and can reveal it", async () => {
    const api = await renderDeal({
      user: ALEX,
      opportunities: [anOpportunity()],
      entries: [
        anEntry({ id: 101, title: "Kept back", visibility: "private" }),
      ],
    });
    await screen.findByText("Kept back");

    await userEvent.click(screen.getByRole("button", { name: "Reveal" }));

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/v2/timeline/101")).toHaveLength(1),
    );
    expect(api.callsTo("PATCH", "/api/v2/timeline/101")[0].body).toEqual({
      visibility: "shared",
    });
  });

  it("can take a revealed entry back", async () => {
    const api = await renderDeal({
      user: ALEX,
      opportunities: [anOpportunity()],
      entries: [anEntry({ id: 101, visibility: "shared" })],
    });
    await screen.findByText("Discovery call");

    await userEvent.click(screen.getByRole("button", { name: "Keep private" }));

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/v2/timeline/101")[0].body).toEqual({
        visibility: "private",
      }),
    );
  });
});

describe("a notebook of one's own", () => {
  it("is empty until it is written, and keeps what it is given", async () => {
    await renderDashboard({
      opportunities: [anOpportunity({ id: 10 })],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");

    await userEvent.click(
      await screen.findByRole("button", {
        name: /Keep a note on this deal, just for you/,
      }),
    );
    writeInEditor(
      screen.getByLabelText("My private notes on this deal"),
      "Their procurement lead is the blocker.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText("Their procurement lead is the blocker."),
    ).toBeInTheDocument();
  });

  it("says who can see it, where it is written", async () => {
    await renderDeal({
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });

    const panel = (
      await screen.findByRole("heading", { name: "My notes" })
    ).closest("section") as HTMLElement;

    expect(within(panel).getByText("Only you")).toBeInTheDocument();
  });
});
