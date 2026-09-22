import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ALEX, anEntry, anOpportunity } from "./test-api";
import {
  acceptConfirmation,
  cancelConfirmation,
  findCard,
  openOpportunityForm,
  openTimeline,
  renderApp,
  renderDashboard,
} from "./test-app";

function checkboxFor(name: string) {
  return screen.getByRole("checkbox", {
    name: `Select ${name} for bulk actions`,
  });
}

/** Scoped so its "Delete" button is not confused with a card's own. */
function bulkBar() {
  return screen.getByRole("toolbar", { name: "Bulk actions" });
}

beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("signed out", () => {
  it("shows the sign-up form when the session check fails", async () => {
    renderApp();

    expect(
      await screen.findByRole("button", { name: "Create account" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Opportunities" }),
    ).not.toBeInTheDocument();
  });

  it("drops the name field when switching to sign in", async () => {
    renderApp();
    await screen.findByRole("button", { name: "Create account" });

    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Sign in" })).toHaveLength(2);
  });

  it("signs a new user up and lands them on the dashboard", async () => {
    const api = renderApp({ opportunities: [anOpportunity()] });
    await screen.findByRole("button", { name: "Create account" });

    await userEvent.type(screen.getByLabelText("Name"), "Alex");
    await userEvent.type(screen.getByLabelText("Email"), "alex@opptrail.test");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(
      screen.getByRole("button", { name: "Create account" }),
    );

    expect(
      await screen.findByRole("heading", { name: "Opportunities" }),
    ).toBeInTheDocument();
    expect(api.callsTo("POST", "/api/auth/signup")).toHaveLength(1);
    expect(await screen.findByText("Northwind rollout")).toBeInTheDocument();
  });

  it("shows the API's own message when sign-in is refused", async () => {
    renderApp({
      failures: { "POST /api/auth/login": [401, "Invalid email or password"] },
    });
    await screen.findByRole("button", { name: "Create account" });

    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await userEvent.type(screen.getByLabelText("Email"), "alex@opptrail.test");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(
      screen.getAllByRole("button", { name: "Sign in" })[1],
    );

    expect(
      await screen.findByText("Invalid email or password"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Opportunities" }),
    ).not.toBeInTheDocument();
  });
});

describe("the dashboard", () => {
  it("groups opportunities by stage and flags the stalled one", async () => {
    await renderDashboard({
      opportunities: [
        anOpportunity({
          id: 10,
          name: "Northwind rollout",
          stage: "Negotiation",
        }),
        anOpportunity({
          id: 11,
          name: "Globex renewal",
          stage: "Proposal",
          stalled: true,
        }),
      ],
    });

    const globex = await findCard("Globex renewal");
    expect(within(globex).getByText("Stalled")).toBeInTheDocument();

    const negotiation = screen
      .getByRole("heading", { name: "Negotiation" })
      .closest("div")!;
    expect(negotiation).toHaveTextContent("1");
  });

  it("virtualizes a stage column at the 400-opportunity scale (milestone 2.3)", async () => {
    const opportunities = Array.from({ length: 400 }, (_, index) =>
      anOpportunity({
        id: 1000 + index,
        name: `Deal ${index}`,
        stage: "Negotiation",
      }),
    );

    await renderDashboard({ opportunities });
    await screen.findByText("Deal 0");

    const negotiation = screen
      .getByRole("heading", { name: "Negotiation" })
      .closest("div")!;
    expect(negotiation).toHaveTextContent("400");

    const cards = screen.getAllByRole("article");
    expect(cards.length).toBeGreaterThan(0);
    expect(cards.length).toBeLessThan(50);
    expect(screen.getByText("Deal 0")).toBeInTheDocument();
    expect(screen.queryByText("Deal 399")).not.toBeInTheDocument();
  });

  it("creates an opportunity from the dialog the board opens", async () => {
    const api = await renderDashboard();

    await openOpportunityForm();
    // The dialog lands the cursor on the field the reader fills first.
    expect(screen.getByLabelText("Opportunity")).toHaveFocus();
    await userEvent.type(screen.getByLabelText("Opportunity"), "Contoso pilot");
    await userEvent.type(screen.getByLabelText("Account"), "Contoso");
    await userEvent.click(
      screen.getByRole("button", { name: "Create opportunity" }),
    );

    await waitFor(() =>
      expect(api.callsTo("POST", "/api/opportunities")).toHaveLength(1),
    );
    expect(api.callsTo("POST", "/api/opportunities")[0].body).toMatchObject({
      name: "Contoso pilot",
      account_name: "Contoso",
      expected_close_date: null,
    });
    expect(await screen.findByText("Contoso pilot")).toBeInTheDocument();
    // Saving closes the dialog, so the board is what the reader is left on.
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("sends every field the form collects", async () => {
    const api = await renderDashboard();

    await openOpportunityForm();
    await userEvent.type(screen.getByLabelText("Opportunity"), "Contoso pilot");
    await userEvent.type(screen.getByLabelText("Account"), "Contoso");
    await userEvent.clear(screen.getByLabelText("Value"));
    await userEvent.type(screen.getByLabelText("Value"), "42000");
    await userEvent.clear(screen.getByLabelText("Currency"));
    await userEvent.type(screen.getByLabelText("Currency"), "EUR");
    // Scoped to the dialog: the board's filter bar behind it now carries a
    // visible "Stage" caption of its own (milestone 2.13).
    await userEvent.selectOptions(
      within(screen.getByRole("dialog")).getByLabelText("Stage"),
      "Proposal",
    );
    await userEvent.type(screen.getByLabelText("Expected close"), "2027-03-01");
    await userEvent.click(
      screen.getByRole("button", { name: "Create opportunity" }),
    );

    await waitFor(() =>
      expect(api.callsTo("POST", "/api/opportunities")).toHaveLength(1),
    );
    expect(api.callsTo("POST", "/api/opportunities")[0].body).toMatchObject({
      name: "Contoso pilot",
      account_name: "Contoso",
      value: "42000",
      currency: "EUR",
      stage: "Proposal",
      expected_close_date: "2027-03-01",
    });
  });

  it("surfaces a rejected create instead of clearing the form", async () => {
    await renderDashboard({
      failures: { "POST /api/opportunities": [422, "Stage is not valid"] },
    });

    await openOpportunityForm();
    await userEvent.type(screen.getByLabelText("Opportunity"), "Bad stage");
    await userEvent.type(screen.getByLabelText("Account"), "Acme");
    await userEvent.click(
      screen.getByRole("button", { name: "Create opportunity" }),
    );

    expect(await screen.findByText("Stage is not valid")).toBeInTheDocument();
    expect(screen.getByLabelText("Opportunity")).toHaveValue("Bad stage");
  });

  it("only asks the API to delete after the confirmation is accepted", async () => {
    const api = await renderDashboard({ opportunities: [anOpportunity()] });
    const card = (await screen.findAllByRole("article"))[0];

    await userEvent.click(within(card).getByRole("button", { name: "Delete" }));
    await cancelConfirmation();
    expect(api.callsTo("DELETE", "/api/opportunities/10")).toHaveLength(0);

    await userEvent.click(within(card).getByRole("button", { name: "Delete" }));
    await acceptConfirmation("Northwind rollout");
    await waitFor(() =>
      expect(api.callsTo("DELETE", "/api/opportunities/10")).toHaveLength(1),
    );
    await waitFor(() =>
      expect(screen.queryByText("Northwind rollout")).not.toBeInTheDocument(),
    );
  });

  it("closes the timeline of an opportunity it just deleted", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });
    await openTimeline("Northwind rollout");
    await screen.findByText("Your role: owner");
    const card = await findCard("Northwind rollout");

    await userEvent.click(within(card).getByRole("button", { name: "Delete" }));
    await acceptConfirmation("Northwind rollout");

    expect(
      await screen.findByText("Select an opportunity to open its timeline."),
    ).toBeInTheDocument();
  });

  it("loads the edit dialog from the card and saves a stage change", async () => {
    const api = await renderDashboard({ opportunities: [anOpportunity()] });
    const card = (await screen.findAllByRole("article"))[0];

    await userEvent.click(within(card).getByRole("button", { name: "Edit" }));
    expect(
      await screen.findByRole("heading", { name: "Edit opportunity" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Opportunity")).toHaveValue(
      "Northwind rollout",
    );

    await userEvent.selectOptions(
      within(screen.getByRole("dialog")).getByLabelText("Stage"),
      "Closed Won",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/opportunities/10")).toHaveLength(1),
    );
    expect(api.callsTo("PATCH", "/api/opportunities/10")[0].body).toMatchObject(
      { stage: "Closed Won" },
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("abandons an edit, and opens the dialog empty next time", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });
    const card = (await screen.findAllByRole("article"))[0];

    await userEvent.click(within(card).getByRole("button", { name: "Edit" }));
    await userEvent.click(await screen.findByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    await openOpportunityForm();
    expect(screen.getByLabelText("Opportunity")).toHaveValue("");
  });

  it("signs out and clears what was on screen", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(
      await screen.findByRole("button", { name: "Create account" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Northwind rollout")).not.toBeInTheDocument();
  });

  it("reports an opportunity list that will not load", async () => {
    renderApp({
      user: ALEX,
      failures: { "GET /api/opportunities": [503, "Database is unavailable"] },
    });

    expect(
      await screen.findByText("Database is unavailable"),
    ).toBeInTheDocument();
  });
});

describe("bulk actions (milestone 2.4c)", () => {
  it("replaces the filter bar with the action bar once a card is checked", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });
    await findCard("Northwind rollout");

    expect(screen.getByRole("button", { name: "Apply" })).toBeInTheDocument();

    await userEvent.click(checkboxFor("Northwind rollout"));

    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Apply" }),
    ).not.toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Clear selection" }),
    );

    expect(screen.getByRole("button", { name: "Apply" })).toBeInTheDocument();
    expect(screen.queryByText("1 selected")).not.toBeInTheDocument();
  });

  it("shift-clicks a range across the board order", async () => {
    const opportunities = [
      anOpportunity({
        id: 10,
        name: "First",
        updated_at: "2026-09-03T00:00:00Z",
      }),
      anOpportunity({
        id: 11,
        name: "Second",
        updated_at: "2026-09-02T00:00:00Z",
      }),
      anOpportunity({
        id: 12,
        name: "Third",
        updated_at: "2026-09-01T00:00:00Z",
      }),
    ];
    await renderDashboard({ opportunities });
    await findCard("First");

    await userEvent.click(checkboxFor("First"));
    fireEvent.click(checkboxFor("Third"), { shiftKey: true });

    expect(screen.getByText("3 selected")).toBeInTheDocument();
    expect(checkboxFor("First")).toBeChecked();
    expect(checkboxFor("Second")).toBeChecked();
    expect(checkboxFor("Third")).toBeChecked();
  });

  it("disables change-stage and delete when the selection includes an opportunity the reader does not own", async () => {
    await renderDashboard({
      opportunities: [
        anOpportunity({ id: 10, name: "Mine", current_user_role: "owner" }),
        anOpportunity({
          id: 11,
          name: "Theirs",
          current_user_role: "editor",
        }),
      ],
    });
    await findCard("Mine");

    await userEvent.click(checkboxFor("Mine"));
    await userEvent.click(checkboxFor("Theirs"));

    expect(
      within(bulkBar()).getByRole("button", { name: "Delete" }),
    ).toBeDisabled();
    expect(
      within(bulkBar()).getByRole("button", { name: "Change stage" }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        "Change stage and delete are limited to opportunities you own.",
      ),
    ).toBeInTheDocument();
  });

  it("bulk-changes the stage of every checked opportunity in one request", async () => {
    const api = await renderDashboard({
      opportunities: [
        anOpportunity({ id: 10, name: "First" }),
        anOpportunity({ id: 11, name: "Second" }),
      ],
    });
    await findCard("First");

    await userEvent.click(checkboxFor("First"));
    await userEvent.click(checkboxFor("Second"));
    await userEvent.selectOptions(
      screen.getByLabelText("Change stage to"),
      "Closed Won",
    );
    await userEvent.click(screen.getByRole("button", { name: "Change stage" }));

    await waitFor(() =>
      expect(api.callsTo("POST", "/api/v2/opportunities/bulk")).toHaveLength(1),
    );
    expect(
      api.callsTo("POST", "/api/v2/opportunities/bulk")[0].body,
    ).toMatchObject({
      ids: [10, 11],
      action: "set_stage",
      stage: "Closed Won",
    });
    expect(
      await screen.findByText("2 opportunities updated."),
    ).toBeInTheDocument();
    // The action bar clears once the request settles.
    expect(screen.queryByText("2 selected")).not.toBeInTheDocument();
  });

  it("bulk-deletes only after the confirmation is accepted, and offers Undo", async () => {
    const api = await renderDashboard({
      opportunities: [
        anOpportunity({ id: 10, name: "First" }),
        anOpportunity({ id: 11, name: "Second" }),
      ],
    });
    await findCard("First");

    await userEvent.click(checkboxFor("First"));
    await userEvent.click(checkboxFor("Second"));

    await userEvent.click(
      within(bulkBar()).getByRole("button", { name: "Delete" }),
    );
    await cancelConfirmation();
    expect(api.callsTo("POST", "/api/v2/opportunities/bulk")).toHaveLength(0);

    await userEvent.click(
      within(bulkBar()).getByRole("button", { name: "Delete" }),
    );
    // Several at once: the dialog asks for the word rather than one of the
    // names, since no single name describes what is about to go.
    await acceptConfirmation("delete");

    await waitFor(() =>
      expect(screen.queryByText("First")).not.toBeInTheDocument(),
    );
    expect(screen.queryByText("Second")).not.toBeInTheDocument();
    expect(
      await screen.findByText("2 opportunities deleted."),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Undo" }));

    expect(await screen.findByText("First")).toBeInTheDocument();
    expect(await screen.findByText("Second")).toBeInTheDocument();
  });

  it("reports a partial bulk failure without losing the successful items", async () => {
    const api = await renderDashboard({
      opportunities: [
        anOpportunity({ id: 10, name: "Mine" }),
        anOpportunity({ id: 11, name: "Also mine" }),
      ],
    });
    await findCard("Mine");
    await userEvent.click(checkboxFor("Mine"));
    await userEvent.click(checkboxFor("Also mine"));

    // Simulates another actor deleting the second one between selection and
    // the click: the bulk endpoint answers per item off server state, not
    // off what the client still believes is selected.
    api.opportunities = api.opportunities.filter(
      (opportunity) => opportunity.id !== 11,
    );

    await userEvent.click(
      within(bulkBar()).getByRole("button", { name: "Delete" }),
    );
    await acceptConfirmation("delete");

    expect(
      await screen.findByText(
        "1 opportunity deleted. 1 failed: Opportunity not found",
      ),
    ).toBeInTheDocument();
  });
});

describe("moving an opportunity between stages (milestone 2.7)", () => {
  /** jsdom has no drag machinery of its own; this is the object a real
   * `dragstart` would carry. */
  function dataTransfer() {
    return {
      setData: vi.fn(),
      getData: vi.fn(),
      dropEffect: "none",
      effectAllowed: "none",
    } as unknown as DataTransfer;
  }

  function column(stage: string) {
    return screen
      .getByRole("heading", { name: stage })
      .closest<HTMLElement>(".stage-column")!;
  }

  async function dragTo(card: HTMLElement, stage: string) {
    const transfer = dataTransfer();
    fireEvent.dragStart(card, { dataTransfer: transfer });
    fireEvent.dragOver(column(stage), { dataTransfer: transfer });
    fireEvent.drop(column(stage), { dataTransfer: transfer });
  }

  it("writes the stage the card was dropped in, and announces it", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity({ stage: "Prospecting" })],
    });
    const card = await findCard("Northwind rollout");

    await dragTo(card, "Proposal");

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/opportunities/10")).toHaveLength(1),
    );
    expect(api.callsTo("PATCH", "/api/opportunities/10")[0].body).toEqual({
      stage: "Proposal",
    });
    // The stage change is the only field the drag sends, and the card is in
    // its new column before the response arrives.
    expect(within(column("Proposal")).getByText("Northwind rollout"));
    expect(
      screen.getByText("Northwind rollout moved to Proposal."),
    ).toBeInTheDocument();
  });

  it("lights the column the card is over, and unlights it on the way out", async () => {
    await renderDashboard({
      opportunities: [anOpportunity({ stage: "Prospecting" })],
    });
    const card = await findCard("Northwind rollout");
    const transfer = dataTransfer();

    fireEvent.dragStart(card, { dataTransfer: transfer });
    fireEvent.dragOver(column("Proposal"), { dataTransfer: transfer });
    expect(column("Proposal")).toHaveClass("drop-target");

    // `relatedTarget` is what the pointer entered, so leaving for something
    // outside the column is what clears the highlight.
    fireEvent.dragLeave(column("Proposal"), {
      dataTransfer: transfer,
      relatedTarget: document.body,
    });
    expect(column("Proposal")).not.toHaveClass("drop-target");
  });

  it("totals a column, and counts it instead when the currencies differ", async () => {
    await renderDashboard({
      opportunities: [
        anOpportunity({ id: 10, stage: "Proposal", value: "1500" }),
        anOpportunity({ id: 11, stage: "Proposal", value: "2500" }),
        anOpportunity({
          id: 12,
          name: "Zurich pilot",
          stage: "Negotiation",
          value: "900",
          currency: "CHF",
        }),
        anOpportunity({ id: 13, stage: "Negotiation", value: "100" }),
      ],
    });
    await screen.findByText("Zurich pilot");

    expect(within(column("Proposal")).getByText("USD 4,000"));
    expect(within(column("Negotiation")).getByText("2 in mixed currencies"));
  });

  it("does nothing when a card is dropped back in its own column", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity({ stage: "Prospecting" })],
    });
    const card = await findCard("Northwind rollout");

    await dragTo(card, "Prospecting");

    expect(api.callsTo("PATCH", "/api/opportunities/10")).toHaveLength(0);
  });

  it("offers no drag and no stage control on an opportunity the reader does not own", async () => {
    await renderDashboard({
      opportunities: [anOpportunity({ current_user_role: "viewer" })],
    });
    const card = await findCard("Northwind rollout");

    expect(card).not.toHaveAttribute("draggable", "true");
    expect(
      screen.queryByLabelText("Move Northwind rollout to stage"),
    ).toBeNull();
  });

  it("moves through the card's stage control, which is the keyboard path", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity({ stage: "Prospecting" })],
    });
    await findCard("Northwind rollout");

    await userEvent.selectOptions(
      screen.getByLabelText("Move Northwind rollout to stage"),
      "Negotiation",
    );

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/opportunities/10")).toHaveLength(1),
    );
    expect(api.callsTo("PATCH", "/api/opportunities/10")[0].body).toEqual({
      stage: "Negotiation",
    });
  });

  it("puts the card back and explains when the move is refused", async () => {
    await renderDashboard({
      opportunities: [anOpportunity({ stage: "Prospecting" })],
      failures: {
        "PATCH /api/opportunities/10": [403, "Only the owner may do that"],
      },
    });
    const card = await findCard("Northwind rollout");

    await dragTo(card, "Proposal");

    expect(
      await screen.findByText(
        "Could not move Northwind rollout to Proposal: Only the owner may do that",
      ),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        within(column("Prospecting")).getByText("Northwind rollout"),
      ).toBeInTheDocument(),
    );
  });
});

