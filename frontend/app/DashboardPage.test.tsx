import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ALEX, anEntry, anOpportunity } from "./test-api";
import { findCard, renderApp, renderDashboard } from "./test-app";

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

  it("creates an opportunity from the sidebar form", async () => {
    const api = await renderDashboard();

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
  });

  it("surfaces a rejected create instead of clearing the form", async () => {
    await renderDashboard({
      failures: { "POST /api/opportunities": [422, "Stage is not valid"] },
    });

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

    vi.spyOn(window, "confirm").mockReturnValue(false);
    await userEvent.click(within(card).getByRole("button", { name: "Delete" }));
    expect(api.callsTo("DELETE", "/api/opportunities/10")).toHaveLength(0);

    vi.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(within(card).getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(api.callsTo("DELETE", "/api/opportunities/10")).toHaveLength(1),
    );
    await waitFor(() =>
      expect(screen.queryByText("Northwind rollout")).not.toBeInTheDocument(),
    );
  });

  it("closes the timeline of an opportunity it just deleted", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });
    const card = await findCard("Northwind rollout");
    await userEvent.click(within(card).getByRole("link", { name: "Timeline" }));
    await screen.findByText("Your role: owner");

    vi.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(within(card).getByRole("button", { name: "Delete" }));

    expect(
      await screen.findByText("Select an opportunity to open its timeline."),
    ).toBeInTheDocument();
  });

  it("loads the edit form from the card and saves a stage change", async () => {
    const api = await renderDashboard({ opportunities: [anOpportunity()] });
    const card = (await screen.findAllByRole("article"))[0];

    await userEvent.click(within(card).getByRole("button", { name: "Edit" }));
    expect(
      screen.getByRole("heading", { name: "Edit Opportunity" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Opportunity")).toHaveValue(
      "Northwind rollout",
    );

    await userEvent.selectOptions(screen.getByLabelText("Stage"), "Closed Won");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(api.callsTo("PATCH", "/api/opportunities/10")).toHaveLength(1),
    );
    expect(api.callsTo("PATCH", "/api/opportunities/10")[0].body).toMatchObject(
      { stage: "Closed Won" },
    );
    expect(
      await screen.findByRole("heading", { name: "New Opportunity" }),
    ).toBeInTheDocument();
  });

  it("abandons an edit and empties the form", async () => {
    await renderDashboard({ opportunities: [anOpportunity()] });
    const card = (await screen.findAllByRole("article"))[0];

    await userEvent.click(within(card).getByRole("button", { name: "Edit" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel edit" }));

    expect(
      screen.getByRole("heading", { name: "New Opportunity" }),
    ).toBeInTheDocument();
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

    await userEvent.selectOptions(
      await screen.findByLabelText("Saved opportunity views"),
      "Negotiation only",
    );

    expect(screen.queryByText("Globex renewal")).not.toBeInTheDocument();
    expect(screen.getByText("Northwind rollout")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Save current opportunity view" }),
    );
    await userEvent.type(
      screen.getByLabelText("Saved opportunity view name"),
      "My pipeline",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Save opportunity view" }),
    );

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
