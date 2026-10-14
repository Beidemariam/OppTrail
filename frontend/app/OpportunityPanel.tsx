"use client";

import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import {
  emptyTimelineFilters,
  formatMoney,
  timelineFiltersApplied,
  type Access,
  type Opportunity,
  type TimelineFilters,
  customFieldText,
  linkTargetFromParams,
  type CustomValues,
} from "../lib/domain";
import { useKeyboardShortcuts } from "../lib/keyboard";
import { useLiveUpdates } from "../lib/liveUpdates";
import {
  canChangeItem,
  canManageOpportunity,
  canWriteTimeline,
} from "../lib/permissions";
import {
  useCustomFields,
  useMembers,
  useOpportunities,
  useSession,
  useSetWatch,
  useTimeline,
  useWatchStatus,
} from "../lib/queries";
import type { SuggestionSources } from "../lib/suggestions";
import { boardHref, paramsWithState, stateFromParams } from "../lib/viewState";
import { ActivityButton } from "./ActivityDialog";
import { AiSidebar } from "./AiSidebar";
import {
  OpportunityField,
  useInlineEditor,
  useOpportunityFieldSave,
} from "./InlineEdit";
import { SavedViewsMenu } from "./SavedViewsMenu";
import { SharingPanel } from "./SharingPanel";
import { SuggestionSourceProvider } from "./Suggestions";
import { TaskPanel } from "./TaskPanel";
import { TimelineEntryForm } from "./TimelineEntryForm";
import { TimelineEntryList } from "./TimelineEntryList";
import { TimelineFilterBar } from "./TimelineFilterBar";

/**
 * The timeline at `/opportunities/:opportunityId`.
 *
 * Re-keyed on the id so opening another opportunity starts with a clean filter
 * bar and entry form rather than inheriting the last one's.
 */
export function OpportunityPanel() {
  const { opportunityId } = useParams();
  const id = Number(opportunityId);

  if (!Number.isInteger(id) || id <= 0) {
    return (
      <main className="app-shell empty-panel">
        <h2>Select an opportunity to open its timeline.</h2>
      </main>
    );
  }

  return <OpportunityTimeline key={id} opportunityId={id} />;
}

