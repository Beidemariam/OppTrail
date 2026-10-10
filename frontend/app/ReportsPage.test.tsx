import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { aDashboard, emptyDashboard } from "./test-api";
import { renderApp } from "./test-app";
import { ALEX } from "./test-api";

/**
 * The reports screen (milestone 6.2, `docs/FEATURES.md` §10).
 *
 * The arithmetic is `backend/tests/test_dashboard.py`'s; what matters here is
 * how a number is *drawn*, and especially the two that are deliberately
 * absent — §10 is explicit that an unmeasured average must be labelled rather
 * than "silently shown as zero", and a win rate with nothing closed is not 0%.
 */
beforeEach(() => {
  document.cookie = "opptrail_csrf=test-token";
});

afterEach(() => {
  document.cookie = "opptrail_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

async function openReports(dashboard = aDashboard()) {
  const api = renderApp({ user: ALEX, dashboard }, "/reports");
  await screen.findByRole("heading", { name: "Reports" });
  return api;
}

describe("the six aggregations on screen", () => {
  it("draws the pipeline with a row per open stage", async () => {
    await openReports();
    const pipeline = await screen.findByRole("region", {
      name: "Pipeline by stage",
    });

    // Every open stage, including the empty one: a stage missing from a chart
    // reads as a rendering fault rather than as an empty column.
    for (const stage of [
      "Prospecting",
      "Qualification",
      "Needs Analysis",
      "Proposal",
      "Negotiation",
    ]) {
      expect(within(pipeline).getByText(stage)).toBeInTheDocument();
    }
    expect(within(pipeline).getByText("7 open")).toBeInTheDocument();
    expect(within(pipeline).getByText(/USD 120,000/)).toBeInTheDocument();
    // Closed stages are not pipeline.
    expect(within(pipeline).queryByText("Closed Won")).not.toBeInTheDocument();
  });

  it("shows a win rate, and says so when there is none", async () => {
    await openReports();
    expect(await screen.findByText("75%")).toBeInTheDocument();
    expect(screen.getByText(/3 won, 1 lost/)).toBeInTheDocument();

    document.body.innerHTML = "";
    await openReports(emptyDashboard());
    // Not "0%": a team that has closed nothing has no win rate, and 0% says
    // they lost everything.
    expect(
      await screen.findByText(/Nothing closed yet in this period/),
    ).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("labels an unmeasured stage instead of drawing it as zero", async () => {
    // §10's own caveat, and the reason the API carries `earliest_change`.
    await openReports();
    const card = await screen.findByRole("region", {
      name: "Average time in stage",
    });

    expect(within(card).getByText("12.5 days")).toBeInTheDocument();
    expect(within(card).getByText("8 days")).toBeInTheDocument();
    expect(within(card).getAllByText("Not yet measured").length).toBe(5);
    expect(
      within(card).getByText(/Measured from stage changes recorded since/),
    ).toBeInTheDocument();
    expect(within(card).queryByText("0 days")).not.toBeInTheDocument();
  });

  it("says nothing has been measured when no stage has ever changed", async () => {
    await openReports(emptyDashboard());
    const card = await screen.findByRole("region", {
      name: "Average time in stage",
    });
    expect(
      within(card).getByText(/No stage change has been recorded yet/),
    ).toBeInTheDocument();
  });

  it("lists what has gone quiet, each linking to its deal", async () => {
    await openReports();
    const card = await screen.findByRole("region", { name: "Gone quiet" });

    expect(
      within(card).getByRole("link", { name: "Northwind rollout" }),
    ).toHaveAttribute("href", "/opportunities/10");

    document.body.innerHTML = "";
    await openReports(emptyDashboard());
    expect(
      await screen.findByText(/Nothing has been silent for 14 days/),
    ).toBeInTheDocument();
  });

  it("shows the forecast with the probabilities it used", async () => {
    // A forecast whose assumptions nobody can see is a number nobody should
    // act on, which is why the API returns the ramp beside the total.
    await openReports();
    const card = await screen.findByRole("region", { name: "Forecast" });

    expect(within(card).getByText(/USD 145,000/)).toBeInTheDocument();
    expect(within(card).getByText("60%")).toBeInTheDocument();
    expect(within(card).getByText("80%")).toBeInTheDocument();
  });

  it("draws one series per person for activity", async () => {
    await openReports();
    const card = await screen.findByRole("region", {
      name: "Activity per person",
    });

    expect(within(card).getByText("Alex")).toBeInTheDocument();
    expect(within(card).getByText("Blair")).toBeInTheDocument();
    // Alex's two weeks total 15; Blair's single week is 3.
    expect(within(card).getByText("15")).toBeInTheDocument();
    expect(within(card).getByText("3")).toBeInTheDocument();
  });

  it("drives both windowed metrics from the period, and says which", async () => {
    // The human's finding at the 6.2 review: the control drove win/loss alone
    // while reading as though it drove everything. Four of the six have no
    // period at all, so the fix is both halves -- the window applies to the
    // two that are windowed, and every card states the one it used.
    const api = await openReports();

    expect(screen.getByText(/The period applies to/)).toBeInTheDocument();
    expect(
      within(
        await screen.findByRole("region", { name: "Activity per person" }),
      ).getByText("last 52 weeks"),
    ).toBeInTheDocument();

    await userEvent.selectOptions(
      screen.getByLabelText("Win and loss period"),
      "30",
    );

    // Thirty days is four weeks, and the activity card now says so.
    await waitFor(() =>
      expect(
        api.calls.some(
          (call) =>
            call.path.startsWith("/api/v2/dashboard") &&
            call.path.includes("weeks=4"),
        ),
      ).toBe(true),
    );
    expect(
      within(
        screen.getByRole("region", { name: "Activity per person" }),
      ).getByText("last 4 weeks"),
    ).toBeInTheDocument();
    // And the win/loss card names the period it covers.
    expect(
      within(screen.getByRole("region", { name: "Win and loss" })).getByText(
        "last 30 days",
      ),
    ).toBeInTheDocument();
  });

  it("asks the API for the period the reader chose", async () => {
    const api = await openReports();
    await userEvent.selectOptions(
      screen.getByLabelText("Win and loss period"),
      "30",
    );

    // A different period is a different question, so it is a different query
    // key rather than a refetch of the same one.
    expect(
      api.calls.some(
        (call) =>
          call.path.startsWith("/api/v2/dashboard") &&
          call.path.includes("since="),
      ),
    ).toBe(true);
  });

  it("invites a sign-in rather than asking for numbers", async () => {
    renderApp({}, "/reports");
    expect(
      await screen.findByRole("link", { name: "Sign in" }),
    ).toBeInTheDocument();
  });
});

describe("a figure says what currency it is in", () => {
  it("labels a total with the currency the API summed", async () => {
    await openReports(aDashboard({ currency: "EUR" }));
    expect(await screen.findByText(/EUR 145,000/)).toBeInTheDocument();
  });

  it("says so rather than stamping a symbol on a mixed sum", async () => {
    // The API answers `null` when the deals it summed carry more than one
    // currency, because then the total is a number and not an amount. A
    // screen that printed "USD 145,000" anyway would be telling a lie the API
    // went out of its way to avoid.
    await openReports(aDashboard({ currency: null }));
    expect(
      await screen.findByText(/145,000 \(mixed currencies\)/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/USD 145,000/)).not.toBeInTheDocument();
  });
});