describe("the list view (milestone 2.7)", () => {
  const twoDeals = [
    anOpportunity({
      id: 10,
      name: "Northwind rollout",
      stage: "Negotiation",
      updated_at: "2026-09-02T10:00:00Z",
    }),
    anOpportunity({
      id: 11,
      name: "Globex renewal",
      stage: "Proposal",
      updated_at: "2026-09-03T10:00:00Z",
    }),
  ];

  it("switches renderer without asking the API again", async () => {
    const api = await renderDashboard({ opportunities: twoDeals });
    await screen.findByText("Northwind rollout");

    await userEvent.click(screen.getByRole("button", { name: "List" }));

    // One list, drawn twice: no second request, and the stage columns are
    // gone.
    expect(api.callsTo("GET", "/api/opportunities")).toHaveLength(1);
    expect(
      screen.queryByRole("region", {
        name: "Opportunities grouped by stage",
      }),
    ).toBeNull();
    expect(
      screen.getByRole("region", { name: "Opportunities" }),
    ).toBeInTheDocument();
    // Linkable: the choice of renderer is in the URL, not in component
    // state, so a reload and a shared link both land on the list.
    expect(screen.getByRole("button", { name: "List" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("opens in the list when the URL asks for it, in the sorted order", async () => {
    await renderDashboard(
      { opportunities: twoDeals },
      "/?opportunities.view=list",
    );

    const rows = await screen.findAllByRole("article");
    // Sorted by last activity, newest first, which is the default sort.
    expect(rows[0]).toHaveTextContent("Globex renewal");
    expect(rows[1]).toHaveTextContent("Northwind rollout");
  });

  it("keeps the cursor, the selection and the filters across the switch", async () => {
    await renderDashboard({ opportunities: twoDeals });
    await screen.findByText("Northwind rollout");

    await userEvent.type(
      screen.getByLabelText("Filter opportunities by keyword"),
      "globex",
    );
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    await userEvent.keyboard("jx");
    await userEvent.click(screen.getByRole("button", { name: "List" }));

    expect(screen.queryByText("Northwind rollout")).not.toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", {
        name: "Select Globex renewal for bulk actions",
      }),
    ).toBeChecked();
    expect(
      screen.getByRole("toolbar", { name: "Bulk actions" }),
    ).toBeInTheDocument();
  });

  it("moves a row's stage through the same control the card uses", async () => {
    const api = await renderDashboard(
      { opportunities: [anOpportunity({ stage: "Prospecting" })] },
      "/?opportunities.view=list",
    );
    await screen.findByText("Northwind rollout");

    await userEvent.selectOptions(
      screen.getByLabelText("Move Northwind rollout to stage"),
      "Proposal",
    );

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/opportunities/10")).toHaveLength(1),
    );
  });

  it("deletes from a row, behind the same typed confirmation a card asks for", async () => {
    const api = await renderDashboard(
      { opportunities: [anOpportunity()] },
      "/?opportunities.view=list",
    );
    const row = await findCard("Northwind rollout");

    await userEvent.click(within(row).getByRole("button", { name: "Delete" }));
    await acceptConfirmation("Northwind rollout");

    await waitFor(() =>
      expect(api.callsTo("DELETE", "/api/opportunities/10")).toHaveLength(1),
    );
  });

  it("shows a viewer the stage without offering to change it", async () => {
    await renderDashboard(
      { opportunities: [anOpportunity({ current_user_role: "viewer" })] },
      "/?opportunities.view=list",
    );

    const row = await findCard("Northwind rollout");
    expect(within(row).getByText("Negotiation")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Edit" })).toBeNull();
    expect(
      screen.queryByLabelText("Move Northwind rollout to stage"),
    ).toBeNull();
  });
});

describe("what the dashboard shows when it has nothing to show", () => {
  it("explains what an opportunity is before there is one", async () => {
    await renderDashboard({ opportunities: [] });

    expect(
      await screen.findByRole("heading", {
        name: "Track your first opportunity",
      }),
    ).toBeInTheDocument();
    // The board is not drawn as seven empty columns.
    expect(
      screen.queryByRole("region", {
        name: "Opportunities grouped by stage",
      }),
    ).toBeNull();

    // The panel's own button opens the same dialog the header's does.
    await userEvent.click(
      screen.getAllByRole("button", { name: "New opportunity" })[1],
    );
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("distinguishes filtered-to-nothing from nothing, and clears the filter", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });
    await screen.findByText("Northwind rollout");

    await userEvent.type(
      screen.getByLabelText("Filter opportunities by keyword"),
      "nothing matches this",
    );
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(
      screen.getByRole("heading", {
        name: "No opportunities match these filters",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("0 of 1 shown, 1 filtered out"),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Clear filters" }),
    );
    expect(await screen.findByText("Northwind rollout")).toBeInTheDocument();
  });

  // D-076: nothing told the reviewer why their colleague's shared view looked
  // emptier than its author's. Both empty answers now say that a view filters
  // the opportunities this reader can read and nothing wider, which is the
  // sentence that would have prevented the confusion.
  it("says an empty board can be someone else's full one", async () => {
    await renderDashboard({ opportunities: [] });
    expect(
      await screen.findByText(/appear here once they share them with you/),
    ).toBeInTheDocument();
  });

  it("says that the set being filtered is only what this reader may see", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });
    await screen.findByText("Northwind rollout");
    await userEvent.type(
      screen.getByLabelText("Filter opportunities by keyword"),
      "nothing matches this",
    );
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(
      screen.getByText(/A view never widens what you can read/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/it filters the one opportunity you own/),
    ).toBeInTheDocument();
  });
});

