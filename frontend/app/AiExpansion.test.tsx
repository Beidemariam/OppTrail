import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ALEX, anEntry, anOpportunity } from "./test-api";
import { openTimeline, renderDashboard } from "./test-app";

/**
 * The AI expansion on screen (milestone 6.4, `docs/FEATURES.md` §14).
 *
 * What the model is asked and what comes back is
 * `backend/tests/test_ai_expansion.py`. What matters here is the half a
 * person meets: an answer that appears as it is written, a date range that
 * says what it is while shut, and a filter proposal that can be read before
 * it is applied — which is the whole safety argument for the last one.
 */
beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  document.cookie = "opptrail_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

async function openSidebar() {
  await renderDashboard({
    user: ALEX,
    opportunities: [anOpportunity()],
    entries: [anEntry()],
  });
  await openTimeline("Northwind rollout");
  return (await screen.findByRole("heading", { name: "AI Agent" })).closest(
    "aside",
  ) as HTMLElement;
}

describe("an answer that arrives as it is written", () => {
  it("assembles the pieces into one answer with its citations", async () => {
    const sidebar = await openSidebar();

    await userEvent.type(
      within(sidebar).getByLabelText(/Ask the read-only AI agent/),
      "Where do we stand?",
    );
    await userEvent.click(within(sidebar).getByRole("button", { name: "Ask" }));

    // The deltas arrive as separate frames and the reader sees one sentence.
    expect(
      await within(sidebar).findByText("Answer to: Where do we stand?"),
    ).toBeInTheDocument();
    // The citations come with `done`, because they are computed from the
    // finished text.
    expect(await within(sidebar).findByText(/Entries: 1/)).toBeInTheDocument();
  });

  it("shows the question immediately, before any of the answer exists", async () => {
    // D-168 measured a ~29s floor before this model says anything at all.
    // The question appearing at once is what tells the reader it was heard.
    const sidebar = await openSidebar();
    await userEvent.type(
      within(sidebar).getByLabelText(/Ask the read-only AI agent/),
      "Anything?",
    );
    await userEvent.click(within(sidebar).getByRole("button", { name: "Ask" }));

    expect(await within(sidebar).findByText("Anything?")).toBeInTheDocument();
  });
});

describe("limiting the question to a date range", () => {
  it("is shut by default and says what it is once set", async () => {
    const sidebar = await openSidebar();
    const trigger = within(sidebar).getByRole("button", {
      name: /Limit to dates/,
    });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(trigger);
    await userEvent.type(within(sidebar).getByLabelText("From"), "2026-06-01");

    // The rule `TimelineFilterBar` follows: a scope that is in force has to
    // be legible while its control is shut (D-136 finding 5).
    expect(
      within(sidebar).getByRole("button", { name: /From 2026-06-01/ }),
    ).toBeInTheDocument();
  });

  it("sends the range with the question", async () => {
    const api = await renderDashboard({
      user: ALEX,
      opportunities: [anOpportunity()],
      entries: [anEntry()],
    });
    await openTimeline("Northwind rollout");
    const sidebar = (
      await screen.findByRole("heading", { name: "AI Agent" })
    ).closest("aside") as HTMLElement;

    await userEvent.click(
      within(sidebar).getByRole("button", { name: /Limit to dates/ }),
    );
    await userEvent.type(within(sidebar).getByLabelText("From"), "2026-06-01");
    await userEvent.type(within(sidebar).getByLabelText("To"), "2026-06-30");
    await userEvent.type(
      within(sidebar).getByLabelText(/Ask the read-only AI agent/),
      "What happened?",
    );
    await userEvent.click(within(sidebar).getByRole("button", { name: "Ask" }));

    await waitFor(() => {
      const call = api.calls.find((item) =>
        item.path.includes("/ai/ask/stream"),
      );
      expect(call?.body).toMatchObject({
        question: "What happened?",
        since: "2026-06-01",
        until: "2026-06-30",
      });
    });
  });

  it("keeps the range for the next question", async () => {
    // Somebody scoping to a quarter usually has more than one question
    // about it, so the control sits outside the form that clears.
    const sidebar = await openSidebar();
    await userEvent.click(
      within(sidebar).getByRole("button", { name: /Limit to dates/ }),
    );
    await userEvent.type(within(sidebar).getByLabelText("From"), "2026-06-01");
    await userEvent.type(
      within(sidebar).getByLabelText(/Ask the read-only AI agent/),
      "First question",
    );
    await userEvent.click(within(sidebar).getByRole("button", { name: "Ask" }));

    expect(
      await within(sidebar).findByRole("button", { name: /From 2026-06-01/ }),
    ).toBeInTheDocument();
  });
});

