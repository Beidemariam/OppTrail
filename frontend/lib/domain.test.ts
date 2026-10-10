import { describe, expect, it } from "vitest";

import {
  adjacentStage,
  applyOpportunityView,
  calendarRange,
  calendarWeeks,
  closingOn,
  columnsFromState,
  defaultOpportunityColumns,
  editableField,
  editableOpportunityFields,
  columnLabel,
  customColumn,
  customColumnKey,
  customFieldText,
  customFilterState,
  customFilters,
  activityByRep,
  activityWeeks,
  isLinked,
  linkTargetFromParams,
  matchesCustomFilters,
  searchResultHref,
  weekLabel,
  winRatePercent,
  type CustomField,
  emptyOpportunityViewState,
  emptyTimelineFilters,
  tasksDueOn,
  formatBytes,
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
  type Task,
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

function aTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 100,
    opportunity_id: 1,
    opportunity_name: "Northwind rollout",
    entry_id: null,
    entry_title: null,
    title: "Send updated pricing",
    description: "",
    assignees: [{ user_id: 1, name: "Alex" }],
    due_date: "2026-12-02",
    completed_at: null,
    completed_by: null,
    completed_by_name: null,
    created_by: 1,
    author_name: "Alex",
    created_at: "2026-11-01T09:00:00Z",
    updated_at: "2026-11-01T09:00:00Z",
    comments: [],
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

  it("reads a file size in the unit it lands in (milestone 4.3)", () => {
    // The API sends `byte_size` and never a formatted string, for the same
    // reason it sends a currency and an amount: the screen and the PDF
    // manifest format it differently.
    expect(formatBytes(0)).toBe("0 bytes");
    expect(formatBytes(512)).toBe("512 bytes");
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(2_411_724)).toBe("2.3 MB");
    // Powers of 1024 stop at MB, because the upload cap is 10 MiB -- a
    // gigabyte unit would be a unit nothing can reach.
    expect(formatBytes(10 * 1024 * 1024)).toBe("10.0 MB");
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
    // matches, and changing any filter stops it matching. Picked opposite the
    // default reading order (D-115 flipped `emptyTimelineFilters.order` to
    // "desc") so the third case - the raw defaults, no view applied - is
    // actually a state the view's own filter disagrees with.
    const view = aSavedView({ filters: { order: "asc" } });
    expect(
      matchesSavedView(
        view,
        { ...emptyTimelineFilters, order: "asc" },
        emptyTimelineFilters,
      ),
    ).toBe(true);
    expect(
      matchesSavedView(
        view,
        { ...emptyTimelineFilters, order: "asc", q: "acme" },
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

describe("the calendar's follow-up layer (milestone 3.0b, D-088)", () => {
  it("bounds the read to exactly the grid calendarWeeks draws", () => {
    // Same December 2026 grid as above: the first week opens on 30 November,
    // the last closes on 3 January, so the range must reach both neighbours.
    expect(calendarRange("2026-12")).toEqual({
      from: "2026-11-30",
      to: "2027-01-03",
    });
  });

  it("finds the tasks due on one day and ignores the rest", () => {
    // The calendar's second layer since milestone 4.2: tasks rather than an
    // entry's `follow_up_date`, which the migration moved into them.
    const tasks = [
      aTask({ id: 1, due_date: "2026-12-02" }),
      aTask({ id: 2, due_date: "2026-12-03" }),
      aTask({ id: 3, due_date: "2026-12-02" }),
    ];

    expect(tasksDueOn(tasks, "2026-12-02").map((item) => item.id)).toEqual([
      1, 3,
    ]);
    expect(tasksDueOn(tasks, "2026-12-25")).toEqual([]);
  });
});

describe("linking to one thing inside a timeline (milestone 6.0)", () => {
  const params = (query: string) => new URLSearchParams(query);

  it("reads the level a URL names", () => {
    expect(linkTargetFromParams(params("entry=7"))).toEqual({
      level: "entry",
      id: 7,
    });
    expect(linkTargetFromParams(params("note=12"))).toEqual({
      level: "note",
      id: 12,
    });
    expect(linkTargetFromParams(params("comment=4"))).toEqual({
      level: "comment",
      id: 4,
    });
  });

  it("takes the innermost level when a URL names several", () => {
    // A link may say which entry a comment is under without the entry
    // stealing the mark from the thing the reader actually followed.
    expect(linkTargetFromParams(params("entry=7&note=12&comment=4"))).toEqual({
      level: "comment",
      id: 4,
    });
    expect(linkTargetFromParams(params("entry=7&note=12"))).toEqual({
      level: "note",
      id: 12,
    });
  });

  it("treats an absent or unusable parameter as no target", () => {
    // A stale hand-edited URL should land the reader on the deal rather than
    // break, so every one of these is the same answer as no parameter at all.
    expect(linkTargetFromParams(params(""))).toBeNull();
    expect(linkTargetFromParams(params("entry=nonsense"))).toBeNull();
    expect(linkTargetFromParams(params("entry=0"))).toBeNull();
    expect(linkTargetFromParams(params("entry=-3"))).toBeNull();
    expect(linkTargetFromParams(params("timeline.order=asc"))).toBeNull();
  });

  it("sends each kind of search result to the level it matched", () => {
    const base = {
      opportunity_id: 3,
      opportunity_name: "Acme",
      note_id: null,
      title: null,
      snippet: { text: "", matches: [] },
      timestamp: "2026-01-01T00:00:00Z",
      author_id: 1,
      author_name: "Owner",
    };
    expect(
      searchResultHref({ ...base, kind: "entry", id: 7, entry_id: 7 }),
    ).toBe("/opportunities/3?entry=7");
    expect(
      searchResultHref({ ...base, kind: "note", id: 12, entry_id: 7 }),
    ).toBe("/opportunities/3?note=12");
    expect(
      searchResultHref({ ...base, kind: "comment", id: 4, entry_id: 7 }),
    ).toBe("/opportunities/3?comment=4");
    // An attachment has no level of its own: it is rendered on the entry it
    // hangs off, so it is addressed by that entry rather than by its own id
    // -- four kinds, three levels.
    expect(
      searchResultHref({ ...base, kind: "attachment", id: 99, entry_id: 7 }),
    ).toBe("/opportunities/3?entry=7");
  });

  it("matches a row only at its own level", () => {
    // The id spaces are independent, so note 7 and entry 7 both exist and a
    // link to one must not mark the other.
    const target = { level: "note", id: 7 } as const;
    expect(isLinked(target, "note", 7)).toBe(true);
    expect(isLinked(target, "entry", 7)).toBe(false);
    expect(isLinked(target, "note", 8)).toBe(false);
    expect(isLinked(null, "note", 7)).toBe(false);
    expect(isLinked(undefined, "note", 7)).toBe(false);
  });
});

describe("custom fields (milestone 6.1)", () => {
  const field = (overrides: Partial<CustomField> = {}): CustomField => ({
    id: 1,
    entity_type: "opportunity",
    key: "region",
    label: "Region",
    type: "text",
    options: [],
    required: false,
    position: 0,
    created_by: 1,
    created_at: "2026-09-01T09:00:00Z",
    updated_at: "2026-09-01T09:00:00Z",
    archived_at: null,
    ...overrides,
  });

  it("keeps a custom column in its own namespace", () => {
    // A field's key is chosen by a person, and nothing stops somebody
    // defining one called `stage`.
    expect(customColumn("stage")).toBe("custom:stage");
    expect(customColumnKey("custom:stage")).toBe("stage");
    expect(customColumnKey("stage")).toBeNull();
  });

  it("offers a custom column only while its field is live", () => {
    const fields = [field({ key: "region" })];
    expect(columnsFromState("stage,custom:region", fields)).toEqual([
      "stage",
      "custom:region",
    ]);
    // Archived, so the definition list no longer holds it: the column drops
    // out of a saved view and a bookmarked URL without either being edited.
    expect(columnsFromState("stage,custom:region", [])).toEqual(["stage"]);
    // And a column string that names nothing live falls back to the default
    // set rather than rendering a table with no columns.
    expect(columnsFromState("custom:region", [])).toEqual(
      defaultOpportunityColumns,
    );
  });

  it("reads each type as the text a cell shows", () => {
    expect(customFieldText(field(), "EMEA")).toBe("EMEA");
    expect(customFieldText(field({ type: "number" }), 42)).toBe("42");
    expect(customFieldText(field({ type: "checkbox" }), true)).toBe("Yes");
    expect(customFieldText(field({ type: "checkbox" }), false)).toBe("No");
    expect(
      customFieldText(field({ type: "multi_select" }), ["Core", "Addon"]),
    ).toBe("Core, Addon");
    expect(
      customFieldText(field({ type: "user" }), 7, new Map([[7, "Alex"]])),
    ).toBe("Alex");
    // A value of the wrong shape reads as empty rather than as
    // "[object Object]": a field can be archived and recreated with a
    // different type (ADR 0006's answer to a type change), which leaves older
    // rows holding the previous shape, and a table cell is not where a reader
    // should discover that.
    expect(customFieldText(field({ type: "number" }), "forty")).toBe("");
    expect(customFieldText(field({ type: "multi_select" }), "Core")).toBe("");
    expect(customFieldText(field(), null)).toBe("");
    expect(customFieldText(field(), undefined)).toBe("");
  });

  it("round-trips the filters through the flat string the URL holds", () => {
    const parsed = customFilters("region:EMEA,tier:Gold");
    expect([...parsed]).toEqual([
      ["region", "EMEA"],
      ["tier", "Gold"],
    ]);
    expect(customFilterState(parsed)).toBe("region:EMEA,tier:Gold");
  });

  it("ignores a filter whose field is gone, rather than matching nothing", () => {
    // The tolerance `pinnedIds` and `columnsFromState` already have: a stale
    // link should show a reader more than they expected, never an empty
    // screen they cannot explain.
    const fields = [field({ key: "region" })];
    expect([...customFilters("region:EMEA,gone:Yes", fields)]).toEqual([
      ["region", "EMEA"],
    ]);
    expect([...customFilters("region:,:EMEA,nonsense", fields)]).toEqual([]);
  });

  it("matches a value by type", () => {
    // A multi-select matches when the wanted option is among the chosen;
    // everything else matches on its text, like the keyword box.
    const filters = new Map([["products", "Core"]]);
    expect(matchesCustomFilters({ products: ["Core", "Addon"] }, filters)).toBe(
      true,
    );
    expect(matchesCustomFilters({ products: ["Addon"] }, filters)).toBe(false);
    expect(
      matchesCustomFilters(
        { region: "EMEA-North" },
        new Map([["region", "emea"]]),
      ),
    ).toBe(true);
    expect(
      matchesCustomFilters(
        { strategic: true },
        new Map([["strategic", "true"]]),
      ),
    ).toBe(true);
    expect(
      matchesCustomFilters(
        { strategic: false },
        new Map([["strategic", "true"]]),
      ),
    ).toBe(false);
    // A record with no value for a filtered field is filtered out, which is
    // what "show me the EMEA deals" means.
    expect(matchesCustomFilters({}, filters)).toBe(false);
  });

  it("filters the dashboard list by a custom value", () => {
    const fields = [field({ key: "region" })];
    const deals = [
      {
        ...anOpportunity({ id: 1, name: "Acme" }),
        custom_values: { region: "EMEA" },
      },
      {
        ...anOpportunity({ id: 2, name: "Globex" }),
        custom_values: { region: "APAC" },
      },
      { ...anOpportunity({ id: 3, name: "Initech" }), custom_values: {} },
    ];
    const shown = applyOpportunityView(
      deals,
      { ...emptyOpportunityViewState, custom: "region:EMEA" },
      fields,
    );
    expect(shown.map((deal) => deal.name)).toEqual(["Acme"]);
  });

  it("labels a column from its field, and a cell from its value", () => {
    const fields = [field({ key: "region", label: "Sales region" })];
    expect(columnLabel("custom:region", fields)).toBe("Sales region");
    expect(columnLabel("stage", fields)).toBe("Stage");
    // A column whose field is gone still has to render something.
    expect(columnLabel("custom:region", [])).toBe("region");

    const deal = {
      ...anOpportunity({ id: 1, name: "Acme" }),
      custom_values: { region: "EMEA" },
    };
    expect(opportunityCell(deal, "custom:region", fields)).toBe("EMEA");
    expect(opportunityCell(deal, "custom:region", [])).toBe("");
  });
});

describe("the dashboard's reading helpers (milestone 6.2)", () => {
  it("keeps the absence of a win rate as an absence", () => {
    // 0% is a different claim from "nothing closed": it says they lost
    // everything.
    expect(winRatePercent(null)).toBeNull();
    expect(winRatePercent(0)).toBe("0%");
    expect(winRatePercent(0.755)).toBe("76%");
    expect(winRatePercent(1)).toBe("100%");
  });

  it("turns a flat activity series into one row per person", () => {
    const series = [
      { author_id: 2, author_name: "Blair", week: "2026-39", items: 3 },
      { author_id: 1, author_name: "Alex", week: "2026-38", items: 6 },
      { author_id: 1, author_name: "Alex", week: "2026-39", items: 9 },
    ];
    const reps = activityByRep(series);
    // Alphabetical, so the rows do not move when the counts change.
    expect(reps.map((rep) => rep.authorName)).toEqual(["Alex", "Blair"]);
    expect([...reps[0].weeks]).toEqual([
      ["2026-38", 6],
      ["2026-39", 9],
    ]);
    // Every week present anywhere, oldest first -- the shared x axis.
    expect(activityWeeks(series)).toEqual(["2026-38", "2026-39"]);
  });

  it("reads a stored week without inventing a date for it", () => {
    // `%Y-%W` is what SQLite can compute cheaply over a fixed-width
    // timestamp. Converting it to a date would mean adopting a first-day-of
    // -week convention this app has no reason to have.
    expect(weekLabel("2026-40")).toBe("2026-W40");
    expect(weekLabel("nonsense")).toBe("nonsense");
  });
});
