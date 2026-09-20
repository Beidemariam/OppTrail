import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ALEX, anEntry, anOpportunity } from "./test-api";
import { findCard, renderApp, renderDashboard } from "./test-app";

const northwind = anOpportunity();
const acme = anOpportunity({
  id: 11,
  name: "Acme expansion",
  account_name: "Acme",
  stage: "Prospecting",
});

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Ctrl rather than Cmd, because the matcher treats them as one chord and
 * `chordFor`'s unit tests already cover both spellings. */
const CTRL_K = "{Control>}k{/Control}";
const CTRL_ENTER = "{Control>}{Enter}{/Control}";

describe("the command palette", () => {
  it("opens on Ctrl K and jumps to the opportunity the query picks", async () => {
    await renderDashboard({ opportunities: [northwind, acme] });

    await userEvent.keyboard(CTRL_K);
    const palette = await screen.findByRole("dialog", {
      name: "Command palette",
    });

    await userEvent.keyboard("acme");
    expect(
      within(palette).queryByText("Northwind rollout"),
    ).not.toBeInTheDocument();

    await userEvent.keyboard("{Enter}");

    expect(
      await screen.findByRole("heading", { level: 2, name: "Acme expansion" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("falls through to full-text search for a query that is not a command", async () => {
    await renderDashboard({
      opportunities: [northwind],
      searchResults: [],
    });

    await userEvent.keyboard(CTRL_K);
    await userEvent.keyboard("procurement");
    await userEvent.click(
      screen.getByRole("option", { name: /Search everything for/ }),
    );

    expect(
      await screen.findByRole("heading", { name: "Search" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Search")).toHaveValue("procurement");
  });

  it("moves the highlight with the arrow keys", async () => {
    await renderDashboard({ opportunities: [northwind, acme] });

    await userEvent.keyboard(CTRL_K);
    await screen.findByRole("dialog", { name: "Command palette" });

    const first = screen.getByRole("option", { name: /Go to the dashboard/ });
    expect(first).toHaveAttribute("aria-selected", "true");

    await userEvent.keyboard("{ArrowDown}");
    expect(first).toHaveAttribute("aria-selected", "false");
    expect(
      screen.getByRole("option", { name: "Go to search" }),
    ).toHaveAttribute("aria-selected", "true");

    await userEvent.keyboard("{ArrowUp}");
    expect(first).toHaveAttribute("aria-selected", "true");
  });

  it("says so when nothing matches", async () => {
    await renderDashboard({ opportunities: [northwind] });

    await userEvent.keyboard(CTRL_K);
    // A query with no subsequence in any command, including the search
    // fallthrough, which is dropped here because its own label is matched.
    await userEvent.keyboard("zzzz");

    expect(screen.queryByText("Nothing matches that.")).not.toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /Search everything for "zzzz"/ }),
    ).toBeInTheDocument();
  });

  it("opens from the top bar as well, for a reader who has never pressed Ctrl K", async () => {
    await renderDashboard({ opportunities: [northwind] });

    await userEvent.click(
      screen.getByRole("button", { name: /Search or jump to/ }),
    );

    expect(
      await screen.findByRole("dialog", { name: "Command palette" }),
    ).toBeInTheDocument();
  });

  it("goes back to the board from the search page", async () => {
    renderApp({ user: ALEX, opportunities: [northwind] }, "/search");
    await screen.findByRole("heading", { name: "Search" });

    await userEvent.keyboard(CTRL_K);
    await userEvent.click(
      screen.getByRole("option", { name: /Go to the dashboard/ }),
    );

    expect(
      await screen.findByRole("heading", { name: "Opportunities" }),
    ).toBeInTheDocument();
  });

  it("signs the reader out", async () => {
    const api = await renderDashboard({ opportunities: [northwind] });

    await userEvent.keyboard(CTRL_K);
    await userEvent.click(screen.getByRole("option", { name: "Sign out" }));

    expect(
      await screen.findByRole("button", { name: "Create account" }),
    ).toBeInTheDocument();
    expect(api.callsTo("POST", "/api/auth/logout")).toHaveLength(1);
  });

  it("stays shut for a signed-out visitor", async () => {
    renderApp();
    await screen.findByRole("button", { name: "Create account" });

    await userEvent.keyboard(CTRL_K);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("the keyboard reference", () => {
  it("opens on ?, closes on Escape, and gives focus back", async () => {
    await renderDashboard({ opportunities: [northwind] });
    const trigger = screen.getByRole("button", { name: /Search or jump to/ });
    trigger.focus();

    await userEvent.keyboard("?");
    const help = await screen.findByRole("dialog", {
      name: "Keyboard shortcuts",
    });
    expect(within(help).getByText("Open the command palette")).toBeVisible();

    await userEvent.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(trigger).toHaveFocus();
  });

  it("keeps Tab inside the dialog", async () => {
    await renderDashboard({ opportunities: [northwind] });

    await userEvent.keyboard("?");
    const close = await screen.findByRole("button", { name: "Close" });
    close.focus();

    // The reference has exactly one focusable control, so a trapped Tab and a
    // trapped Shift Tab both land back on it — which is the point: focus
    // cannot escape to the page behind.
    await userEvent.tab();
    expect(close).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(close).toHaveFocus();
  });

  it("closes on the Close button and on a click outside it", async () => {
    await renderDashboard({ opportunities: [northwind] });

    await userEvent.keyboard("?");
    await userEvent.click(await screen.findByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await userEvent.keyboard("?");
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(dialog);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await userEvent.click(document.querySelector(".modal-backdrop")!);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is reachable from the palette", async () => {
    await renderDashboard({ opportunities: [northwind] });

    await userEvent.keyboard(CTRL_K);
    await userEvent.click(
      screen.getByRole("option", { name: "Show keyboard shortcuts" }),
    );

    expect(
      await screen.findByRole("dialog", { name: "Keyboard shortcuts" }),
    ).toBeInTheDocument();
  });
});

describe("going places", () => {
  it("walks g s to search and g d back to the board", async () => {
    await renderDashboard({ opportunities: [northwind] });

    await userEvent.keyboard("gs");
    expect(
      await screen.findByRole("heading", { name: "Search" }),
    ).toBeInTheDocument();

    await userEvent.keyboard("gd");
    expect(
      await screen.findByRole("heading", { name: "Opportunities" }),
    ).toBeInTheDocument();
  });

  it("does nothing for a g sequence that means nothing", async () => {
    await renderDashboard({ opportunities: [northwind] });

    await userEvent.keyboard("gz");

    expect(
      screen.getByRole("heading", { name: "Opportunities" }),
    ).toBeInTheDocument();
  });
});

describe("the board under the keyboard", () => {
  it("moves the cursor with j and k, across stage columns", async () => {
    await renderDashboard({ opportunities: [northwind, acme] });
    await findCard("Northwind rollout");

    // Prospecting comes before Negotiation, so the board order is Acme first.
    await userEvent.keyboard("j");
    expect(await findCard("Acme expansion")).toHaveFocus();

    await userEvent.keyboard("j");
    expect(await findCard("Northwind rollout")).toHaveFocus();

    await userEvent.keyboard("k");
    expect(await findCard("Acme expansion")).toHaveFocus();
  });

  it("stops at the ends rather than wrapping", async () => {
    await renderDashboard({ opportunities: [northwind, acme] });
    await findCard("Northwind rollout");

    await userEvent.keyboard("k");
    expect(await findCard("Northwind rollout")).toHaveFocus();

    await userEvent.keyboard("k");
    expect(await findCard("Acme expansion")).toHaveFocus();

    await userEvent.keyboard("k");
    expect(await findCard("Acme expansion")).toHaveFocus();
  });

  it("edits the focused opportunity with e, and clears the cursor with Escape", async () => {
    await renderDashboard({ opportunities: [northwind] });
    await findCard("Northwind rollout");

    await userEvent.keyboard("je");

    expect(
      screen.getByRole("heading", { name: "Edit Opportunity" }),
    ).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(await findCard("Northwind rollout")).not.toHaveFocus();
  });

  it("toggles bulk selection of the focused card with x, and Escape clears the selection first", async () => {
    await renderDashboard({ opportunities: [northwind] });
    await findCard("Northwind rollout");

    await userEvent.keyboard("jx");
    expect(
      screen.getByRole("checkbox", {
        name: "Select Northwind rollout for bulk actions",
      }),
    ).toBeChecked();
    expect(
      screen.getByRole("toolbar", { name: "Bulk actions" }),
    ).toBeInTheDocument();

    // Escape clears the selection rather than the keyboard cursor, per
    // `docs/UX.md`'s ordering — the card is still focused afterwards.
    await userEvent.keyboard("{Escape}");
    expect(
      screen.queryByRole("toolbar", { name: "Bulk actions" }),
    ).not.toBeInTheDocument();
    expect(await findCard("Northwind rollout")).toHaveFocus();
  });

  it("offers no edit for an opportunity the reader does not own", async () => {
    await renderDashboard({
      opportunities: [anOpportunity({ current_user_role: "viewer" })],
    });
    await findCard("Northwind rollout");

    await userEvent.keyboard("je");

    expect(
      screen.getByRole("heading", { name: "New Opportunity" }),
    ).toBeInTheDocument();
  });

  it("opens the focused card's timeline with Enter", async () => {
    await renderDashboard({
      opportunities: [northwind],
      entries: [anEntry()],
    });
    await findCard("Northwind rollout");

    await userEvent.keyboard("j{Enter}");

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "Northwind rollout",
      }),
    ).toBeInTheDocument();
  });

  it("focuses the keyword filter with /", async () => {
    await renderDashboard({ opportunities: [northwind] });

    await userEvent.keyboard("/");

    expect(
      screen.getByLabelText("Filter opportunities by keyword"),
    ).toHaveFocus();
  });

  it("composes an opportunity with c", async () => {
    await renderDashboard({ opportunities: [northwind] });

    await userEvent.keyboard("c");

    expect(screen.getByLabelText("Opportunity")).toHaveFocus();
  });
});

describe("with a timeline open", () => {
  it("gives c to the entry composer instead of the board", async () => {
    await renderDashboard(
      { opportunities: [northwind], entries: [anEntry()] },
      "/opportunities/10",
    );
    await screen.findByRole("heading", {
      level: 2,
      name: "Northwind rollout",
    });

    await userEvent.keyboard("c");

    expect(screen.getByLabelText("Title")).toHaveFocus();
    expect(screen.getByLabelText("Opportunity")).not.toHaveFocus();
  });

  it("submits the entry composer on Ctrl Enter", async () => {
    const api = await renderDashboard(
      { opportunities: [northwind], entries: [anEntry()] },
      "/opportunities/10",
    );
    await screen.findByRole("heading", {
      level: 2,
      name: "Northwind rollout",
    });

    await userEvent.keyboard("c");
    await userEvent.keyboard("Pricing call");
    await userEvent.type(screen.getByLabelText("Body"), "They pushed back.");
    await userEvent.keyboard(CTRL_ENTER);

    await waitFor(() =>
      expect(
        api.callsTo("POST", "/api/opportunities/10/timeline"),
      ).toHaveLength(1),
    );
  });

  it("posts a note on Ctrl Enter without reaching for the button", async () => {
    const api = await renderDashboard(
      { opportunities: [northwind], entries: [anEntry()] },
      "/opportunities/10",
    );
    await screen.findByRole("heading", {
      level: 2,
      name: "Northwind rollout",
    });

    await userEvent.type(
      screen.getByLabelText("Add a note to this entry"),
      "Budget confirmed.",
    );
    await userEvent.keyboard(CTRL_ENTER);

    await waitFor(() =>
      expect(api.callsTo("POST", "/api/timeline/100/notes")).toHaveLength(1),
    );
  });
});

describe("shortcuts and text", () => {
  /**
   * The guard test (brief §6.5). Without `isTypingTarget` in `chordFor`, every
   * letter of this note is a command: "c" opens a composer, "e" opens the edit
   * form, "j" and "k" move the board's cursor, and the note never gets typed.
   */
  it("does not treat what the reader types as commands", async () => {
    await renderDashboard(
      { opportunities: [northwind], entries: [anEntry()] },
      "/opportunities/10",
    );
    await screen.findByRole("heading", {
      level: 2,
      name: "Northwind rollout",
    });

    const composer = screen.getByLabelText("Add a note to this entry");
    await userEvent.type(composer, "check jack's expiry date?");

    expect(composer).toHaveValue("check jack's expiry date?");
    expect(composer).toHaveFocus();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Edit Opportunity" }),
    ).not.toBeInTheDocument();
  });
});