describe("a sentence as a filter you can read first", () => {
  it("shows what it would set, in the filter bar's own words", async () => {
    await renderDashboard({
      user: ALEX,
      opportunities: [anOpportunity()],
    });

    await userEvent.click(
      await screen.findByRole("button", { name: "Describe a filter" }),
    );
    await userEvent.type(
      screen.getByLabelText(/Describe what you are looking for/),
      "deals stuck in negotiation over 50k",
    );
    await userEvent.click(screen.getByRole("button", { name: "Suggest" }));

    // Scoped to the panel: "Stalled only" is also an option in the filter
    // bar's own select, which is the point -- the proposal is described in
    // the words the controls use, so the two can be compared (D-186).
    const panel = document.querySelector(".ai-filter-panel") as HTMLElement;
    expect(
      await within(panel).findByText("Stage is Negotiation"),
    ).toBeInTheDocument();
    expect(within(panel).getByText("Value is at least 50000")).toBeTruthy();
    expect(within(panel).getByText("Stalled only")).toBeTruthy();
  });

  it("applies nothing until Apply is pressed", async () => {
    await renderDashboard({
      user: ALEX,
      opportunities: [anOpportunity({ stage: "Prospecting" })],
    });

    await userEvent.click(
      await screen.findByRole("button", { name: "Describe a filter" }),
    );
    await userEvent.type(
      screen.getByLabelText(/Describe what you are looking for/),
      "negotiation deals",
    );
    await userEvent.click(screen.getByRole("button", { name: "Suggest" }));
    const panel = document.querySelector(".ai-filter-panel") as HTMLElement;
    await within(panel).findByText("Stage is Negotiation");

    // The board still shows the Prospecting deal: a proposal is a proposal.
    expect(screen.getByText("Northwind rollout")).toBeInTheDocument();

    await userEvent.click(within(panel).getByRole("button", { name: "Apply" }));

    // And now the filter is in force, which the bar itself reports.
    await waitFor(() =>
      expect(screen.getByLabelText("Filter by stage")).toHaveValue(
        "Negotiation",
      ),
    );
    expect(screen.getByLabelText("Filter by minimum value")).toHaveValue(50000);
  });

  it("names what it could not use rather than swallowing it", async () => {
    await renderDashboard({
      user: ALEX,
      opportunities: [anOpportunity()],
      filterProposal: {
        proposal: {
          stage: "Negotiation",
          q: null,
          min_value: null,
          max_value: null,
          stalled: null,
          sort: null,
          direction: null,
        },
        ignored: ["owner", "closing_before"],
        empty: false,
      },
    });

    await userEvent.click(
      await screen.findByRole("button", { name: "Describe a filter" }),
    );
    await userEvent.type(
      screen.getByLabelText(/Describe what you are looking for/),
      "Alex's deals closing this month",
    );
    await userEvent.click(screen.getByRole("button", { name: "Suggest" }));

    expect(
      await screen.findByText("Could not express: owner; closing_before."),
    ).toBeInTheDocument();
  });

  it("says plainly when nothing could be turned into a filter", async () => {
    await renderDashboard({
      user: ALEX,
      opportunities: [anOpportunity()],
      filterProposal: {
        proposal: {
          q: null,
          stage: null,
          min_value: null,
          max_value: null,
          stalled: null,
          sort: null,
          direction: null,
        },
        ignored: [],
        empty: true,
      },
    });

    await userEvent.click(
      await screen.findByRole("button", { name: "Describe a filter" }),
    );
    await userEvent.type(
      screen.getByLabelText(/Describe what you are looking for/),
      "hello",
    );
    await userEvent.click(screen.getByRole("button", { name: "Suggest" }));

    const panel = document.querySelector(".ai-filter-panel") as HTMLElement;
    expect(
      await within(panel).findByText(
        /Nothing in that could be turned into a filter/,
      ),
    ).toBeInTheDocument();
    // No Apply, because there is nothing to apply.
    expect(within(panel).queryByRole("button", { name: "Apply" })).toBeNull();
  });
});