describe("filtering, sorting and saved views (milestone 2.2)", () => {
  it("filters the board by keyword without asking the API again", async () => {
    const api = await renderDashboard({
      opportunities: [
        anOpportunity({ id: 10, name: "Northwind rollout" }),
        anOpportunity({ id: 11, name: "Globex renewal" }),
      ],
    });
    await screen.findByText("Northwind rollout");

    await userEvent.type(
      screen.getByLabelText("Filter opportunities by keyword"),
      "globex",
    );
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(screen.queryByText("Northwind rollout")).not.toBeInTheDocument();
    expect(screen.getByText("Globex renewal")).toBeInTheDocument();
    // The board's filter/sort model is applied to the already-fetched list
    // (`lib/domain.ts`'s `applyOpportunityView`), so filtering never sends a
    // second request.
    expect(api.callsTo("GET", "/api/opportunities")).toHaveLength(1);
  });

  it("filters and sorts using every control, then clears them", async () => {
    await renderDashboard({
      opportunities: [
        anOpportunity({
          id: 10,
          name: "Northwind rollout",
          stage: "Negotiation",
          value: "100",
          stalled: false,
        }),
        anOpportunity({
          id: 11,
          name: "Globex renewal",
          stage: "Negotiation",
          value: "300",
          stalled: true,
        }),
      ],
    });
    await screen.findByText("Northwind rollout");

    await userEvent.selectOptions(
      screen.getByLabelText("Filter by stage"),
      "Negotiation",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Filter by stalled status"),
      "Stalled only",
    );
    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "Value");
    await userEvent.selectOptions(
      screen.getByLabelText("Sort direction"),
      "Ascending",
    );
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(screen.queryByText("Northwind rollout")).not.toBeInTheDocument();
    expect(screen.getByText("Globex renewal")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByText("Northwind rollout")).toBeInTheDocument();
    expect(screen.getByLabelText("Filter by stage")).toHaveValue("");
  });

  it("keeps the board filter in the URL a reload would use", async () => {
    await renderDashboard(
      {
        opportunities: [
          anOpportunity({
            id: 10,
            name: "Northwind rollout",
            stage: "Negotiation",
          }),
          anOpportunity({ id: 11, name: "Globex renewal", stage: "Proposal" }),
        ],
      },
      "/?opportunities.stage=Negotiation",
    );
    await screen.findByText("Northwind rollout");

    expect(screen.getByLabelText("Filter by stage")).toHaveValue("Negotiation");
    expect(screen.queryByText("Globex renewal")).not.toBeInTheDocument();
  });

  it("applies a saved opportunities view and can save the current one", async () => {
    const api = await renderDashboard({
      opportunities: [
        anOpportunity({
          id: 10,
          name: "Northwind rollout",
          stage: "Negotiation",
        }),
        anOpportunity({ id: 11, name: "Globex renewal", stage: "Proposal" }),
      ],
      savedViews: [
        {
          id: 1,
          created_by: ALEX.id,
          creator_name: ALEX.name,
          name: "Negotiation only",
          entity: "opportunities",
          filters: { stage: "Negotiation" },
          sort: {},
          group_by: "stage",
          is_shared: false,
          is_default: false,
          created_at: "2026-09-01T00:00:00Z",
          updated_at: "2026-09-01T00:00:00Z",
        },
      ],
    });
    await screen.findByText("Northwind rollout");

    // By value: the option's text now carries the view's visibility too
    // (milestone 2.13), so its name alone no longer identifies it.
    await userEvent.selectOptions(
      await screen.findByLabelText("Saved opportunity views"),
      "1",
    );

    expect(screen.queryByText("Globex renewal")).not.toBeInTheDocument();
    expect(screen.getByText("Northwind rollout")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Save current opportunity view" }),
    );
    await userEvent.type(screen.getByLabelText("View name"), "My pipeline");
    await userEvent.click(screen.getByRole("button", { name: "Save view" }));

    await waitFor(() =>
      expect(api.callsTo("POST", "/api/v2/saved-views")).toHaveLength(1),
    );
    expect(api.callsTo("POST", "/api/v2/saved-views")[0].body).toMatchObject({
      name: "My pipeline",
      entity: "opportunities",
      filters: { stage: "Negotiation" },
      group_by: "stage",
    });
  });

  it("tells a reader with no saved views how to make one", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });
    await screen.findByText("Northwind rollout");

    await userEvent.click(
      screen.getByRole("button", { name: "Manage opportunity views" }),
    );
    expect(
      await screen.findByText(/You have not saved an? opportunity view yet/),
    ).toBeInTheDocument();
  });
});

