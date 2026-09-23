"use client";

import { useEffect, useRef } from "react";
import { useParams, useSearchParams } from "react-router";

import {
  emptyTimelineFilters,
  formatMoney,
  opportunityVersionFields,
  type Access,
  type Opportunity,
  type TimelineFilters,
} from "../lib/domain";
import { useKeyboardShortcuts } from "../lib/keyboard";
import {
  canChangeItem,
  canManageOpportunity,
  canWriteTimeline,
} from "../lib/permissions";
import {
  useOpportunities,
  useOpportunityVersions,
  useSession,
  useTimeline,
} from "../lib/queries";
import { paramsWithState, stateFromParams } from "../lib/viewState";
import { AiSidebar } from "./AiSidebar";
import { HistoryButton } from "./HistoryDialog";
import { OpportunityField, useOpportunityFieldSave } from "./InlineEdit";
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
        canManage={access.canManage}
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

      {/* The composer only, since milestone 2.11: editing an existing entry
          happens in that entry's own card, where the reader already is. */}
      {access.canWriteTimeline && (
        <TimelineEntryForm
          opportunityId={opportunityId}
          editing={null}
          titleRef={entryTitleRef}
          onDone={() => {}}
        />
      )}

      {timeline.isError ? (
        <p className="error">{timeline.error.message}</p>
      ) : timeline.isPending ? (
        <p className="status">Loading timeline...</p>
      ) : (
        <TimelineEntryList
          entries={timeline.data}
          opportunityId={opportunityId}
          access={access}
        />
      )}

      <AiSidebar opportunityId={opportunityId} />
    </section>
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
        {(["pdf", "csv", "json"] as const).map((format) => (
          <a
            key={format}
            className="secondary-button"
            href={`/api/v2/opportunities/${opportunity.id}/export/${format}`}
          >
            {format.toUpperCase()}
          </a>
        ))}
        {/* Owner-only, like the sharing panel and the audit log below it
            (milestone 2.10, D-096). */}
        {canManage && (
          <HistoryButton
            title={`History of ${opportunity.name}`}
            fields={opportunityVersionFields}
            itemId={opportunity.id}
            useVersions={useOpportunityVersions}
          />
        )}
        <button type="button" className="secondary-button" onClick={onRefresh}>
          Refresh
        </button>
      </div>
    </div>
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
