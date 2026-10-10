import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ALEX,
  BLAIR,
  aComment,
  aNote,
  anEntry,
  anOpportunity,
} from "./test-api";
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
    expect(api.callsTo("POST", "/api/v2/auth/signup")).toHaveLength(1);
    expect(await screen.findByText("Northwind rollout")).toBeInTheDocument();
  });

  it("shows the API's own message when sign-in is refused", async () => {
    renderApp({
      failures: {
        "POST /api/v2/auth/login": [401, "Invalid email or password"],
      },
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
      expect(api.callsTo("POST", "/api/v2/opportunities")).toHaveLength(1),
    );
    expect(api.callsTo("POST", "/api/v2/opportunities")[0].body).toMatchObject({
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
      expect(api.callsTo("POST", "/api/v2/opportunities")).toHaveLength(1),
    );
    expect(api.callsTo("POST", "/api/v2/opportunities")[0].body).toMatchObject({
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
      failures: { "POST /api/v2/opportunities": [422, "Stage is not valid"] },
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
    expect(api.callsTo("DELETE", "/api/v2/opportunities/10")).toHaveLength(0);

    await userEvent.click(within(card).getByRole("button", { name: "Delete" }));
    await acceptConfirmation("Northwind rollout");
    await waitFor(() =>
      expect(api.callsTo("DELETE", "/api/v2/opportunities/10")).toHaveLength(1),
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
      expect(api.callsTo("PATCH", "/api/v2/opportunities/10")).toHaveLength(1),
    );
    expect(
      api.callsTo("PATCH", "/api/v2/opportunities/10")[0].body,
    ).toMatchObject({ stage: "Closed Won" });
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

  // Milestone 2.9a / D-091: 2.2 put the applied view in the query string on
  // purpose, so it survives a reload. It must not survive a sign-out too —
  // otherwise whoever signs in next, in the same tab, lands on the previous
  // reader's filtered view with no idea why.
  it("resets the view state in the URL on sign-out, for the next reader in this tab", async () => {
    await renderDashboard(
      { opportunities: [anOpportunity()] },
      "/?opportunities.view=table",
    );
    expect(screen.getByRole("button", { name: "Table" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await screen.findByRole("button", { name: "Create account" });

    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await userEvent.type(screen.getByLabelText("Email"), "casey@opptrail.test");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(
      screen.getAllByRole("button", { name: "Sign in" })[1],
    );

    await screen.findByRole("heading", { name: "Opportunities" });
    expect(screen.getByRole("button", { name: "Board" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("reports an opportunity list that will not load", async () => {
    renderApp({
      user: ALEX,
      failures: {
        "GET /api/v2/opportunities": [503, "Database is unavailable"],
      },
    });

    expect(
      await screen.findByText("Database is unavailable"),
    ).toBeInTheDocument();
  });
});

describe("reading a paginated collection (milestone 2.9)", () => {
  it("walks every page of the opportunity list, not just the first", async () => {
    // `/api/v2/opportunities` is keyset-paginated, and the board needs the
    // whole set: its keyboard cursor, its bulk selection and the calendar's
    // month are all derived from the filtered list, not from a window of it.
    // `useOpportunities` therefore follows `next_cursor` to the end (D-093).
    const api = await renderDashboard({
      pageSize: 2,
      opportunities: [
        anOpportunity({ id: 10, name: "Northwind rollout" }),
        anOpportunity({ id: 11, name: "Globex renewal" }),
        anOpportunity({ id: 12, name: "Initech expansion" }),
      ],
    });

    expect(await screen.findByText("Initech expansion")).toBeInTheDocument();
    expect(screen.getByText("Northwind rollout")).toBeInTheDocument();
    expect(screen.getByText("Globex renewal")).toBeInTheDocument();

    // Two pages of two, then the page that answers `next_cursor: null`.
    const reads = api.calls.filter(
      (call) =>
        call.method === "GET" && call.path.startsWith("/api/v2/opportunities?"),
    );
    expect(reads).toHaveLength(2);
    expect(reads[0].path).toContain("limit=200");
    expect(reads[1].path).toContain("cursor=2");
  });

  it("stops after one request when the first page is the last", async () => {
    const api = await renderDashboard({
      opportunities: [anOpportunity({ id: 10, name: "Northwind rollout" })],
    });
    await screen.findByText("Northwind rollout");

    expect(
      api.calls.filter(
        (call) =>
          call.method === "GET" &&
          call.path.startsWith("/api/v2/opportunities?"),
      ),
    ).toHaveLength(1);
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

  it("disables the actions that write to an opportunity when the selection includes one the reader does not own", async () => {
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
      within(bulkBar()).getByRole("button", { name: "Assign owner" }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        "Change stage, assign owner and delete are limited to opportunities you own.",
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

  it("hands the checked opportunities to another user", async () => {
    const api = await renderDashboard({
      opportunities: [
        anOpportunity({ id: 10, name: "First" }),
        anOpportunity({ id: 11, name: "Second" }),
      ],
    });
    await findCard("First");

    await userEvent.click(checkboxFor("First"));
    await userEvent.click(checkboxFor("Second"));
    await userEvent.type(
      screen.getByLabelText("Assign owner by email"),
      BLAIR.email,
    );
    await userEvent.click(screen.getByRole("button", { name: "Assign owner" }));

    await waitFor(() =>
      expect(api.callsTo("POST", "/api/v2/opportunities/bulk")).toHaveLength(1),
    );
    expect(
      api.callsTo("POST", "/api/v2/opportunities/bulk")[0].body,
    ).toMatchObject({
      ids: [10, 11],
      action: "assign_owner",
      new_owner_email: BLAIR.email,
    });
    expect(
      await screen.findByText("2 opportunities handed over."),
    ).toBeInTheDocument();
  });

  it("reports an ownership transfer to an address nobody uses", async () => {
    await renderDashboard({
      opportunities: [anOpportunity({ id: 10, name: "First" })],
    });
    await findCard("First");

    await userEvent.click(checkboxFor("First"));
    await userEvent.type(
      screen.getByLabelText("Assign owner by email"),
      "nobody@example.com",
    );
    await userEvent.click(screen.getByRole("button", { name: "Assign owner" }));

    // A whole-request failure, so it arrives as a thrown error rather than as
    // a per-item result: nothing was applied.
    expect(
      await screen.findByText(
        "Could not assign owner: User with that email was not found",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("1 selected")).toBeInTheDocument();
  });

  it("pins the checked opportunities into one of the reader's own views", async () => {
    const api = await renderDashboard({
      opportunities: [
        anOpportunity({ id: 10, name: "First" }),
        anOpportunity({ id: 11, name: "Second" }),
      ],
      savedViews: [
        {
          id: 1,
          created_by: ALEX.id,
          creator_name: ALEX.name,
          name: "My shortlist",
          entity: "opportunities",
          filters: {},
          sort: {},
          group_by: "stage",
          is_shared: false,
          is_default: false,
          created_at: "2026-09-01T00:00:00Z",
          updated_at: "2026-09-01T00:00:00Z",
        },
        {
          id: 2,
          created_by: BLAIR.id,
          creator_name: BLAIR.name,
          name: "Blair's shortlist",
          entity: "opportunities",
          filters: {},
          sort: {},
          group_by: "stage",
          is_shared: true,
          is_default: false,
          created_at: "2026-09-01T00:00:00Z",
          updated_at: "2026-09-01T00:00:00Z",
        },
      ],
    });
    await findCard("First");

    await userEvent.click(checkboxFor("First"));
    const viewPicker = within(bulkBar()).getByLabelText("Add to saved view");
    // A colleague's shared view is readable and still not a target: adding to
    // it would change what every signed-in reader sees through it (D-106).
    expect(
      within(viewPicker).queryByText(/Blair's shortlist/),
    ).not.toBeInTheDocument();

    await userEvent.selectOptions(viewPicker, "1");
    await userEvent.click(screen.getByRole("button", { name: "Add to view" }));

    await waitFor(() =>
      expect(api.callsTo("POST", "/api/v2/opportunities/bulk")).toHaveLength(1),
    );
    expect(
      api.callsTo("POST", "/api/v2/opportunities/bulk")[0].body,
    ).toMatchObject({ ids: [10], action: "add_to_view", view_id: 1 });
    expect(
      await screen.findByText("1 opportunity added to the view."),
    ).toBeInTheDocument();

    // Applying the view now draws the pinned selection and says so.
    await userEvent.selectOptions(
      await screen.findByLabelText("Saved opportunity views"),
      "1",
    );
    expect(screen.queryByText("Second")).not.toBeInTheDocument();
    expect(
      screen.getByText(/Showing 1 pinned opportunity from a saved view/),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(await screen.findByText("Second")).toBeInTheDocument();
  });

  it("offers the selection as one export link per format", async () => {
    await renderDashboard({
      opportunities: [
        anOpportunity({ id: 10, name: "First" }),
        anOpportunity({ id: 11, name: "Second" }),
      ],
    });
    await findCard("First");

    await userEvent.click(checkboxFor("First"));
    await userEvent.click(checkboxFor("Second"));

    // A read, so it is a link rather than a mutation (D-107).
    expect(
      within(bulkBar()).getByRole("link", { name: "Export CSV" }),
    ).toHaveAttribute("href", "/api/v2/opportunities/export/csv?ids=10,11");
    expect(
      within(bulkBar()).getByRole("link", { name: "Export JSON" }),
    ).toHaveAttribute("href", "/api/v2/opportunities/export/json?ids=10,11");
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
      expect(api.callsTo("PATCH", "/api/v2/opportunities/10")).toHaveLength(1),
    );
    expect(api.callsTo("PATCH", "/api/v2/opportunities/10")[0].body).toEqual({
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

    expect(api.callsTo("PATCH", "/api/v2/opportunities/10")).toHaveLength(0);
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
      expect(api.callsTo("PATCH", "/api/v2/opportunities/10")).toHaveLength(1),
    );
    expect(api.callsTo("PATCH", "/api/v2/opportunities/10")[0].body).toEqual({
      stage: "Negotiation",
    });
  });

  it("puts the card back and explains when the move is refused", async () => {
    await renderDashboard({
      opportunities: [anOpportunity({ stage: "Prospecting" })],
      failures: {
        "PATCH /api/v2/opportunities/10": [403, "Only the owner may do that"],
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
    expect(api.callsTo("GET", "/api/v2/opportunities")).toHaveLength(1);
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
      expect(api.callsTo("PATCH", "/api/v2/opportunities/10")).toHaveLength(1),
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
      expect(api.callsTo("DELETE", "/api/v2/opportunities/10")).toHaveLength(1),
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

describe("the table view (milestone 2.8)", () => {
  const deals = [
    anOpportunity({
      id: 10,
      name: "Northwind rollout",
      account_name: "Northwind",
      stage: "Negotiation",
      value: "185000",
      updated_at: "2026-09-02T10:00:00Z",
    }),
    anOpportunity({
      id: 11,
      name: "Globex renewal",
      account_name: "Globex",
      stage: "Proposal",
      value: "42000",
      updated_at: "2026-09-03T10:00:00Z",
    }),
  ];

  it("draws the default columns, and only those", async () => {
    await renderDashboard(
      { opportunities: deals },
      "/?opportunities.view=table",
    );

    const row = await findCard("Northwind rollout");
    // The five default columns plus the name, which is never optional.
    expect(within(row).getByText("Northwind")).toBeInTheDocument();
    expect(within(row).getByText("USD 185,000")).toBeInTheDocument();
    expect(within(row).getByText("2026-12-01")).toBeInTheDocument();
    // "Created" is offered by the picker and off by default.
    expect(
      screen.queryByRole("button", { name: "Sort by Created" }),
    ).toBeNull();
  });

  it("turns a column on, and says so in the URL", async () => {
    await renderDashboard(
      { opportunities: deals },
      "/?opportunities.view=table",
    );
    await screen.findByText("Northwind rollout");

    await userEvent.click(screen.getByRole("button", { name: "Columns (5)" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Created" }));

    expect(
      screen.getByRole("button", { name: "Sort by Created" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Columns (6)" }),
    ).toBeInTheDocument();
  });

  it("turns a column off again, and says so in the URL", async () => {
    await renderDashboard(
      { opportunities: deals },
      "/?opportunities.view=table",
    );
    await screen.findByText("Northwind rollout");

    await userEvent.click(screen.getByRole("button", { name: "Columns (5)" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Owner" }));

    expect(screen.queryByRole("button", { name: "Sort by Owner" })).toBeNull();
    expect(
      screen.getByRole("button", { name: "Columns (4)" }),
    ).toBeInTheDocument();
  });

  it("refuses to turn off the last column standing", async () => {
    await renderDashboard(
      { opportunities: deals },
      "/?opportunities.view=table&opportunities.columns=value",
    );
    await screen.findByText("Northwind rollout");

    await userEvent.click(screen.getByRole("button", { name: "Columns (1)" }));
    // A table of names alone is the list view, which is one click away in the
    // switcher.
    expect(screen.getByRole("checkbox", { name: "Value" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "Account" })).toBeEnabled();
  });

  it("sorts from a column header, and reverses it on a second click", async () => {
    await renderDashboard(
      { opportunities: deals },
      "/?opportunities.view=table",
    );
    await screen.findByText("Northwind rollout");

    await userEvent.click(
      screen.getByRole("button", { name: "Sort by Value" }),
    );
    let rows = screen.getAllByRole("article");
    expect(rows[0]).toHaveTextContent("Globex renewal");

    await userEvent.click(
      screen.getByRole("button", { name: "Sort by Value" }),
    );
    rows = screen.getAllByRole("article");
    expect(rows[0]).toHaveTextContent("Northwind rollout");
  });

  it("is the same setting the filter bar's sort dropdown writes", async () => {
    await renderDashboard(
      { opportunities: deals },
      "/?opportunities.view=table",
    );
    await screen.findByText("Northwind rollout");

    await userEvent.click(
      screen.getByRole("button", { name: "Sort by Value" }),
    );

    // One setting asked two ways: the dropdown shows what the header did.
    expect(screen.getByLabelText("Sort by")).toHaveValue("value");
    expect(screen.getByLabelText("Sort direction")).toHaveValue("asc");
  });

  it("sorts stages down the pipeline from the header too", async () => {
    await renderDashboard(
      { opportunities: deals },
      "/?opportunities.view=table",
    );
    await screen.findByText("Northwind rollout");

    await userEvent.click(
      screen.getByRole("button", { name: "Sort by Stage" }),
    );

    const rows = screen.getAllByRole("article");
    expect(rows[0]).toHaveTextContent("Globex renewal");
  });

  it("moves a row's stage through the same control every other view uses", async () => {
    const api = await renderDashboard(
      { opportunities: [anOpportunity({ stage: "Prospecting" })] },
      "/?opportunities.view=table",
    );
    await screen.findByText("Northwind rollout");

    await userEvent.selectOptions(
      screen.getByLabelText("Move Northwind rollout to stage"),
      "Proposal",
    );

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/v2/opportunities/10")).toHaveLength(1),
    );
  });

  it("shows a viewer the stage as text, with no controls", async () => {
    await renderDashboard(
      { opportunities: [anOpportunity({ current_user_role: "viewer" })] },
      "/?opportunities.view=table",
    );

    const row = await findCard("Northwind rollout");
    expect(within(row).getByText("Negotiation")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Edit" })).toBeNull();
    expect(
      screen.queryByLabelText("Move Northwind rollout to stage"),
    ).toBeNull();
  });

  it("edits and deletes a row, the same way every other view does", async () => {
    const api = await renderDashboard(
      { opportunities: [anOpportunity()] },
      "/?opportunities.view=table",
    );
    const row = await findCard("Northwind rollout");

    await userEvent.click(within(row).getByRole("button", { name: "Edit" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent(
      "Edit opportunity",
    );
    await userEvent.keyboard("{Escape}");

    await userEvent.click(
      within(await findCard("Northwind rollout")).getByRole("button", {
        name: "Delete",
      }),
    );
    await acceptConfirmation("Northwind rollout");
    await waitFor(() =>
      expect(api.callsTo("DELETE", "/api/v2/opportunities/10")).toHaveLength(1),
    );
  });

  it("moves the cursor down the rows, and scrolls to follow it", async () => {
    await renderDashboard(
      { opportunities: deals },
      "/?opportunities.view=table",
    );
    await screen.findByText("Northwind rollout");

    // `j` twice: the sorted order is last activity first, so Globex then
    // Northwind. `x` acts on whichever the cursor is on.
    await userEvent.keyboard("jjx");
    expect(checkboxFor("Northwind rollout")).toBeChecked();
    expect(checkboxFor("Globex renewal")).not.toBeChecked();
  });

  it("keeps the declared column order however the columns were ticked", async () => {
    await renderDashboard(
      { opportunities: deals },
      "/?opportunities.view=table&opportunities.columns=owner_name",
    );
    await screen.findByText("Northwind rollout");

    await userEvent.click(screen.getByRole("button", { name: "Columns (1)" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Account" }));

    // Account is declared before Owner, so it is drawn first whichever was
    // ticked first - a table's columns read the same way for everyone.
    const headers = screen
      .getAllByRole("button", { name: /^Sort by / })
      .map((button) => button.getAttribute("aria-label"));
    expect(headers).toEqual([
      "Sort by Opportunity",
      "Sort by Account",
      "Sort by Owner",
    ]);
  });

  it("switches density, and only offers the control where it means something", async () => {
    await renderDashboard(
      { opportunities: deals },
      "/?opportunities.view=table",
    );
    await screen.findByText("Northwind rollout");

    await userEvent.selectOptions(
      screen.getByLabelText("Row density"),
      "compact",
    );
    // A root attribute, not a component variant (D-075): one block of size
    // tokens changes and every row reads them.
    expect(document.documentElement.dataset.density).toBe("compact");

    await userEvent.click(screen.getByRole("button", { name: "Board" }));
    expect(screen.queryByLabelText("Row density")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Columns/ })).toBeNull();
  });
});

describe("editing a table cell where it is read (milestone 2.11)", () => {
  // Built per test, not once for the describe: these tests write, and the
  // fake API edits the row objects it was handed in place — exactly as the
  // real one edits the database.
  function deals() {
    return [
      anOpportunity({
        id: 10,
        name: "Northwind rollout",
        account_name: "Northwind",
        value: "185000",
        expected_close_date: "2026-12-01",
      }),
      anOpportunity({
        id: 11,
        name: "Globex renewal",
        account_name: "Globex",
        value: "42000",
      }),
    ];
  }

  it("edits an account in its own cell, sending only that field", async () => {
    const api = await renderDashboard(
      { opportunities: deals() },
      "/?opportunities.view=table",
    );

    const row = await findCard("Northwind rollout");
    await userEvent.click(within(row).getByTitle("Edit Account"));
    await userEvent.clear(within(row).getByLabelText("Account"));
    await userEvent.type(
      within(row).getByLabelText("Account"),
      "Northwind Traders",
    );
    await userEvent.click(
      within(row).getByRole("button", { name: "Save Account" }),
    );

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/v2/opportunities/10")).toHaveLength(1),
    );
    // A partial PATCH: nothing the reader did not touch is rewritten.
    expect(api.callsTo("PATCH", "/api/v2/opportunities/10")[0].body).toEqual({
      account_name: "Northwind Traders",
    });
    // Optimistic, so the cell reads the new value without waiting for the
    // list to be fetched again.
    expect(
      within(await findCard("Northwind rollout")).getByText(
        "Northwind Traders",
      ),
    ).toBeInTheDocument();
  });

  it("edits a value and a close date in their own cells", async () => {
    const api = await renderDashboard(
      { opportunities: deals() },
      "/?opportunities.view=table",
    );

    const row = await findCard("Northwind rollout");
    await userEvent.click(within(row).getByTitle("Edit Value"));
    await userEvent.clear(within(row).getByLabelText("Value"));
    await userEvent.type(within(row).getByLabelText("Value"), "200000");
    await userEvent.keyboard("{Enter}");

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/v2/opportunities/10")).toHaveLength(1),
    );
    expect(api.callsTo("PATCH", "/api/v2/opportunities/10")[0].body).toEqual({
      value: "200000",
    });

    const again = await findCard("Northwind rollout");
    await userEvent.click(within(again).getByTitle("Edit Close date"));
    await userEvent.clear(within(again).getByLabelText("Close date"));
    await userEvent.click(
      within(again).getByRole("button", { name: "Save Close date" }),
    );

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/v2/opportunities/10")).toHaveLength(2),
    );
    // Cleared, not omitted: the route updates exactly the keys it is given.
    expect(api.callsTo("PATCH", "/api/v2/opportunities/10")[1].body).toEqual({
      expected_close_date: null,
    });
  });

  it("leaves the name alone, because the name is the link to the timeline", async () => {
    await renderDashboard(
      { opportunities: deals() },
      "/?opportunities.view=table",
    );

    const row = await findCard("Northwind rollout");
    expect(
      within(row).getByRole("link", { name: "Northwind rollout" }),
    ).toBeInTheDocument();
    expect(within(row).queryByTitle("Edit Opportunity")).toBeNull();
  });

  it("offers no cell editor on a row the reader does not own", async () => {
    await renderDashboard(
      {
        opportunities: [
          anOpportunity({
            id: 12,
            name: "Initech expansion",
            current_user_role: "editor",
            owner_id: BLAIR.id,
            owner_name: BLAIR.name,
          }),
        ],
      },
      "/?opportunities.view=table",
    );

    const row = await findCard("Initech expansion");
    expect(within(row).queryByTitle("Edit Account")).toBeNull();
    expect(within(row).queryByTitle("Edit Value")).toBeNull();
    expect(within(row).getByText("Northwind")).toBeInTheDocument();
  });

  it("puts the old value back and says so when the server refuses", async () => {
    await renderDashboard(
      {
        opportunities: deals(),
        failures: { "PATCH /api/v2/opportunities/10": [403, "Not the owner"] },
      },
      "/?opportunities.view=table",
    );

    const row = await findCard("Northwind rollout");
    await userEvent.click(within(row).getByTitle("Edit Account"));
    await userEvent.clear(within(row).getByLabelText("Account"));
    await userEvent.type(within(row).getByLabelText("Account"), "Wrongwind");
    await userEvent.click(
      within(row).getByRole("button", { name: "Save Account" }),
    );

    expect(
      await screen.findByText(
        "Could not change the account of Northwind rollout: Not the owner",
      ),
    ).toBeInTheDocument();
    expect(
      within(await findCard("Northwind rollout")).getByText("Northwind"),
    ).toBeInTheDocument();
  });
});

describe("the calendar view (milestone 2.8)", () => {
  const deals = [
    anOpportunity({
      id: 10,
      name: "Northwind rollout",
      expected_close_date: "2026-12-02",
    }),
    anOpportunity({
      id: 11,
      name: "Globex renewal",
      expected_close_date: "2026-12-20",
    }),
    anOpportunity({
      id: 12,
      name: "Initech pilot",
      expected_close_date: null,
    }),
    anOpportunity({
      id: 13,
      name: "Umbrella expansion",
      expected_close_date: "2027-01-15",
    }),
  ];

  const december = "/?opportunities.view=calendar&opportunities.month=2026-12";

  it("places each deal on its close date and names the month", async () => {
    await renderDashboard({ opportunities: deals }, december);

    expect(
      await screen.findByRole("heading", { name: "December 2026" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Northwind rollout")).toBeInTheDocument();
    expect(screen.getByText("Globex renewal")).toBeInTheDocument();
    // Closing in another month, so not on this one.
    expect(screen.queryByText("Umbrella expansion")).toBeNull();
  });

  it("lists what it cannot place rather than dropping it", async () => {
    await renderDashboard({ opportunities: deals }, december);
    await screen.findByRole("heading", { name: "December 2026" });

    // A view that silently omits rows is how a reader concludes they have
    // fewer deals than they do - the failure D-076 found in the empty states.
    expect(
      screen.getByRole("heading", { name: "No close date (1)" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Initech pilot")).toBeInTheDocument();
  });

  it("walks to another month and back, keeping it in the URL", async () => {
    await renderDashboard({ opportunities: deals }, december);
    await screen.findByRole("heading", { name: "December 2026" });

    await userEvent.click(screen.getByRole("button", { name: "Next month" }));
    expect(
      screen.getByRole("heading", { name: "January 2027" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Umbrella expansion")).toBeInTheDocument();
    expect(screen.queryByText("Northwind rollout")).toBeNull();

    await userEvent.click(
      screen.getByRole("button", { name: "Previous month" }),
    );
    expect(
      screen.getByRole("heading", { name: "December 2026" }),
    ).toBeInTheDocument();
  });

  it("opens on the reader's own month when the link names none", async () => {
    await renderDashboard(
      { opportunities: deals },
      "/?opportunities.view=calendar",
    );

    // The month is resolved rather than stored, so a shared link opens where
    // the reader is rather than where it was written.
    const thisMonth = new Date().toLocaleDateString("en-US", {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    });
    expect(
      await screen.findByRole("heading", { name: thisMonth }),
    ).toBeInTheDocument();
  });

  it("comes back to the reader's own month from wherever it walked to", async () => {
    await renderDashboard({ opportunities: deals }, december);
    await screen.findByRole("heading", { name: "December 2026" });

    await userEvent.click(screen.getByRole("button", { name: "Next month" }));
    await userEvent.click(screen.getByRole("button", { name: "Today" }));

    const thisMonth = new Date().toLocaleDateString("en-US", {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    });
    expect(
      screen.getByRole("heading", { name: thisMonth }),
    ).toBeInTheDocument();
  });

  it("walks the drawn month with the keyboard, in date order", async () => {
    await renderDashboard({ opportunities: deals }, december);
    await screen.findByRole("heading", { name: "December 2026" });

    // `j` twice: the 2nd, then the 20th. The undated one comes after those,
    // and the January deal is not on screen so the cursor never reaches it.
    await userEvent.keyboard("jx");
    expect(
      screen.getByRole("checkbox", {
        name: "Select Northwind rollout for bulk actions",
      }),
    ).toBeChecked();

    await userEvent.keyboard("jjx");
    expect(
      screen.getByRole("checkbox", {
        name: "Select Initech pilot for bulk actions",
      }),
    ).toBeChecked();
  });

  it("keeps a selection made in another view, even when the month hides it", async () => {
    await renderDashboard(
      { opportunities: deals },
      "/?opportunities.view=list",
    );
    await screen.findByText("Umbrella expansion");

    await userEvent.click(checkboxFor("Umbrella expansion"));
    await userEvent.click(screen.getByRole("button", { name: "Calendar" }));

    // January's deal is not drawn in December, but it is still selected: the
    // action bar acts on everything the filters let through, not on what one
    // month happens to show.
    expect(screen.queryByText("Umbrella expansion")).toBeNull();
    expect(bulkBar()).toHaveTextContent("1 selected");
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
    expect(api.callsTo("GET", "/api/v2/opportunities")).toHaveLength(1);
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
    // The timeline's bar is collapsed unless a filter is applied (milestone
    // 3.7) and `order=desc` is the default, so it is opened here to read the
    // control the assertion below is about.
    await userEvent.click(
      screen.getByRole("button", { name: "Filter and order" }),
    );

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
  it("follows a notification to the row it is about (milestone 6.1a)", async () => {
    // The human's ruling. Until this the panel rendered no anchor at all, so
    // "you were mentioned in a comment" left the reader to go and find it.
    const api = await renderDashboard({
      opportunities: [anOpportunity({ id: 10, name: "Northwind rollout" })],
      entries: [
        anEntry({
          id: 100,
          title: "Security review",
          notes: [aNote({ id: 200, comments: [aComment({ id: 300 })] })],
        }),
      ],
      notifications: [
        {
          id: 1,
          type: "mention",
          payload: {
            opportunity_id: 10,
            source_type: "comment",
            source_id: 300,
            actor_id: 2,
            email: "alex@example.com",
          },
          read_at: null,
          created_at: "2026-09-03T09:00:00Z",
        },
      ],
    });

    await userEvent.click(
      screen.getByRole("button", { name: /Notifications/ }),
    );
    await userEvent.click(
      await screen.findByRole("link", {
        name: "You were mentioned in a timeline update.",
      }),
    );

    // It lands on the comment, marked -- 6.0's mechanism, not a second one.
    await waitFor(() =>
      expect(document.querySelector(".comment-row.is-linked")).not.toBeNull(),
    );
    // Clicking through is reading it.
    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/v2/notifications/1/read")).toHaveLength(
        1,
      ),
    );
    // And the panel closes, rather than covering the row it just opened.
    expect(
      screen.queryByText("You were mentioned in a timeline update."),
    ).not.toBeInTheDocument();
  });

  it("offers no link when access was just removed", async () => {
    // The reader cannot open what it is about, so a link would be a 404.
    await renderDashboard({
      notifications: [
        {
          id: 2,
          type: "share_removed",
          payload: { opportunity_id: 10, actor_id: 2, role: "viewer" },
          read_at: null,
          created_at: "2026-09-03T09:00:00Z",
        },
      ],
    });

    await userEvent.click(
      screen.getByRole("button", { name: /Notifications/ }),
    );
    expect(
      await screen.findByText("Your opportunity access was removed."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", {
        name: "Your opportunity access was removed.",
      }),
    ).not.toBeInTheDocument();
    // Still markable, which is why the button is not replaced by the link.
    expect(
      screen.getByRole("button", { name: "Mark read" }),
    ).toBeInTheDocument();
  });

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
      expect(api.callsTo("PATCH", "/api/v2/notifications/1/read")).toHaveLength(
        1,
      ),
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
