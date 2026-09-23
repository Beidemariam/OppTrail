/**
 * The vocabulary the whole client shares: the fixed stage list, the entry
 * types, and short names for the generated API schemas.
 *
 * These were declared inside `app/Home.tsx` until milestone 2.1 split that
 * file into routed views. They live here now because several views need the
 * same names, and because the stage list is a fixed, non-renamable list
 * (`AGENTS.md` invariant 6) that should have exactly one definition.
 */

import type { components } from "./api-types";

export const stages = [
  "Prospecting",
  "Qualification",
  "Needs Analysis",
  "Proposal",
  "Negotiation",
  "Closed Won",
  "Closed Lost",
] as const;

/**
 * A money figure as the views show it: grouped thousands, cents only when
 * there are any, and the currency code in front — this app stores an amount
 * and a currency and does no conversion, so the code is part of the number
 * rather than decoration.
 */
export function formatMoney(currency: string, value: string | number): string {
  return `${currency} ${Number(value).toLocaleString("en-US", {
    maximumFractionDigits: 2,
  })}`;
}

/** The fixed stage list as a type: the generated `Opportunity["stage"]`
 * union, named once so every stage-carrying signature reads the same. */
export type Stage = (typeof stages)[number];

export const entryTypes = [
  { value: "call", label: "Call" },
  { value: "email", label: "Email" },
  { value: "meeting", label: "Meeting" },
  { value: "demo", label: "Demo" },
  { value: "proposal", label: "Proposal" },
  { value: "contract", label: "Contract" },
  { value: "stage_change", label: "Stage Change" },
  { value: "other", label: "Other" },
  { value: "site_visit", label: "Site Visit" },
  { value: "objection", label: "Objection" },
  { value: "competitor_intel", label: "Competitor Intel" },
] as const;

export type EntryType = (typeof entryTypes)[number]["value"];

export function entryTypeLabel(type: EntryType): string {
  return (
    entryTypes.find((candidate) => candidate.value === type)?.label ?? type
  );
}

export const notificationTypeOptions = [
  { value: "mention", label: "Mentions" },
  { value: "comment", label: "Comments" },
  { value: "shared_activity", label: "Activity" },
  { value: "share_added", label: "Sharing added" },
  { value: "share_role_changed", label: "Role changed" },
  { value: "share_removed", label: "Sharing removed" },
] as const;

export type User = components["schemas"]["UserPublic"];
export type Opportunity = components["schemas"]["OpportunityPublic"];
export type OpportunityShare = components["schemas"]["SharePublic"];
export type ShareRole = components["schemas"]["ShareCreate"]["role"];
export type AuditLogEntry = components["schemas"]["AuditLogEntryPublic"];
export type AppNotification = components["schemas"]["NotificationPublic"];
export type NotificationType = AppNotification["type"];
export type TimelineEntry = components["schemas"]["TimelineEntryPublic"];
export type TimelineNote = components["schemas"]["NotePublic"];
export type BulkActionResultItem =
  components["schemas"]["BulkActionResultItem"];

/* --- Edit history (milestone 2.10) ---------------------------------------
 *
 * Three histories over three different shapes, read through one screen
 * (`app/HistoryDialog.tsx`). What differs between them is only which fields a
 * version snapshots and how each one reads, so that is all that is declared
 * per kind; the comparison below is written once.
 */

export type OpportunityVersion =
  components["schemas"]["OpportunityVersionPublic"];
export type TimelineEntryVersion =
  components["schemas"]["TimelineEntryVersionPublic"];
export type NoteVersion = components["schemas"]["NoteVersionPublic"];

/**
 * One versioned field: which column it is, what to call it, and how to read it
 * off a version.
 *
 * `field` is the column name `backend/app/versioning.py` snapshots under. The
 * history screen never needs it — it reads values — but the activity log is
 * given only the names of the columns an edit moved (milestone 3.0), and
 * naming them a second time there is how the two screens would come to call
 * the same field different things.
 */
export interface VersionField<VersionT> {
  field: string;
  label: string;
  read: (version: VersionT) => string;
}

export const opportunityVersionFields: VersionField<OpportunityVersion>[] = [
  { field: "name", label: "Name", read: (version) => version.name },
  {
    field: "account_name",
    label: "Account",
    read: (version) => version.account_name,
  },
  {
    field: "value",
    label: "Value",
    read: (version) => formatMoney(version.currency, version.value),
  },
  { field: "stage", label: "Stage", read: (version) => version.stage },
  {
    field: "expected_close_date",
    label: "Close date",
    read: (version) => version.expected_close_date ?? "Not set",
  },
];