describe("two view states in one URL (milestone 2.2)", () => {
  it("keeps the board's keyword filter out of the open timeline's query", async () => {
    // The board and the open timeline are mounted together (D-054) and share
    // one query string, so each has to own its own parameter names: a board
    // keyword is not a timeline keyword.
    const api = await renderDashboard(
      {
        opportunities: [anOpportunity({ id: 10, name: "Northwind rollout" })],
        entries: [anEntry()],
      },
      "/opportunities/10",
    );
    await screen.findByRole("heading", { name: "Discovery call" });
    const before = api.callsTo("GET", "/timeline").length;

    await userEvent.type(
      screen.getByLabelText("Filter opportunities by keyword"),
      "northwind",
    );
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    await waitFor(() =>
      expect(screen.queryByText("Globex renewal")).not.toBeInTheDocument(),
    );
    expect(api.callsTo("GET", "q=northwind")).toHaveLength(0);
    expect(api.callsTo("GET", "/timeline")).toHaveLength(before);
  });

  it("keeps the timeline's reading order when the board is filtered", async () => {
    const api = await renderDashboard(
      {
        opportunities: [
          anOpportunity({ id: 10, name: "Northwind rollout" }),
          anOpportunity({ id: 11, name: "Globex renewal" }),
        ],
        entries: [anEntry()],
      },
      "/opportunities/10?timeline.order=desc",
    );
    await screen.findByRole("heading", { name: "Discovery call" });

    await userEvent.selectOptions(
      screen.getByLabelText("Filter by stage"),
      "Negotiation",
    );
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    // Writing one state into the URL must not drop the other's parameters.
    await waitFor(() =>
      expect(screen.getByLabelText("Timeline reading order")).toHaveValue(
        "desc",
      ),
    );
    expect(api.callsTo("GET", "order=asc")).toHaveLength(0);
  });
});

