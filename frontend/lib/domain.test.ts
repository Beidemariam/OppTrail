import { describe, expect, it } from "vitest";

import {
  adjacentStage,
  applyOpportunityView,
  calendarWeeks,
  closingOn,
  columnsFromState,
  defaultOpportunityColumns,
  editableField,
  editableOpportunityFields,
  emptyOpportunityViewState,
  emptyTimelineFilters,
  formatMoney,
  matchesSavedView,
  monthLabel,
  monthOrder,
  opportunityCell,
  resolveMonth,
  savedViewLabel,
  savedViewVisibility,
  shiftMonth,
  viewOrder,
  withoutCloseDate,
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

  it("filters to a pinned selection, and ignores what is not one", () => {
    const opportunities = [
      anOpportunity({ id: 1 }),
      anOpportunity({ id: 2 }),
      anOpportunity({ id: 3 }),
    ];
    // A filter, not an ordering: the pinned rows are still drawn in the
    // view's own sort order rather than in the order they were pinned.
    expect(
      applyOpportunityView(opportunities, {
        ...emptyOpportunityViewState,
        ids: "3,1",
      }).map((item) => item.id),
    ).toEqual([1, 3]);

    // A stale or hand-edited link reads as the ids it does carry, the way a
    // stale column list still draws a table.
    expect(
      applyOpportunityView(opportunities, {
        ...emptyOpportunityViewState,
        ids: "2,nonsense",
      }).map((item) => item.id),
    ).toEqual([2]);

    // Empty pins nothing, which is not the same as pinning an empty set.
    expect(
      applyOpportunityView(opportunities, emptyOpportunityViewState),
    ).toHaveLength(3);
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

    expect(
      viewOrder(opportunities, "list", "2026-12").map((item) => item.id),
    ).toEqual([1, 2]);
    // The table is the list's data in the list's order; only the layout
    // differs.
    expect(
      viewOrder(opportunities, "table", "2026-12").map((item) => item.id),
    ).toEqual([1, 2]);
    // Prospecting is the first column, so the board reads it first.
    expect(
      viewOrder(opportunities, "board", "2026-12").map((item) => item.id),
    ).toEqual([2, 1]);
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

describe("sorting by any column the table can show (milestone 2.8)", () => {
  const deals = [
    anOpportunity({ id: 1, name: "Beta", account_name: "Zenith" }),
    anOpportunity({ id: 2, name: "Alpha", account_name: "Acme" }),
  ];

  function sortedIds(
    field: (typeof emptyOpportunityViewState)["sortField"],
    direction: "asc" | "desc" = "asc",
  ) {
    return applyOpportunityView(deals, {
      ...emptyOpportunityViewState,
      sortField: field,
      sortDirection: direction,
    }).map((item) => item.id);
  }

  it("orders by every text column the table offers", () => {
    expect(sortedIds("name")).toEqual([2, 1]);
    expect(sortedIds("account_name")).toEqual([2, 1]);
    expect(sortedIds("name", "desc")).toEqual([1, 2]);
  });

  it("orders stages down the pipeline, not down the alphabet", () => {
    // The whole point of sorting a stage column: "Closed Won" after
    // "Prospecting", which alphabetical order gets backwards.
    const stagesOut = applyOpportunityView(
      [
        anOpportunity({ id: 1, stage: "Prospecting" }),
        anOpportunity({ id: 2, stage: "Closed Won" }),
        anOpportunity({ id: 3, stage: "Needs Analysis" }),
      ],
      {
        ...emptyOpportunityViewState,
        sortField: "stage",
        sortDirection: "asc",
      },
    );
    expect(stagesOut.map((item) => item.stage)).toEqual([
      "Prospecting",
      "Needs Analysis",
      "Closed Won",
    ]);
  });

  it("sorts undated deals together rather than scattering them", () => {
    const out = applyOpportunityView(
      [
        anOpportunity({ id: 1, expected_close_date: "2026-12-01" }),
        anOpportunity({ id: 2, expected_close_date: null }),
        anOpportunity({ id: 3, expected_close_date: "2026-11-01" }),
      ],
      {
        ...emptyOpportunityViewState,
        sortField: "expected_close_date",
        sortDirection: "asc",
      },
    );
    expect(out.map((item) => item.id)).toEqual([2, 3, 1]);
  });
});

describe("the table's columns (milestone 2.8)", () => {
  it("falls back to the default set for a link that names no real column", () => {
    expect(columnsFromState("")).toEqual([...defaultOpportunityColumns]);
    expect(columnsFromState("nonsense,also_nonsense")).toEqual([
      ...defaultOpportunityColumns,
    ]);
    // A stale link that names one real column and one that no longer exists
    // still draws the real one.
    expect(columnsFromState("value,retired_column")).toEqual(["value"]);
  });

  it("formats a cell the way that column is read", () => {
    const opportunity = anOpportunity({
      value: "185000",
      currency: "USD",
      expected_close_date: null,
      updated_at: "2026-09-02T14:31:00Z",
    });
    expect(opportunityCell(opportunity, "value")).toBe("USD 185,000");
    expect(opportunityCell(opportunity, "expected_close_date")).toBe("Not set");
    // Date alone: nobody scans a column of timestamps for the minute.
    expect(opportunityCell(opportunity, "updated_at")).toBe("2026-09-02");
    expect(opportunityCell(opportunity, "account_name")).toBe("Northwind");
  });
});

describe("which opportunity fields are edited in place (milestone 2.11)", () => {
  const opportunity = anOpportunity({
    name: "Northwind rollout",
    account_name: "Northwind",
    value: "185000",
    stage: "Negotiation",
    expected_close_date: "2026-12-01",
  });

  it("reads each field as its editor's own value, not as the cell reads it", () => {
    // The cell shows "USD 185,000"; the number input has to open on 185000.
    expect(editableOpportunityFields.value.read(opportunity)).toBe("185000");
    expect(opportunityCell(opportunity, "value")).toBe("USD 185,000");
    expect(editableOpportunityFields.name.read(opportunity)).toBe(
      "Northwind rollout",
    );
    expect(editableOpportunityFields.account_name.read(opportunity)).toBe(
      "Northwind",
    );
    expect(editableOpportunityFields.stage.read(opportunity)).toBe(
      "Negotiation",
    );
    expect(
      editableOpportunityFields.expected_close_date.read(opportunity),
    ).toBe("2026-12-01");
    // An empty date, not the "Not set" the cell says.
    expect(
      editableOpportunityFields.expected_close_date.read(
        anOpportunity({ expected_close_date: null }),
      ),
    ).toBe("");
  });

  it("sends one key per edited field, and null to clear a close date", () => {
    expect(editableOpportunityFields.name.patch("Renamed")).toEqual({
      name: "Renamed",
    });
    expect(editableOpportunityFields.account_name.patch("Globex")).toEqual({
      account_name: "Globex",
    });
    expect(editableOpportunityFields.value.patch("210000")).toEqual({
      value: "210000",
    });
    expect(editableOpportunityFields.stage.patch("Closed Won")).toEqual({
      stage: "Closed Won",
    });
    expect(
      editableOpportunityFields.expected_close_date.patch("2027-01-15"),
    ).toEqual({ expected_close_date: "2027-01-15" });
    expect(editableOpportunityFields.expected_close_date.patch("")).toEqual({
      expected_close_date: null,
    });
  });

  it("knows which table columns are fields and which are only read", () => {
    expect(editableField("account_name")).toBe(
      editableOpportunityFields.account_name,
    );
    expect(editableField("value")).toBe(editableOpportunityFields.value);
    // Derived or owned elsewhere: none of these is something a reader types
    // over in a cell.
    expect(editableField("owner_name")).toBeNull();
    expect(editableField("updated_at")).toBeNull();
    expect(editableField("created_at")).toBeNull();
  });
});

describe("the calendar's month (milestone 2.8)", () => {
  it("draws whole weeks from Monday, including the neighbours' days", () => {
    // December 2026 starts on a Tuesday and ends on a Thursday, so the first
    // week opens on 30 November and the last closes on 3 January.
    const weeks = calendarWeeks("2026-12");
    expect(weeks[0][0]).toBe("2026-11-30");
    expect(weeks[0][1]).toBe("2026-12-01");
    expect(weeks.at(-1)!.at(-1)).toBe("2027-01-03");
    expect(weeks.every((week) => week.length === 7)).toBe(true);
  });

  it("draws a month that starts on a Monday without a leading week", () => {
    // June 2026 starts on a Monday: the first cell is the first of the month.
    expect(calendarWeeks("2026-06")[0][0]).toBe("2026-06-01");
  });

  it("steps across a year boundary in both directions", () => {
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(monthLabel("2026-12")).toBe("December 2026");
  });

  it("falls back to the reader's own month when the URL names none", () => {
    expect(resolveMonth("2026-03")).toBe("2026-03");
    // An empty or malformed month resolves to today's, not to nothing - a
    // link with no month in it opens where the reader is.
    expect(resolveMonth("", new Date("2026-03-15T00:00:00Z"))).toBe("2026-03");
    expect(resolveMonth("not-a-month", new Date("2026-03-15T00:00:00Z"))).toBe(
      "2026-03",
    );
    expect(resolveMonth("")).toBe(new Date().toISOString().slice(0, 7));
  });

  it("reads the drawn month by date, then the deals it cannot place", () => {
    const deals = [
      anOpportunity({ id: 1, expected_close_date: "2026-12-20" }),
      anOpportunity({ id: 2, expected_close_date: null }),
      anOpportunity({ id: 3, expected_close_date: "2026-12-02" }),
      // Another month entirely: not drawn, so the cursor must not visit it.
      anOpportunity({ id: 4, expected_close_date: "2026-08-04" }),
    ];

    expect(closingOn(deals, "2026-12-02").map((item) => item.id)).toEqual([3]);
    expect(withoutCloseDate(deals).map((item) => item.id)).toEqual([2]);
    expect(monthOrder(deals, "2026-12").map((item) => item.id)).toEqual([
      3, 1, 2,
    ]);
    expect(
      viewOrder(deals, "calendar", "2026-12").map((item) => item.id),
    ).toEqual([3, 1, 2]);
  });
});