export const timelineEntryVersionFields: VersionField<TimelineEntryVersion>[] =
  [
    {
      field: "type",
      label: "Type",
      read: (version) => entryTypeLabel(version.type),
    },
    { field: "title", label: "Title", read: (version) => version.title },
    {
      field: "body",
      label: "Details",
      read: (version) => version.body || "No details",
    },
    {
      field: "event_timestamp",
      label: "Event time",
      read: (version) => version.event_timestamp,
    },
    {
      field: "follow_up_date",
      label: "Follow up",
      read: (version) => version.follow_up_date ?? "Not set",
    },
  ];

export const noteVersionFields: VersionField<NoteVersion>[] = [
  { field: "body", label: "Body", read: (version) => version.body },
];

/**
 * One line of a version block: a field, what it says now, and what it said
 * before if this version is what changed it.
 */
export interface VersionChange {
  label: string;
  before: string | null;
  after: string;
}

/**
 * What one version is, read against the one before it.
 *
 * The first version has nothing to be read against, so it is the whole state —
 * that is the point of recording it at creation. Every later version shows
 * only the fields it moved, because a history answers "what changed" and the
 * unchanged ones are already on the line above. A version that changed nothing
 * (a save of an untouched form) is an empty list, which the dialog says in
 * words rather than drawing as a gap.
 */
export function versionChanges<VersionT>(
  fields: VersionField<VersionT>[],
  version: VersionT,
  previous: VersionT | undefined,
): VersionChange[] {
  if (!previous) {
    return fields.map((field) => ({
      label: field.label,
      before: null,
      after: field.read(version),
    }));
  }
  return fields
    .map((field) => ({
      label: field.label,
      before: field.read(previous),
      after: field.read(version),
    }))
    .filter((change) => change.before !== change.after);
}

/** What the signed-in user is allowed to do inside one opportunity. */
export interface Access {
  canWriteTimeline: boolean;
  canManage: boolean;
  /** Edit and delete resolve through one rule (`lib/permissions.ts`). */
  canChangeItem: (authorId: number | null) => boolean;
}

/**
 * The timeline query parameters the filter bar sends, plus the reading order
 * (D-051). Every field is a plain string because this shape is also what
 * lives in the URL and in a saved view's `filters`
 * (`lib/viewState.ts`) — one shape, not a conversion between two.
 */
export type TimelineFilters = {
  q: string;
  type: string;
  from: string;
  to: string;
  author_id: string;
  order: "asc" | "desc";
};

export const emptyTimelineFilters: TimelineFilters = {
  q: "",
  type: "",
  from: "",
  to: "",
  author_id: "",
  order: "asc",
};

/**
 * The opportunity views' shared filter/sort model (milestone 2.2),
 * URL-serialized the same way as `TimelineFilters`. `view` is which renderer
 * draws the result (2.7): board and list read the same filtered, sorted list
 * and differ only in how they lay it out, which is what makes switching them
 * a URL change rather than a second query. No `groupBy` field yet — grouping
 * by stage is what makes the board the board — so a saved view records
 * `group_by: "stage"` as a constant (`SavedViewsMenu.tsx`), and the column
 * exists in the schema before a view gives it a reason to vary.
 */
export type OpportunityViewState = {
  q: string;
  stage: string;
  stalled: "" | "true" | "false";
  sortField: OpportunitySortField;
  sortDirection: "asc" | "desc";
  view: OpportunityView;
  /** The table's visible columns, comma-separated in the order they are
   * drawn (milestone 2.8). A string because this shape is also the URL and a
   * saved view's `filters`, both of which are flat string maps. */
  columns: string;
  /** Which month the calendar is showing, `YYYY-MM`. Empty means the month
   * the reader is in, resolved at render (`resolveMonth`) rather than stored,
   * so a link with no month in it always opens on today. */
  month: string;
  /**
   * A curated selection, comma-separated (milestone 3.0a, **D-106**). This is
   * what the action bar's "add to view" writes: a saved view is a filter set
   * rather than a folder, so pinning deals into one is a filter like any
   * other and needs no membership table. Empty means no selection is pinned,
   * which is every view that does not use the feature.
   */
  ids: string;
};

