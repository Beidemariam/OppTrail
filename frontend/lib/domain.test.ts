import { describe, expect, it } from "vitest";

import {
  adjacentStage,
  applyOpportunityView,
  emptyOpportunityViewState,
  emptyTimelineFilters,
  formatMoney,
  matchesSavedView,
  savedViewLabel,
  savedViewVisibility,
  viewOrder,
  type Opportunity,
  type SavedView,
} from "./domain";

function aSavedView(overrides: Partial<SavedView> = {}): SavedView {
  return {
    id: 1,
    created_by: 1,
    creator_name: "Alex Morgan",
    name: "Newest first",
    entity: "timeline",
    filters: {},
    sort: {},
    group_by: null,
    is_shared: false,
    is_default: false,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}

function anOpportunity(overrides: Partial<Opportunity> = {}): Opportunity {
  return {
    id: 1,
    name: "Northwind rollout",
    account_name: "Northwind",
    value: "100",
    currency: "USD",
    stage: "Negotiation",
    owner_id: 1,
    owner_name: "Alex",
    expected_close_date: "2026-12-01",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    stalled: false,
    current_user_role: "owner",
    ...overrides,
  };
}

describe("applyOpportunityView", () => {
  it("defaults to last activity, most recent first", () => {
    const opportunities = [
      anOpportunity({ id: 1, updated_at: "2026-09-01T00:00:00Z" }),
      anOpportunity({ id: 2, updated_at: "2026-09-05T00:00:00Z" }),
    ];
    expect(
      applyOpportunityView(opportunities, emptyOpportunityViewState).map(
        (item) => item.id,
      ),
    ).toEqual([2, 1]);
  });

  it("filters by stage", () => {
    const opportunities = [
      anOpportunity({ id: 1, stage: "Negotiation" }),
      anOpportunity({ id: 2, stage: "Proposal" }),
    ];
    const result = applyOpportunityView(opportunities, {
      ...emptyOpportunityViewState,
      stage: "Proposal",
    });
    expect(result.map((item) => item.id)).toEqual([2]);
  });

  it("filters by stalled status", () => {
    const opportunities = [
      anOpportunity({ id: 1, stalled: true }),
      anOpportunity({ id: 2, stalled: false }),
    ];
    expect(
      applyOpportunityView(opportunities, {
        ...emptyOpportunityViewState,
        stalled: "true",
      }).map((item) => item.id),
    ).toEqual([1]);
    expect(
      applyOpportunityView(opportunities, {
        ...emptyOpportunityViewState,
        stalled: "false",
      }).map((item) => item.id),
    ).toEqual([2]);
  });

  it("filters by a keyword across name, account and owner", () => {
    const opportunities = [
      anOpportunity({ id: 1, name: "Northwind rollout" }),
      anOpportunity({ id: 2, name: "Globex renewal", account_name: "Globex" }),
    ];
    expect(
      applyOpportunityView(opportunities, {
        ...emptyOpportunityViewState,
        q: "globex",
      }).map((item) => item.id),
    ).toEqual([2]);
  });

  it("sorts by value in the chosen direction", () => {
    const opportunities = [
      anOpportunity({ id: 1, value: "100" }),
      anOpportunity({ id: 2, value: "300" }),
      anOpportunity({ id: 3, value: "200" }),
    ];
    expect(
      applyOpportunityView(opportunities, {
        ...emptyOpportunityViewState,
        sortField: "value",
        sortDirection: "asc",
      }).map((item) => item.id),
    ).toEqual([1, 3, 2]);
    expect(
      applyOpportunityView(opportunities, {
        ...emptyOpportunityViewState,
        sortField: "value",
        sortDirection: "desc",
      }).map((item) => item.id),
    ).toEqual([2, 3, 1]);
  });

  it("sorts by name", () => {
    const opportunities = [
      anOpportunity({ id: 1, name: "Zeta" }),
      anOpportunity({ id: 2, name: "Alpha" }),
    ];
    expect(
      applyOpportunityView(opportunities, {
        ...emptyOpportunityViewState,
        sortField: "name",
        sortDirection: "asc",
      }).map((item) => item.id),
    ).toEqual([2, 1]);
  });

  it("sorts by expected close date, treating a missing date as earliest", () => {
    const opportunities = [
      anOpportunity({ id: 1, expected_close_date: "2026-12-01" }),
      anOpportunity({ id: 2, expected_close_date: null }),
    ];
    expect(
      applyOpportunityView(opportunities, {
        ...emptyOpportunityViewState,
        sortField: "expected_close_date",
        sortDirection: "asc",
      }).map((item) => item.id),
    ).toEqual([2, 1]);
  });
});

describe("the shared formatting and ordering helpers (milestone 2.7)", () => {
  it("groups thousands and keeps cents only when there are any", () => {
    expect(formatMoney("USD", "185000.00")).toBe("USD 185,000");
    expect(formatMoney("EUR", "1234.5")).toBe("EUR 1,234.5");
    expect(formatMoney("GBP", 0)).toBe("GBP 0");
  });

  it("reads the list in sort order and the board in stage order", () => {
    const opportunities = [
      anOpportunity({ id: 1, stage: "Negotiation" }),
      anOpportunity({ id: 2, stage: "Prospecting" }),
    ];

    expect(viewOrder(opportunities, "list").map((item) => item.id)).toEqual([
      1, 2,
    ]);
    // Prospecting is the first column, so the board reads it first.
    expect(viewOrder(opportunities, "board").map((item) => item.id)).toEqual([
      2, 1,
    ]);
  });

  it("stops at both ends of the fixed stage list", () => {
    expect(adjacentStage("Proposal", 1)).toBe("Negotiation");
    expect(adjacentStage("Proposal", -1)).toBe("Needs Analysis");
    expect(adjacentStage("Prospecting", -1)).toBeNull();
    expect(adjacentStage("Closed Lost", 1)).toBeNull();
  });
});

describe("what a saved view is, said in words (milestone 2.13)", () => {
  it("reads one flag as the three facts it actually carries", () => {
    // D-076: `is_shared` is one boolean, but "mine and private", "mine and
    // everyone's" and "someone else's" are three different things to be told.
    expect(savedViewVisibility(aSavedView(), 1)).toBe("private");
    expect(savedViewVisibility(aSavedView({ is_shared: true }), 1)).toBe(
      "shared with everyone",
    );
    expect(savedViewVisibility(aSavedView({ is_shared: true }), 2)).toBe(
      "shared by Alex Morgan",
    );
  });

  it("names a view with its default marker and its visibility", () => {
    expect(savedViewLabel(aSavedView({ is_default: true }), 1)).toBe(
      "Newest first (default) - private",
    );
    expect(savedViewLabel(aSavedView({ is_shared: true }), 2)).toBe(
      "Newest first - shared by Alex Morgan",
    );
  });

  it("recognises the view the filters on screen amount to", () => {
    // Nothing records which view is applied - applying one only writes its
    // filters into the URL - so the applied view is the one the state
    // matches, and changing any filter stops it matching.
    const view = aSavedView({ filters: { order: "desc" } });
    expect(
      matchesSavedView(
        view,
        { ...emptyTimelineFilters, order: "desc" },
        emptyTimelineFilters,
      ),
    ).toBe(true);
    expect(
      matchesSavedView(
        view,
        { ...emptyTimelineFilters, order: "desc", q: "acme" },
        emptyTimelineFilters,
      ),
    ).toBe(false);
    expect(
      matchesSavedView(view, emptyTimelineFilters, emptyTimelineFilters),
    ).toBe(false);
  });
});