function OpportunityTimeline({ opportunityId }: { opportunityId: number }) {
  // The applied filter set lives in the URL (milestone 2.2), so a reload, the
  // back button and a saved view all arrive here the same way: as a change to
  // `searchParams`, not to component state.
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = stateFromParams<TimelineFilters>(
    searchParams,
    emptyTimelineFilters,
    "timeline",
  );
  function setFilters(next: TimelineFilters) {
    setSearchParams(
      paramsWithState(searchParams, next, emptyTimelineFilters, "timeline"),
    );
  }
  // What a link pointed at inside this timeline (milestone 3.2, **D-124**;
  // extended to notes and comments by milestone 6.0): `lib/suggestions.ts`
  // writes `?entry=` and search writes whichever level it matched, and this is
  // the other half of it — the row is scrolled to and marked, so a reader
  // arriving from a link or a search result lands on the thing it referred to
  // rather than at the top of a timeline.
  const linkTarget = linkTargetFromParams(searchParams);
  // A boolean, not the object: `linkTargetFromParams` builds a fresh one every
  // render, so depending on it below would re-run the effect on every render
  // and scroll a reader back to the top of the panel as they read. The effect
  // only asks whether something else has claimed the scroll.
  const hasLinkTarget = linkTarget !== null;

  // Until R.1 this panel scrolled itself into view, because it was appended
  // below a full screen of board (2.7). It is its own page now and the shell
  // puts every navigation at the top, so the only scrolling left here is a
  // link naming a row inside the timeline (`useLinkTarget`).
  const entryTitleRef = useRef<HTMLInputElement>(null);
  const session = useSession();
  const opportunities = useOpportunities(true);
  const timeline = useTimeline(opportunityId, filters);
  // What the composers' `@` and `#` triggers offer (milestone 3.2). The people
  // are a read of their own; the entries are the timeline *unfiltered*, because
  // a link may point at an entry the filter bar is currently hiding — with no
  // filters applied that is the same query key as the read above, so the common
  // case costs no second request.
  const members = useMembers(opportunityId);
  const linkable = useTimeline(opportunityId, emptyTimelineFilters);
  const suggestions: SuggestionSources = {
    opportunityId,
    people: (members.data ?? []).map((member) => ({
      email: member.email,
      name: member.name,
      role: member.role,
    })),
    entries: (linkable.data ?? []).map((entry) => ({
      id: entry.id,
      title: entry.title,
      type: entry.type,
    })),
  };

  // Somebody else's writes on this deal, pushed rather than polled (milestone
  // 3.4, ADR 0003). Declared here, above the "not available" return, for the
  // same reason the scroll effect is: a hook after a conditional return is a
  // hook that sometimes does not run. A reader with no access gets 404 from
  // the stream, which `EventSource` treats as a failed connection and does not
  // retry (`lib/liveUpdates.ts`).
  useLiveUpdates(opportunityId);

  // The entry composer is collapsed until it is asked for (milestone 3.7,
  // D-136 finding 3): expanded it is 400px of form between the filter bar and
  // the first entry, which is what put the timeline below the fold. Same
  // progressive disclosure as a note's or a comment's `Composer`
  // (`app/RichTextEditor.tsx`, D-110), and the same open/close and focus rule
  // as every other editor that replaces its own trigger — including putting
  // focus back on the trigger when it closes, which is what makes Cancel
  // leave the reader where they started rather than at the top of the page.
  // Whether the AI drawer is open (R.1, decision 2A). Component state rather
  // than a URL parameter: it is not a reading of this deal that another person
  // would want a link to, unlike a filter or an entry id.
  const [asking, setAsking] = useState(false);
  // The timeline's filter controls, and where `/` puts the cursor. The open
  // state is the screen's for the reason the board's is (R.1): a shortcut has
  // to be able to open the controls before it can focus one of them.
  const [filtersOpen, setFiltersOpen] = useState(
    () => timelineFiltersApplied(filters) > 0,
  );
  const keywordFilterRef = useRef<HTMLInputElement>(null);
  const focusKeyword = useRef(false);
  useEffect(() => {
    if (filtersOpen && focusKeyword.current) {
      focusKeyword.current = false;
      keywordFilterRef.current?.focus();
    }
  }, [filtersOpen]);

  const composeRef = useRef<HTMLButtonElement>(null);
  const composer = useInlineEditor(composeRef, entryTitleRef);

  // `c` means "create the thing this screen is about", so while a timeline is
  // open it composes an entry rather than an opportunity (milestone 2.4a).
  // `DashboardPage` stands its own `c` down whenever this panel is mounted.
  // With the composer collapsed it opens it and lands on the title; a second
  // `c` while it is already open is the same focus move, since `open` on an
  // open editor re-runs nothing.
  useKeyboardShortcuts({
    c: () => {
      composer.open();
      entryTitleRef.current?.focus();
    },
    // `/` means "filter what is on this screen" (R.1): the board's keyword box
    // on the board, the timeline's here. The board is not mounted behind this
    // page any more, so without this the chord did nothing at all.
    "/": () => {
      focusKeyword.current = true;
      setFiltersOpen(true);
      keywordFilterRef.current?.focus();
    },
    // Esc puts the drawer away, which is what Esc means everywhere else in
    // this app. Bound only while it is open, so it does not swallow the key
    // from anything else on the screen.
    ...(asking ? { Escape: () => setAsking(false) } : {}),
  });

  const opportunity =
    opportunities.data?.find((candidate) => candidate.id === opportunityId) ??
    null;

  if (!opportunity) {
    return (
      <main className="app-shell empty-panel">
        {opportunities.isPending ? (
          <p className="status">Loading timeline...</p>
        ) : (
          <>
            <h2>This opportunity is not available.</h2>
            {/* Watching an opportunity you are not shared on (milestone
                3.3a, D-129) has no discovery UI of its own -- a colleague
                names the id out of band -- so this is the one place it is
                reachable: the same URL a share would open, offering the one
                thing available with no access at all. */}
            <WatchToggle opportunityId={opportunityId} />
          </>
        )}
      </main>
    );
  }

  // The rules themselves live in ../lib/permissions.ts, next to the note
  // explaining why editing and deleting resolve through one function.
  const role = opportunity.current_user_role;
  const access: Access = {
    canManage: canManageOpportunity(role),
    canWriteTimeline: canWriteTimeline(role),
    canChangeItem: (authorId) =>
      canChangeItem({ role, userId: session.data?.id, authorId }),
  };

  return (
    <SuggestionSourceProvider sources={suggestions}>
      {/* The screen's own landmark, like every other page in the shell: the
          deal used to render inside the dashboard's `main`, and a route of its
          own needs one of its own (R.1). */}
      <main className="app-shell deal-page">
        {/* The record, pinned (R.1, decision 2A). It used to sit inside the
            right-hand column beneath the AI panel (3.1a, D-115), where a long
            answer pushed it — and the deal's tasks under it — two screens
            down. A deal's identity is the one thing that should never leave
            the window, so it is a band of its own across the top and the rail
            below holds only what hangs off it. */}
        <RecordHeader
          opportunity={opportunity}
          canManage={access.canManage}
          order={filters.order}
          onRefresh={() => void timeline.refetch()}
          entryCount={(linkable.data ?? []).length}
          asking={asking}
          onAsk={() => setAsking((open) => !open)}
        />

        <div className={asking ? "deal-body is-asking" : "deal-body"}>
          <div className="timeline-column">
            <SavedViewsMenu
              entity="timeline"
              state={filters}
              defaults={emptyTimelineFilters}
              onApply={setFilters}
            />

            <TimelineFilterBar
              filters={filters}
              onApply={setFilters}
              open={filtersOpen}
              onOpenChange={setFiltersOpen}
              keywordRef={keywordFilterRef}
            />

            {/* The composer only, since milestone 2.11: editing an existing entry
            happens in that entry's own card, where the reader already is. */}
            {access.canWriteTimeline &&
              (composer.editing ? (
                <TimelineEntryForm
                  opportunityId={opportunityId}
                  editing={null}
                  titleRef={entryTitleRef}
                  onDone={composer.close}
                />
              ) : (
                <p className="compose-trigger">
                  <button
                    type="button"
                    ref={composeRef}
                    className="primary-button"
                    aria-expanded={false}
                    onClick={composer.open}
                  >
                    New entry
                  </button>
                </p>
              ))}

            {timeline.isError ? (
              <p className="error">{timeline.error.message}</p>
            ) : timeline.isPending ? (
              <p className="status">Loading timeline...</p>
            ) : (
              <TimelineEntryList
                entries={timeline.data}
                opportunityId={opportunityId}
                access={access}
                linkTarget={linkTarget}
              />
            )}
          </div>

          {/* Tasks first in the rail, and nothing above them that can grow
            (R.1, decision 2A). An action item is a fact about the deal rather
            than an event on its timeline (4.1), so this is where it belongs —
            and it is what the reader came looking for when they said the
            tasks had disappeared. */}
          <div className="sidebar-column">
            <TaskPanel
              opportunityId={opportunityId}
              access={access}
              linkTarget={linkTarget}
            />

            {access.canManage && <SharingPanel opportunityId={opportunityId} />}
          </div>

          {/* The AI overlays the rail and never the timeline, and only when
            asked for. It is mounted while open and unmounted when closed;
            the transcript is cache state (`["ai-conversation", id]`, D-055),
            so closing it keeps the conversation. */}
          {asking && (
            <AiSidebar
              opportunityId={opportunityId}
              onClose={() => setAsking(false)}
            />
          )}
        </div>
      </main>
    </SuggestionSourceProvider>
  );
}