/** The four renderers over one filtered list: board and list from milestone
 * 2.7, table and calendar from 2.8. They are renderers and not queries — the
 * dashboard filters and sorts once and hands the result to whichever one the
 * URL asked for. */
export type OpportunityView = "board" | "list" | "table" | "calendar";

export const opportunityViews = [
  { value: "board", label: "Board" },
  { value: "list", label: "List" },
  { value: "table", label: "Table" },
  { value: "calendar", label: "Calendar" },
] as const;

/**
 * What the opportunity views can be sorted by: every column the table can
 * show, plus the name. Declared here rather than in the filter bar because
 * the table's own column headers sort through the same state (milestone
 * 2.8) — a header click and the sort dropdown are one setting, not two.
 */
export const sortFields = [
  { value: "updated_at", label: "Last activity" },
  { value: "name", label: "Name" },
  { value: "account_name", label: "Account" },
  { value: "stage", label: "Stage" },
  { value: "value", label: "Value" },
  { value: "expected_close_date", label: "Close date" },
  { value: "owner_name", label: "Owner" },
  { value: "created_at", label: "Created" },
] as const;

export type OpportunitySortField = (typeof sortFields)[number]["value"];

/**
 * The columns the table can show, in the order the picker offers them
 * (milestone 2.8). The opportunity's own name is not here: it is the row's
 * identity and the link to its timeline, so it is always drawn and cannot be
 * turned off.
 */
export const opportunityColumns = [
  { key: "account_name", label: "Account" },
  { key: "stage", label: "Stage" },
  { key: "value", label: "Value" },
  { key: "expected_close_date", label: "Close date" },
  { key: "owner_name", label: "Owner" },
  { key: "updated_at", label: "Last activity" },
  { key: "created_at", label: "Created" },
] as const;

export type OpportunityColumn = (typeof opportunityColumns)[number]["key"];

/** What the table shows before anyone picks: the fields the list view already shows,
 * so switching between the two views does not change what is on screen. */
export const defaultOpportunityColumns: readonly OpportunityColumn[] = [
  "account_name",
  "stage",
  "value",
  "expected_close_date",
  "owner_name",
] as const;

export const emptyOpportunityViewState: OpportunityViewState = {
  q: "",
  stage: "",
  stalled: "",
  sortField: "updated_at",
  sortDirection: "desc",
  view: "board",
  columns: defaultOpportunityColumns.join(","),
  month: "",
  ids: "",
};

/**
 * The chosen columns as a list, ignoring anything the URL carries that is not
 * a column — a hand-edited or stale link should draw a table, not nothing.
 * An empty selection falls back to the default set for the same reason.
 */
export function columnsFromState(value: string): OpportunityColumn[] {
  const known = new Set<string>(opportunityColumns.map((column) => column.key));
  const chosen = value
    .split(",")
    .map((key) => key.trim())
    .filter((key): key is OpportunityColumn => known.has(key));
  return chosen.length > 0 ? chosen : [...defaultOpportunityColumns];
}

/** One cell's text. Stage is not here — the table draws it as the same
 * move-to-stage control the list does, for the owner who may change it. */
export function opportunityCell(
  opportunity: Opportunity,
  column: OpportunityColumn,
): string {
  switch (column) {
    case "value":
      return formatMoney(opportunity.currency, opportunity.value);
    case "expected_close_date":
      return opportunity.expected_close_date ?? "Not set";
    case "updated_at":
    case "created_at":
      // Date alone: a table row is one line, and the time of day is not what
      // anyone scans a column of dates for.
      return opportunity[column].slice(0, 10);
    default:
      return opportunity[column];
  }
}

/* --- Editing where content is read (milestone 2.11) -----------------------
 *
 * `AGENTS.md` v2 scope item 12: "content is edited where it is read, not in a
 * form elsewhere on the page". An opportunity's fields are read as fields in
 * two places — the table grid and the opportunity's own heading — and this is
 * the one declaration both of them edit through, so a field cannot be
 * editable as a table cell and not as a heading, or send a different patch
 * from each.
 *
 * Currency is deliberately absent: it is read as part of the value
 * (`formatMoney`) rather than as a field of its own, and it is the one
 * opportunity field nobody changes after the first keystroke (**D-098**). It
 * stays in the create/edit dialog with everything else.
 */

/** A partial `PATCH /api/v2/opportunities/{id}` body: the route updates
 * exactly the fields it is given (`backend/app/routes_opportunities.py`), so
 * one edited field is one key. */