describe("notifications", () => {
  it("lists unread notifications and marks one read without losing it from history", async () => {
    const api = await renderDashboard({
      notifications: [
        {
          id: 1,
          type: "mention",
          payload: {},
          read_at: null,
          created_at: "2026-09-03T09:00:00Z",
        },
      ],
    });

    await userEvent.click(
      screen.getByRole("button", { name: /Notifications/ }),
    );
    expect(
      await screen.findByText("You were mentioned in a timeline update."),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Mark read" }));

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/notifications/1/read")).toHaveLength(1),
    );
    // Milestone 1.7's whole point: a read notification stays in the inbox
    // (as history) instead of disappearing, unlike v1's `WHERE read = 0`.
    await waitFor(() =>
      expect(
        screen.getByText("You were mentioned in a timeline update."),
      ).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Mark read" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("marks every notification read and filters the inbox by type", async () => {
    const api = await renderDashboard({
      notifications: [
        {
          id: 1,
          type: "mention",
          payload: {},
          read_at: null,
          created_at: "2026-09-03T09:00:00Z",
        },
        {
          id: 2,
          type: "comment",
          payload: {},
          read_at: null,
          created_at: "2026-09-03T10:00:00Z",
        },
      ],
    });

    await userEvent.click(
      screen.getByRole("button", { name: /Notifications/ }),
    );
    expect(
      await screen.findByText("New comment on your note."),
    ).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Filter"), "Comments");
    expect(
      screen.queryByText("You were mentioned in a timeline update."),
    ).not.toBeInTheDocument();
    expect(screen.getByText("New comment on your note.")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Filter"), "All types");
    await userEvent.click(
      screen.getByRole("button", { name: "Mark all read" }),
    );

    await waitFor(() =>
      expect(
        api.callsTo("POST", "/api/v2/notifications/mark-all-read"),
      ).toHaveLength(1),
    );
    await waitFor(() =>
      expect(
        screen.queryAllByRole("button", { name: "Mark read" }),
      ).toHaveLength(0),
    );
  });
});