/**
 * The opportunity's own record, above its timeline: what it is called, who it
 * is with, what it is worth, where it stands and when it closes.
 *
 * Every one of those is edited here rather than in the dialog on the board
 * behind this panel (milestone 2.11). `docs/UX.md` asks the header to hold
 * "the facts a rep needs constantly: value, stage, close date", and a fact
 * displayed beside an Edit button that opens a form somewhere else is exactly
 * what `AGENTS.md` v2 scope item 12 rules out. Owner-only, like every other
 * change to an opportunity's own fields — a viewer or an editor reads the
 * same line with no affordance on it.
 */
function RecordHeader({
  opportunity,
  canManage,
  order,
  onRefresh,
  entryCount,
  asking,
  onAsk,
}: {
  opportunity: Opportunity;
  canManage: boolean;
  /** The timeline's own reading order, passed to the export so the document
   * runs the way this screen does (milestone 4.4b). */
  order: TimelineFilters["order"];
  onRefresh: () => void;
  /** Every entry on the deal, not the filtered page: a count that changed
   * when a filter did would be reporting the filter rather than the deal. */
  entryCount: number;
  asking: boolean;
  onAsk: () => void;
}) {
  const save = useOpportunityFieldSave();
  // The board's parameters, read here so the way back can hand them over.
  const [params] = useSearchParams();
  const facts = ["value", "stage", "expected_close_date"] as const;
  // The deal's own custom fields, beside the three fixed facts (6.2a, the
  // human's request at the 6.2 review: "please include Business field as one
  // of the things to show in the top line summary of the opportunity"). Read
  // only here: a value's control depends on its field's type, and this row is
  // one line of facts rather than a form -- it is set in Edit, which is where
  // `CustomFieldInputs` renders the right control for each type.
  const fields = useCustomFields("opportunity");
  const values = (opportunity.custom_values ?? {}) as CustomValues;
  return (
    <header className="record-header">
      <div className="record-main">
        <p className="record-crumb">
          {/* Back to the board, carrying its view state: the filters, the
              sort, the chosen view and the month all live in the URL, so this
              is what makes "the board as you left it" true rather than said
              (R.1, decision 1A). */}
          <Link to={boardHref(params)}>&larr; Opportunities</Link>
        </p>
        {/* The name and the account on one line: this band never leaves the
            window, so every row it keeps is a row the timeline does not get. */}
        <div className="record-identity">
          <h2>
            <OpportunityField
              opportunity={opportunity}
              field="name"
              editable={canManage}
              save={save}
            >
              {opportunity.name}
            </OpportunityField>
          </h2>
          <p className="eyebrow">
            <OpportunityField
              opportunity={opportunity}
              field="account_name"
              editable={canManage}
              save={save}
            >
              {opportunity.account_name}
            </OpportunityField>
          </p>
        </div>
        <p className="meta-row opportunity-facts">
          {facts.map((field) => (
            <OpportunityField
              key={field}
              opportunity={opportunity}
              field={field}
              editable={canManage}
              save={save}
            >
              {headingFact(opportunity, field)}
            </OpportunityField>
          ))}
          {(fields.data ?? [])
            // Only the ones this deal has a value for. A summary line listing
            // every defined field as empty is a longer line that says less.
            .filter((field) => customFieldText(field, values[field.key]) !== "")
            .map((field) => (
              <span key={field.key}>
                {field.label}: {customFieldText(field, values[field.key])}
              </span>
            ))}
          <span>Your role: {opportunity.current_user_role}</span>
          {/* What is on this deal, as a count rather than as a section the
              reader has to scroll to find (R.1). */}
          <span className="record-count">
            {entryCount} {entryCount === 1 ? "entry" : "entries"}
          </span>
        </p>
      </div>
      <div className="export-actions">
        {/* The AI is opened from here and from nowhere else: it is an action
            on the deal, like exporting it or reading its history. */}
        <button
          type="button"
          className={asking ? "primary-button" : "secondary-button"}
          onClick={onAsk}
          aria-expanded={asking}
        >
          Ask
        </button>
        <ExportControl opportunityId={opportunity.id} order={order} />
        {/* One destination for what happened here, offered to every role:
            the log answers with the events the reader's role may see rather
            than refusing them, and an edit row opens to the field-by-field
            record that used to need its own button (3.0, 3.1c, D-121). */}
        <ActivityButton opportunityId={opportunity.id} />
        <button type="button" className="secondary-button" onClick={onRefresh}>
          Refresh
        </button>
      </div>
    </header>
  );
}

