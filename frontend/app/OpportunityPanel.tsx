"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router";

import {
  emptyTimelineFilters,
  formatMoney,
  type Access,
  type Opportunity,
  type TimelineFilters,
} from "../lib/domain";
import { useKeyboardShortcuts } from "../lib/keyboard";
import { useLiveUpdates } from "../lib/liveUpdates";
import {
  canChangeItem,
  canManageOpportunity,
  canWriteTimeline,
} from "../lib/permissions";
import {
  useMembers,
  useOpportunities,
  useSession,
  useSetWatch,
  useTimeline,
  useWatchStatus,
} from "../lib/queries";
import type { SuggestionSources } from "../lib/suggestions";
import { paramsWithState, stateFromParams } from "../lib/viewState";
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
      <section className="timeline-panel empty-panel">
        <h2>Select an opportunity to open its timeline.</h2>
      </section>
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
  // An entry named in the URL is one a link pointed at (milestone 3.2,
  // **D-124**): `lib/suggestions.ts` writes `?entry=`, and this is the other
  // half of it — the entry is scrolled to and marked so a reader arriving from
  // a note lands on the thing it referred to rather than at the top of a
  // timeline.
  const linkedEntryId = Number(searchParams.get("entry")) || null;

  // The views above are a full screen of board or list, so an opportunity
  // opened from the bottom of a column would otherwise land below the fold and
  // leave the reader looking at the thing they just clicked away from
  // (milestone 2.7). Bound to the id rather than to every render, so reading a
  // timeline is never interrupted by its own refetch — and declared here,
  // above the "not available" return, because a hook after a conditional
  // return is a hook that sometimes does not run.
  const panelRef = useRef<HTMLElement>(null);
  useEffect(() => {
    // Not when a link named an entry (milestone 3.2): that entry scrolls itself
    // into view, and this would then scroll straight past it back to the top —
    // child effects run before a parent's, so the last request would win.
    if (linkedEntryId) {
      return;
    }
    panelRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [opportunityId, linkedEntryId]);
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
  });

  const opportunity =
    opportunities.data?.find((candidate) => candidate.id === opportunityId) ??
    null;

  if (!opportunity) {
    return (
      <section className="timeline-panel empty-panel">
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
      </section>
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
      <section className="timeline-panel" ref={panelRef}>
        {/* The timeline itself, first (milestone 3.1a, D-115): the opportunity's
          own record used to open this panel, so a reader scrolled past it to
          reach what they came here for. That block now sits in the sidebar
          column instead, beneath the AI panel. */}
        <div className="timeline-column">
          <SavedViewsMenu
            entity="timeline"
            state={filters}
            defaults={emptyTimelineFilters}
            onApply={setFilters}
          />

          <TimelineFilterBar filters={filters} onApply={setFilters} />

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
              linkedEntryId={linkedEntryId}
            />
          )}
        </div>

        <div className="sidebar-column">
          <AiSidebar opportunityId={opportunityId} />

          <TimelineHeading
            opportunity={opportunity}
            canManage={access.canManage}
            onRefresh={() => void timeline.refetch()}
          />

          {/* Tasks sit with the deal's own record rather than in its history
              (milestone 4.1): an action item is a fact about the opportunity,
              not an event on its timeline. Every role sees the list; writing
              one needs `canWriteTimeline`, which the panel checks. */}
          <TaskPanel opportunityId={opportunityId} access={access} />

          {access.canManage && <SharingPanel opportunityId={opportunityId} />}
        </div>
      </section>
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
function TimelineHeading({
  opportunity,
  canManage,
  onRefresh,
}: {
  opportunity: Opportunity;
  canManage: boolean;
  onRefresh: () => void;
}) {
  const save = useOpportunityFieldSave();
  const facts = ["value", "stage", "expected_close_date"] as const;
  return (
    <div className="timeline-heading">
      <div>
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
          <span>Your role: {opportunity.current_user_role}</span>
        </p>
      </div>
      <div className="export-actions">
        <ExportControl opportunityId={opportunity.id} />
        {/* One destination for what happened here, offered to every role:
            the log answers with the events the reader's role may see rather
            than refusing them, and an edit row opens to the field-by-field
            record that used to need its own button (3.0, 3.1c, D-121). */}
        <ActivityButton opportunityId={opportunity.id} />
        <button type="button" className="secondary-button" onClick={onRefresh}>
          Refresh
        </button>
      </div>
    </div>
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
function ExportControl({ opportunityId }: { opportunityId: number }) {
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
        href={`/api/v2/opportunities/${opportunityId}/export/${format}`}
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