export type OpportunityFieldPatch = Partial<
  Pick<
    Opportunity,
    "name" | "account_name" | "value" | "stage" | "expected_close_date"
  >
>;

export interface EditableOpportunityField {
  label: string;
  /** Which editor to draw. `stage` is the fixed list, so it is a select over
   * `stages` rather than free text (`AGENTS.md` invariant 6). */
  input: "text" | "number" | "date" | "stage";
  /** What the editor opens with, as the input element's own string value —
   * not what the cell reads, which is formatted for scanning. */
  read: (opportunity: Opportunity) => string;
  /** What one edit sends. An empty close date clears the column, which is why
   * this returns `null` rather than omitting the key. */
  patch: (value: string) => OpportunityFieldPatch;
}

export const editableOpportunityFields: Record<
  "name" | "account_name" | "value" | "stage" | "expected_close_date",
  EditableOpportunityField
> = {
  name: {
    label: "Opportunity",
    input: "text",
    read: (opportunity) => opportunity.name,
    patch: (value) => ({ name: value }),
  },
  account_name: {
    label: "Account",
    input: "text",
    read: (opportunity) => opportunity.account_name,
    patch: (value) => ({ account_name: value }),
  },
  value: {
    label: "Value",
    input: "number",
    read: (opportunity) => opportunity.value,
    patch: (value) => ({ value }),
  },
  stage: {
    label: "Stage",
    input: "stage",
    read: (opportunity) => opportunity.stage,
    patch: (value) => ({ stage: value as Stage }),
  },
  expected_close_date: {
    label: "Close date",
    input: "date",
    read: (opportunity) => opportunity.expected_close_date ?? "",
    patch: (value) => ({ expected_close_date: value || null }),
  },
};

export type OpportunityEditableKey = keyof typeof editableOpportunityFields;

/** Whether a table column is one of the editable fields. The column list and
 * the editable list overlap rather than coincide — owner, last activity and
 * created are columns nobody edits — so the table asks this rather than
 * assuming. */
export function editableField(
  column: OpportunityColumn,
): EditableOpportunityField | null {
  return column in editableOpportunityFields
    ? editableOpportunityFields[column as OpportunityEditableKey]
    : null;
}

/**
 * Filters and sorts the already-fetched opportunity list against a view
 * state. Client-side rather than a new query parameter on
 * `GET /api/v2/opportunities` (D-061, reaffirmed at 2.9 by **D-093**):
 * `useOpportunities` walks that endpoint to its last page, so the rows are
 * already in the cache and a server-side predicate would send the same data
 * back in a different order, adding a round trip to every filter press. It
 * is also not only a filter — the keyboard cursor, the bulk selection and
 * the calendar's month are all derived from this result.
 */
export function applyOpportunityView(
  opportunities: Opportunity[],
  state: OpportunityViewState,
): Opportunity[] {
  const keyword = state.q.trim().toLowerCase();
  const pinned = pinnedIds(state.ids);
  const filtered = opportunities.filter((opportunity) => {
    if (pinned && !pinned.has(opportunity.id)) {
      return false;
    }
    if (state.stage && opportunity.stage !== state.stage) {
      return false;
    }
    if (state.stalled === "true" && !opportunity.stalled) {
      return false;
    }
    if (state.stalled === "false" && opportunity.stalled) {
      return false;
    }
    if (keyword) {
      const haystack =
        `${opportunity.name} ${opportunity.account_name} ${opportunity.owner_name}`.toLowerCase();
      if (!haystack.includes(keyword)) {
        return false;
      }
    }
    return true;
  });

  const direction = state.sortDirection === "asc" ? 1 : -1;
  return [...filtered].sort(
    (a, b) => compareOpportunities(a, b, state.sortField) * direction,
  );
}

/**
 * The pinned selection as a set, or `null` when nothing is pinned — which is
 * not the same as an empty set: a view that pins nothing shows everything,
 * and one whose every pinned deal has since been deleted shows none of them.
 * A hand-edited or stale link that carries something other than numbers is
 * read as the numbers it does carry, the way `columnsFromState` reads a
 * stale column list.
 */
export function pinnedIds(value: string): Set<number> | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  return new Set(
    trimmed
      .split(",")
      .map((id) => Number(id.trim()))
      .filter((id) => Number.isInteger(id) && id > 0),
  );
}