type ExportFormat = "pdf" | "csv" | "json";

const exportFormats: ExportFormat[] = ["pdf", "csv", "json"];

/**
 * One control for the three export formats (milestone 3.1a, D-115): three
 * always-visible PDF/CSV/JSON links read as a cluster of controls that could
 * be mistaken for the bulk action bar's own export-by-selection pair
 * (`BulkActionBar.tsx`) — a genuinely different scope, so the fix collapses
 * the per-opportunity trio rather than merging the two. The link's own text
 * names the format it will download, so picking one is visible without a
 * second label.
 */
function ExportControl({
  opportunityId,
  order,
}: {
  opportunityId: number;
  order: TimelineFilters["order"];
}) {
  const [format, setFormat] = useState<ExportFormat>("pdf");
  return (
    <>
      <select
        aria-label="Export format"
        value={format}
        onChange={(event) => setFormat(event.target.value as ExportFormat)}
      >
        {exportFormats.map((candidate) => (
          <option key={candidate} value={candidate}>
            {candidate.toUpperCase()}
          </option>
        ))}
      </select>
      <a
        className="secondary-button"
        href={`/api/v2/opportunities/${opportunityId}/export/${format}?order=${order}`}
      >
        Export {format.toUpperCase()}
      </a>
    </>
  );
}

/**
 * Follow or unfollow an opportunity with no access to it at all (milestone
 * 3.3a, D-129) -- `useWatchStatus` succeeds here precisely because it checks
 * only that the id is live, not who may read it, which is what makes this
 * renderable on the "not available" screen in the first place. Renders
 * nothing while the read is pending or fails (a genuinely unknown id), so the
 * empty panel says nothing more than it already does until watching is
 * actually offerable.
 */
function WatchToggle({ opportunityId }: { opportunityId: number }) {
  const status = useWatchStatus(opportunityId, true);
  const setWatch = useSetWatch(opportunityId);

  if (!status.isSuccess) {
    return null;
  }

  const watching = status.data.watching;
  return (
    <button
      type="button"
      className="secondary-button"
      disabled={setWatch.isPending}
      onClick={() => setWatch.mutate(!watching)}
    >
      {watching ? "Following - stop" : "Follow this opportunity"}
    </button>
  );
}

/** How a heading fact reads before it is edited. The editors underneath take
 * the raw value (`editableOpportunityFields[...].read`); this is the same
 * three fields written for a person scanning the line. */
function headingFact(
  opportunity: Opportunity,
  field: "value" | "stage" | "expected_close_date",
): string {
  switch (field) {
    case "value":
      return formatMoney(opportunity.currency, opportunity.value);
    case "stage":
      return opportunity.stage;
    default:
      return opportunity.expected_close_date
        ? `Closes ${opportunity.expected_close_date}`
        : "No close date";
  }
}
