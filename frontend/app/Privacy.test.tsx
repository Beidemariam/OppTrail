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

  it("keeps its place and its number, and carries nothing else", async () => {
    await renderDeal({
      user: ALEX,
      opportunities: [anOpportunity()],
      entries: [anEntry({ id: 100, title: "Said out loud" }), sealed],
    });

    const card = (
      await screen.findByText(/kept this entry to themselves/)
    ).closest("article") as HTMLElement;

    expect(within(card).getByText("#2")).toBeInTheDocument();
    expect(within(card).getByText("Private")).toBeInTheDocument();
    expect(screen.queryByText("Kept back")).not.toBeInTheDocument();
    expect(
      screen.queryByText("The part nobody else sees"),
    ).not.toBeInTheDocument();
    // And the entry beside it is untouched.
    expect(screen.getByText("Said out loud")).toBeInTheDocument();
  });

  it("offers no way to act on it", async () => {
    await renderDeal({
      user: ALEX,
      opportunities: [anOpportunity()],
      entries: [sealed],
    });
    await screen.findByText(/kept this entry to themselves/);

    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add note" })).toBeNull();
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
