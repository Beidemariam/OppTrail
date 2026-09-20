"use client";

import { useState } from "react";
import { Outlet, useMatch, useNavigate, useSearchParams } from "react-router";

import { confirmDelete } from "../lib/confirm";
import {
  applyOpportunityView,
  emptyOpportunityViewState,
  type Opportunity,
  type OpportunityViewState,
} from "../lib/domain";
import {
  useDeleteOpportunity,
  useOpportunities,
  useSession,
} from "../lib/queries";
import { paramsWithState, stateFromParams } from "../lib/viewState";
import { AuthPanel } from "./AuthPanel";
import { OpportunityFilterBar } from "./OpportunityFilterBar";
import { OpportunityForm } from "./OpportunityForm";
import { SavedViewsMenu } from "./SavedViewsMenu";
import { StageBoard } from "./StageBoard";
import { TopBar } from "./TopBar";

/**
 * The dashboard: the session gate, the stage board, and the panel beside it.
 *
 * It is the layout route for `/` and `/opportunities/:opportunityId`
 * (`AppRoot.tsx`), so the board stays mounted while the child route swaps the
 * panel. That is what gives an opportunity its own URL without reloading the
 * list behind it.
 */
export function DashboardPage() {
  const session = useSession();
  const opportunities = useOpportunities(Boolean(session.data));
  const [editing, setEditing] = useState<Opportunity | null>(null);
  const deleteOpportunity = useDeleteOpportunity();
  const navigate = useNavigate();
  // Read from the URL rather than `useParams`, which in a layout route only
  // sees the segments its own path matched.
  const opened = useMatch("/opportunities/:opportunityId");
  const selectedId = opened ? Number(opened.params.opportunityId) : null;

  // The board's filter/sort state lives in the URL too (milestone 2.2), the
  // same way the timeline's does.
  const [searchParams, setSearchParams] = useSearchParams();
  const viewState = stateFromParams<OpportunityViewState>(
    searchParams,
    emptyOpportunityViewState,
    "opportunities",
  );
  function setViewState(next: OpportunityViewState) {
    setSearchParams(
      paramsWithState(
        searchParams,
        next,
        emptyOpportunityViewState,
        "opportunities",
      ),
    );
  }
  const visibleOpportunities = applyOpportunityView(
    opportunities.data ?? [],
    viewState,
  );

  if (session.isPending) {
    return (
      <main className="app-shell">
        <p className="status">Loading...</p>
      </main>
    );
  }

  if (!session.data) {
    return <AuthPanel />;
  }

  function remove(opportunity: Opportunity) {
    if (!confirmDelete(`"${opportunity.name}" and its entire timeline`)) {
      return;
    }

    deleteOpportunity.mutate(opportunity.id, {
      onSuccess: () => {
        if (editing?.id === opportunity.id) {
          setEditing(null);
        }
        if (selectedId === opportunity.id) {
          navigate("/", { replace: true });
        }
      },
    });
  }

  return (
    <main className="app-shell">
      <TopBar user={session.data} />

      <section className="dashboard-layout">
        {/* Re-keyed so switching which opportunity is being edited reloads the
            fields, and finishing an edit empties them. */}
        <OpportunityForm
          key={editing?.id ?? "new"}
          editing={editing}
          onDone={() => setEditing(null)}
        />

        <section className="workspace">
          {opportunities.isError && (
            <p className="error">{opportunities.error.message}</p>
          )}
          {deleteOpportunity.isError && (
            <p className="error">{deleteOpportunity.error.message}</p>
          )}

          <SavedViewsMenu
            entity="opportunities"
            state={viewState}
            defaults={emptyOpportunityViewState}
            onApply={setViewState}
          />
          <OpportunityFilterBar state={viewState} onApply={setViewState} />

          <StageBoard
            opportunities={visibleOpportunities}
            selectedId={selectedId}
            onEdit={setEditing}
            onDelete={remove}
          />

          <Outlet />
        </section>
      </section>
    </main>
  );
}

/** The panel at `/`, before an opportunity has been opened. */
export function NoOpportunitySelected() {
  return (
    <section className="timeline-panel empty-panel">
      <h2>Select an opportunity to open its timeline.</h2>
    </section>
  );
}
