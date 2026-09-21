"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router";

import {
  emptyTimelineFilters,
  type Access,
  type Opportunity,
  type TimelineEntry,
  type TimelineFilters,
} from "../lib/domain";
import { useKeyboardShortcuts } from "../lib/keyboard";
import {
  canChangeItem,
  canManageOpportunity,
  canWriteTimeline,
} from "../lib/permissions";
import { useOpportunities, useSession, useTimeline } from "../lib/queries";
import { paramsWithState, stateFromParams } from "../lib/viewState";
import { AiSidebar } from "./AiSidebar";
import { SavedViewsMenu } from "./SavedViewsMenu";
import { SharingPanel } from "./SharingPanel";
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
  const [editingEntry, setEditingEntry] = useState<TimelineEntry | null>(null);
  // The views above are a full screen of board or list, so an opportunity
  // opened from the bottom of a column would otherwise land below the fold and
  // leave the reader looking at the thing they just clicked away from
  // (milestone 2.7). Bound to the id rather than to every render, so reading a
  // timeline is never interrupted by its own refetch — and declared here,
  // above the "not available" return, because a hook after a conditional
  // return is a hook that sometimes does not run.
  const panelRef = useRef<HTMLElement>(null);
  useEffect(() => {
    panelRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [opportunityId]);
  const entryTitleRef = useRef<HTMLInputElement>(null);
  const session = useSession();
  const opportunities = useOpportunities(true);
  const timeline = useTimeline(opportunityId, filters);

  // `c` means "create the thing this screen is about", so while a timeline is
  // open it composes an entry rather than an opportunity (milestone 2.4a).
  // `DashboardPage` stands its own `c` down whenever this panel is mounted.
  useKeyboardShortcuts({ c: () => entryTitleRef.current?.focus() });

  const opportunity =
    opportunities.data?.find((candidate) => candidate.id === opportunityId) ??
    null;

  if (!opportunity) {
    return (
      <section className="timeline-panel empty-panel">
        {opportunities.isPending ? (
          <p className="status">Loading timeline...</p>
        ) : (
          <h2>This opportunity is not available.</h2>
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
    <section className="timeline-panel" ref={panelRef}>
      <TimelineHeading
        opportunity={opportunity}
        onRefresh={() => void timeline.refetch()}
      />

      {access.canManage && <SharingPanel opportunityId={opportunityId} />}

      <SavedViewsMenu
        entity="timeline"
        state={filters}
        defaults={emptyTimelineFilters}
        onApply={setFilters}
      />

      <TimelineFilterBar filters={filters} onApply={setFilters} />

      {access.canWriteTimeline && (
        <TimelineEntryForm
          key={editingEntry?.id ?? "new"}
          opportunityId={opportunityId}
          editing={editingEntry}
          titleRef={entryTitleRef}
          onDone={() => setEditingEntry(null)}
        />
      )}

      {timeline.isError ? (
        <p className="error">{timeline.error.message}</p>
      ) : timeline.isPending ? (
        <p className="status">Loading timeline...</p>
      ) : (
        <TimelineEntryList
          entries={timeline.data}
          access={access}
          onEdit={setEditingEntry}
        />
      )}

      <AiSidebar opportunityId={opportunityId} />
    </section>
  );
}

function TimelineHeading({
  opportunity,
  onRefresh,
}: {
  opportunity: Opportunity;
  onRefresh: () => void;
}) {
  return (
    <div className="timeline-heading">
      <div>
        <p className="eyebrow">{opportunity.account_name}</p>
        <h2>{opportunity.name}</h2>
        <p className="meta-row">Your role: {opportunity.current_user_role}</p>
      </div>
      <div className="export-actions">
        {(["pdf", "csv", "json"] as const).map((format) => (
          <a
            key={format}
            className="secondary-button"
            href={`/api/opportunities/${opportunity.id}/export/${format}`}
          >
            {format.toUpperCase()}
          </a>
        ))}
        <button type="button" className="secondary-button" onClick={onRefresh}>
          Refresh
        </button>
      </div>
    </div>
  );
}