/**
 * One field's ordering, ascending. Every sort in the app goes through this —
 * the filter bar's dropdown and the table's column headers are the same
 * setting asked two ways (milestone 2.8).
 *
 * Stage sorts by its position in the fixed pipeline rather than
 * alphabetically: "Closed Won" before "Needs Analysis" is the wrong answer to
 * the only question anyone sorts a stage column to ask.
 */
function compareOpportunities(
  a: Opportunity,
  b: Opportunity,
  field: OpportunitySortField,
): number {
  switch (field) {
    case "value":
      return Number(a.value) - Number(b.value);
    case "stage":
      return stages.indexOf(a.stage) - stages.indexOf(b.stage);
    case "expected_close_date":
      // Undated deals sort together at the far end rather than scattering
      // through the dated ones.
      return (a.expected_close_date ?? "").localeCompare(
        b.expected_close_date ?? "",
      );
    default:
      return a[field].localeCompare(b[field]);
  }
}

export type SavedView = components["schemas"]["SavedViewPublic"];
export type SavedViewEntity = SavedView["entity"];

/** Which state a saved view belongs to, in the words the interface uses. Both
 * menus render one of these at once (the board's and the open timeline's), so
 * every label they write says which. */
export function savedViewEntityLabel(entity: SavedViewEntity): string {
  return entity === "opportunities" ? "opportunity" : "timeline";
}

/**
 * What a saved view's `is_shared` flag means to the person reading it
 * (milestone 2.13, **D-076**).
 *
 * `is_shared` is one boolean, but it reads as three different facts depending
 * on who is looking: my private view, my view that everyone can apply, and
 * someone else's view that reached me. The reviewer who failed check 08 could
 * not tell the first two apart and had no way to know the third was not their
 * own, so the words are defined once here and used everywhere a view is
 * named -- the dropdown, the applied-view line, and the manage dialog.
 */
export function savedViewVisibility(
  view: SavedView,
  userId: number | undefined,
): string {
  if (view.created_by !== userId) {
    return `shared by ${view.creator_name}`;
  }
  return view.is_shared ? "shared with everyone" : "private";
}

/**
 * The view's name as one line: what it is called, whether it opens by
 * default, and who can use it.
 */
export function savedViewLabel(
  view: SavedView,
  userId: number | undefined,
): string {
  const marker = view.is_default ? " (default)" : "";
  return `${view.name}${marker} - ${savedViewVisibility(view, userId)}`;
}

/**
 * Whether a view state is exactly what a saved view holds, which is how the
 * board knows which view is applied: nothing records that, because applying
 * one only writes its filters into the URL (milestone 2.2), and the URL is
 * the whole mechanism behind a shareable view. Comparing instead of tracking
 * also means the line goes away by itself the moment a filter is changed.
 *
 * Two views with identical filters are indistinguishable here and the first
 * wins -- they are the same question asked twice, under two names.
 */
export function matchesSavedView<T extends Record<string, string>>(
  view: SavedView,
  state: T,
  defaults: T,
): boolean {
  const applied = { ...defaults, ...(view.filters as Partial<T>) };
  return Object.keys(defaults).every((key) => applied[key] === state[key]);
}

/** One turn of the read-only AI conversation about an opportunity. */
export interface AiChatMessage {
  role: "user" | "assistant";
  body: string;
  referenced_entry_ids?: number[];
}

/**
 * The board read as one list: stage column by stage column, and within a
 * column in the order the view state sorted them.
 *
 * `j` and `k` move through this (milestone 2.4a), so the keyboard walks the
 * cards in the order the eye does rather than in whatever order the API
 * returned them.
 */
export function boardOrder(opportunities: Opportunity[]): Opportunity[] {
  return stages.flatMap((stage) =>
    opportunities.filter((opportunity) => opportunity.stage === stage),
  );
}

/**
 * The reading order of whichever view is on screen, which is the order the
 * keyboard cursor and a shift-click range both walk.
 *
 * The list and the table already arrive sorted by `applyOpportunityView`, so
 * they read top to bottom; the board regroups that same list into stage
 * columns, so it reads column by column (`boardOrder`); the calendar reads by
 * date, and only the month on screen is in it (`monthOrder`) — `j` cannot
 * move to a card that is not drawn.
 */
export function viewOrder(
  opportunities: Opportunity[],
  view: OpportunityView,
  month: string,
): Opportunity[] {
  switch (view) {
    case "list":
    case "table":
      return opportunities;
    case "calendar":
      return monthOrder(opportunities, month);
    default:
      return boardOrder(opportunities);
  }
}

/* --- Calendar (milestone 2.8) ----------------------------------------------
 *
 * Every date here is handled as the `YYYY-MM-DD` text the API stores and in
 * UTC, never as a local `Date` parsed from that text: `new Date("2026-12-01")`
 * is midnight UTC, which is the previous day west of Greenwich, and a calendar
 * that draws a deal in the wrong cell for half the world is worse than no
 * calendar. `lib/time.ts` makes the same distinction for timestamps; close
 * dates carry no time of day at all, so they are never converted.
 */

/** Days of the week as the grid draws them, Monday first. */
export const weekdayLabels = [
  "Mon",
  "Tue",
  "Wed",
  "Thu",
  "Fri",
  "Sat",
  "Sun",
] as const;

/** `YYYY-MM` for a date. */
function monthOf(date: Date): string {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** `YYYY-MM-DD` for a date. */
function dayOf(date: Date): string {
  return `${monthOf(date)}-${String(date.getUTCDate()).padStart(2, "0")}`;
}

/**
 * The month a calendar should draw: what the URL asked for, or the month the
 * reader is in when it asked for nothing. Empty rather than today's month is
 * the stored default so a saved view or a shared link with no month in it
 * always opens on the reader's own month rather than on whichever one it was
 * written in.
 */
export function resolveMonth(month: string, today: Date = new Date()): string {
  return /^\d{4}-\d{2}$/.test(month) ? month : monthOf(today);
}

/** The month `step` months either side of this one. */
export function shiftMonth(month: string, step: number): string {
  const [year, index] = month.split("-").map(Number);
  return monthOf(new Date(Date.UTC(year, index - 1 + step, 1)));
}

/** "December 2026" — the heading above the grid. */
export function monthLabel(month: string): string {
  const [year, index] = month.split("-").map(Number);
  return new Date(Date.UTC(year, index - 1, 1)).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

/**
 * The grid: whole weeks, Monday first, covering the month and no more. Each
 * cell is a `YYYY-MM-DD` day, including the few days of the neighbouring
 * months that share the first and last weeks — they are drawn dimmed rather
 * than left blank, so the week rows stay whole.
 */
export function calendarWeeks(month: string): string[][] {
  const [year, index] = month.split("-").map(Number);
  const first = new Date(Date.UTC(year, index - 1, 1));
  const last = new Date(Date.UTC(year, index, 0));
  // Monday = 0, which `getUTCDay` (Sunday = 0) does not give directly.
  const start = new Date(first);
  start.setUTCDate(first.getUTCDate() - ((first.getUTCDay() + 6) % 7));

  const weeks: string[][] = [];
  const cursor = new Date(start);
  while (cursor <= last || weeks.length === 0) {
    const week: string[] = [];
    for (let day = 0; day < 7; day += 1) {
      week.push(dayOf(cursor));
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
    weeks.push(week);
  }
  return weeks;
}

/** The opportunities closing on one day. */
export function closingOn(
  opportunities: Opportunity[],
  day: string,
): Opportunity[] {
  return opportunities.filter(
    (opportunity) => opportunity.expected_close_date === day,
  );
}

/** The ones with no close date, which a calendar cannot place and must
 * therefore still account for — a deal missing from the month is a deal the
 * reader thinks they do not have. */
export function withoutCloseDate(opportunities: Opportunity[]): Opportunity[] {
  return opportunities.filter(
    (opportunity) => !opportunity.expected_close_date,
  );
}

/**
 * The calendar as one list, in the order it is read: the drawn month day by
 * day, then the undated deals listed beneath it. Anything closing in another
 * month is not on screen and is not here.
 */
export function monthOrder(
  opportunities: Opportunity[],
  month: string,
): Opportunity[] {
  const days = calendarWeeks(month).flat();
  return [
    ...days.flatMap((day) => closingOn(opportunities, day)),
    ...withoutCloseDate(opportunities),
  ];
}

/** The stage one step either side of an opportunity's own, or `null` at the
 * end of the fixed list (`AGENTS.md` invariant 6 — the list never grows). */
export function adjacentStage(stage: Stage, step: 1 | -1): Stage | null {
  return stages[stages.indexOf(stage) + step] ?? null;
}
